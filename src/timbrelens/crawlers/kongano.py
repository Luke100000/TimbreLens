from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from timbrelens.crawlers.common import (
    licensed_track,
    prepare_previews,
    read_robots,
    validate_options,
)
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

BASE = "https://kongano.com/"
LIBRARY = BASE + "?page_id=8"
FAQ = BASE + "?page_id=12"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"


def map_tracks(html: str, url: str, category: str) -> list[Track]:
    page = BeautifulSoup(html, "html.parser")
    tracks = []

    for audio in page.select(".entry-content audio"):
        link = audio.select_one("a[href]")
        download = audio.find_next_sibling("a", class_="dlm-download-link")
        description = audio.find_previous_sibling("p")
        heading = description.find_previous_sibling("p") if description else None
        if link is None or download is None or heading is None:
            raise ValueError(f"Missing Kongano track metadata: {url}")

        # Use the download ID rather than its timestamped URL as track identity.
        source_id = parse_qs(urlsplit(download["href"]).query).get("download", [""])[0]
        audio_url = urljoin(url, str(link["href"]))
        if not source_id.isdigit() or not urlsplit(audio_url).path.lower().endswith(".mp3"):
            raise ValueError(f"Invalid Kongano download: {url}")

        track = licensed_track(
            "kongano",
            source_id,
            heading.get_text(" ", strip=True),
            "Eino Toivanen",
            url,
            audio_url,
            LICENSE,
        )
        track["description"] = description.get_text(" ", strip=True)
        track["genres"] = [] if category in {"Mood", "Shorts", "Unique"} else [category]
        track["tags"] = [category]
        track["metadata"] = {
            "license_source": FAQ,
            "collections": [{"name": category, "url": url}],
        }
        tracks.append(track)

    if not tracks:
        raise ValueError(f"No Kongano tracks found: {url}")

    return tracks


def crawl(
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> list[Track]:
    validate_options(duration, limit)

    with CachedHTTP(cache / "kongano") as http:
        age = 0 if refresh else 86400
        robots = read_robots(http, BASE, age)

        for url in (LIBRARY, FAQ):
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError(f"Kongano robots.txt disallows {url}")

        faq = BeautifulSoup(http.get(FAQ, age).read_text(), "html.parser").get_text(" ", strip=True)
        if "By Attribution 4.0" not in faq:
            raise ValueError("Kongano's CC BY 4.0 declaration is missing.")

        page = BeautifulSoup(http.get(LIBRARY, age).read_text(), "html.parser")
        categories = page.select("#site-navigation .page-item-8 .children a[href]")
        if not categories:
            raise ValueError("Kongano music categories not found.")

        # Categories overlap, so merge their labels under the same download ID.
        tracks = {}
        for category in categories:
            url = urljoin(BASE, str(category["href"]))
            if urlsplit(url).hostname != urlsplit(BASE).hostname:
                raise ValueError(f"Unexpected Kongano category: {url}")

            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError(f"Kongano robots.txt disallows {url}")

            for track in map_tracks(
                http.get(url, age).read_text(), url, category.get_text(strip=True)
            ):
                existing = tracks.get(track["id"])
                if existing:
                    if existing["audio_url"] != track["audio_url"]:
                        raise ValueError(f"Conflicting Kongano download ID: {track['id']}")

                    existing["genres"] = sorted(set(existing["genres"] + track["genres"]))
                    existing["tags"] = sorted(set(existing["tags"] + track["tags"]))
                    existing["metadata"]["collections"].extend(track["metadata"]["collections"])
                else:
                    tracks[track["id"]] = track

        selected = sorted(tracks.values(), key=lambda track: track["id"])[:limit]
        for track in selected:
            if not robots.can_fetch(USER_AGENT, track["audio_url"]):
                raise ValueError(f"Kongano robots.txt disallows {track['audio_url']}")

        prepare_previews(selected, http, previews, duration, refresh)

    return selected
