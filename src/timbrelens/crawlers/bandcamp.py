import json
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from timbrelens.crawlers.common import (
    attribution,
    get_audio,
    licensed_track,
    parse_license,
    prepare_preview,
    read_robots,
    validate_options,
)
from timbrelens.files import sha256
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track


def discover(page: BeautifulSoup, url: str) -> list[str]:
    if urlsplit(url).path.startswith(("/album/", "/track/")):
        return [url]

    grid = page.select_one("#music-grid")
    if grid is None:
        raise ValueError(f"Bandcamp release grid not found: {url}")

    links = [str(anchor["href"]) for anchor in grid.select("a[href]")]

    # Releases beyond the first sixteen are embedded for the site's “show more” button.
    links.extend(item["page_url"] for item in json.loads(grid.get("data-client-items", "[]")))

    releases = []
    for link in links:
        release = urljoin(url, link)
        parts = urlsplit(release)
        if parts.hostname != urlsplit(url).hostname:
            continue

        if parts.path.startswith(("/album/", "/track/")) and release not in releases:
            releases.append(release)

    if not releases:
        raise ValueError(f"No Bandcamp releases found: {url}")

    return releases


def map_track(
    page: BeautifulSoup, url: str, source: str, artist: str, website: str
) -> tuple[Track, str] | None:
    node = page.select_one("[data-tralbum]")
    if node is None:
        raise ValueError(f"Bandcamp audio metadata not found: {url}")

    data = json.loads(node["data-tralbum"])
    current = data["current"]
    if current["type"] != "track" or len(data["trackinfo"]) != 1:
        raise ValueError(f"Expected a single Bandcamp track: {url}")

    licenses = {parse_license(str(anchor["href"])) for anchor in page.select("#license a[href]")}
    if len(licenses) != 1 or None in licenses:
        return None

    license = licenses.pop()
    info = data["trackinfo"][0]
    stream = (info.get("file") or {}).get("mp3-128")
    if not stream or info.get("private") or info.get("unreleased_track") or info.get("is_capped"):
        return None

    if urlsplit(stream).hostname is None or not urlsplit(stream).hostname.endswith(".bcbits.com"):
        raise ValueError(f"Unexpected Bandcamp stream host: {url}")

    creator = artist or info.get("artist") or data.get("artist", "")
    track = licensed_track(
        source,
        str(info["track_id"]),
        info["title"],
        creator,
        url,
        url,
        license[1],
    )
    track["duration"] = info.get("duration")
    track["isrc"] = current.get("isrc") or None

    published = current.get("publish_date")
    if published:
        track["uploaded"] = parsedate_to_datetime(published).date()

    tags = [tag.get_text(" ", strip=True) for tag in page.select("a.tag")]
    track["tags"] = sorted(set(tags))

    about = page.select_one(".tralbum-about")
    track["description"] = about.get_text("\n", strip=True) if about else ""

    album = page.select_one(".albumTitle a[href]")
    collections = []
    if album:
        collections.append(
            {"name": album.get_text(strip=True), "url": urljoin(url, str(album["href"]))}
        )

    track["attribution"] = attribution(track, website or urlsplit(url)._replace(path="").geturl())
    track["metadata"] = {"license_source": url, "collections": collections}

    return track, stream


def crawl(
    url: str,
    source: str,
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
    artist: str = "",
    website: str = "",
) -> list[Track]:
    validate_options(duration, limit)

    if not (urlsplit(url).hostname or "").endswith(".bandcamp.com"):
        raise ValueError("Bandcamp sources need an artist, album, or track URL.")

    tracks = []
    seen_ids = set()
    seen_recordings = {}
    skipped = 0

    with CachedHTTP(cache / source) as http:
        age = 0 if refresh else 86400
        robots = read_robots(http, url, age)

        def read_page(link: str, max_age: float = age) -> BeautifulSoup:
            if not robots.can_fetch(USER_AGENT, link):
                raise ValueError(f"Bandcamp robots.txt disallows {link}")

            return BeautifulSoup(http.get(link, max_age).read_text(), "html.parser")

        for release in discover(read_page(url), url):
            page = read_page(release)
            node = page.select_one("[data-tralbum]")
            if node is None:
                raise ValueError(f"Bandcamp audio metadata not found: {release}")

            data = json.loads(node["data-tralbum"])
            if data["current"]["type"] == "track":
                links = [release]
            else:
                links = []
                for info in data["trackinfo"]:
                    if not info.get("title_link"):
                        raise ValueError(f"Bandcamp track link is missing: {release}")

                    links.append(urljoin(release, info["title_link"]))

            for link in links:
                if urlsplit(link).hostname != urlsplit(url).hostname:
                    raise ValueError(f"Unexpected Bandcamp track: {link}")

                result = map_track(read_page(link), link, source, artist, website)
                if result is None:
                    skipped += 1
                    continue

                track, stream = result
                if track["id"] in seen_ids:
                    continue

                seen_ids.add(track["id"])
                print(f"[{len(tracks) + 1}] {track['title']}", file=sys.stderr)

                try:
                    audio = get_audio(http, track, stream)
                except httpx.HTTPStatusError as error:
                    if error.response.status_code not in (401, 403):
                        raise

                    # Cached HTML can outlive its stream token.
                    result = map_track(read_page(link, 0), link, source, artist, website)
                    if result is None or result[0]["id"] != track["id"]:
                        raise ValueError(f"Bandcamp track changed while refreshing audio: {link}")

                    track, stream = result
                    audio = get_audio(http, track, stream)

                recording_id = track["isrc"] or sha256(audio)

                # Compilation uploads may have new platform IDs for identical recordings.
                duplicate = seen_recordings.get(recording_id)
                if duplicate:
                    if duplicate["license"] != track["license"]:
                        raise ValueError(
                            f"Conflicting Bandcamp licenses for identical audio: {link}"
                        )

                    duplicate["metadata"]["collections"].extend(track["metadata"]["collections"])
                    continue

                # Stream URLs end in numeric IDs, so name the archived audio explicitly.
                prepare_preview(track, audio, previews, http.cache, duration, extension=".mp3")
                seen_recordings[recording_id] = track
                tracks.append(track)

                if limit is not None and len(tracks) >= limit:
                    return tracks

    if skipped:
        print(f"Skipped {skipped} ineligible Bandcamp tracks.", file=sys.stderr)

    if not tracks:
        raise ValueError(f"No qualifying Bandcamp tracks found: {url}")

    return tracks
