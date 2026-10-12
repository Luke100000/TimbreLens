from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from timbrelens.crawlers.common import (
    licensed_track,
    parse_license,
    prepare_previews,
    read_robots,
    validate_options,
)
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

BASE = "https://teknoaxe.com/"
HOME = BASE + "Home.php"


def track_links(page: BeautifulSoup, url: str) -> list[tuple[str, str, str]]:
    links = []

    for anchor in page.select("a[href]"):
        link = urljoin(url, str(anchor["href"]))
        parts = urlsplit(link)
        if parts.hostname != urlsplit(BASE).hostname or parts.path != "/Link_Code_3.php":
            continue

        query = parse_qs(parts.query)
        source_id = query.get("q", [""])[0]
        genre = query.get("genre", [""])[0]
        if not source_id.isdigit() or not genre:
            raise ValueError(f"Invalid TeknoAXE track link: {link}")

        canonical = BASE + "Link_Code_3.php?" + urlencode({"q": source_id, "genre": genre})
        links.append((source_id, genre, canonical))

    return links


def map_track(page: BeautifulSoup, source_id: str, genre: str, url: str) -> Track | None:
    title = page.select_one(".license_block .p1")
    licenses = page.select('.license_block a[rel="license"][href]')
    if title is None or not licenses:
        raise ValueError(f"Missing TeknoAXE track metadata: {url}")

    license = parse_license(str(licenses[0]["href"]))
    if license is None:
        return None

    download = page.select_one('a[href^="direct_download.php?"]')
    if download is None:
        raise ValueError(f"Missing TeknoAXE audio download: {url}")

    audio_url = urljoin(url, str(download["href"]))
    filename = parse_qs(urlsplit(audio_url).query).get("file", [""])[0]
    if not filename.lower().endswith(".mp3"):
        raise ValueError(f"Invalid TeknoAXE audio download: {url}")

    track = licensed_track(
        "teknoaxe",
        source_id,
        title.get_text(" ", strip=True),
        "Matthew Huffaker",
        url,
        audio_url,
        license[1],
    )
    track["genres"] = [genre.replace("_", " ")]
    track["tags"] = track["genres"][:]
    track["metadata"] = {"license_source": url, "filename": filename}

    return track


def crawl(
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> list[Track]:
    validate_options(duration, limit)

    with CachedHTTP(cache / "teknoaxe") as http:
        age = 0 if refresh else 86400
        robots = read_robots(http, BASE, age)
        if not robots.can_fetch(USER_AGENT, HOME):
            raise ValueError(f"TeknoAXE robots.txt disallows {HOME}")

        home = BeautifulSoup(http.get(HOME, age).read_text(), "html.parser")
        pending = track_links(home, HOME)
        if not pending:
            raise ValueError("TeknoAXE catalog links not found.")

        indexes = set()
        recordings = {}
        pages = {}

        # Each genre page contains its complete track index.
        for source_id, genre, url in pending:
            if genre in indexes:
                continue

            indexes.add(genre)
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError(f"TeknoAXE robots.txt disallows {url}")

            page = BeautifulSoup(http.get(url, age).read_text(), "html.parser")
            links = track_links(page, url)
            if not links:
                raise ValueError(f"TeknoAXE genre index is missing: {url}")

            pages[url] = page
            for linked_id, linked_genre, linked_url in links:
                recording = recordings.setdefault(linked_id, {"url": linked_url, "genres": set()})
                recording["genres"].add(linked_genre)
                if linked_genre not in indexes:
                    pending.append((linked_id, linked_genre, linked_url))

        tracks = []
        for source_id, recording in sorted(recordings.items(), key=lambda item: int(item[0])):
            url = recording["url"]
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError(f"TeknoAXE robots.txt disallows {url}")

            page = pages.get(url)
            if page is None:
                page = BeautifulSoup(http.get(url, age).read_text(), "html.parser")

            genre = parse_qs(urlsplit(url).query)["genre"][0]
            track = map_track(page, source_id, genre, url)
            if track is None:
                continue

            track["genres"] = sorted(genre.replace("_", " ") for genre in recording["genres"])
            track["tags"] = track["genres"][:]
            tracks.append(track)

            if limit is not None and len(tracks) >= limit:
                break

        if not tracks:
            raise ValueError("No qualifying TeknoAXE tracks found.")

        for track in tracks:
            if not robots.can_fetch(USER_AGENT, track["audio_url"]):
                raise ValueError(f"TeknoAXE robots.txt disallows {track['audio_url']}")

        # The .php download endpoint returns MP3 audio, not a PHP file.
        prepare_previews(tracks, http, previews, duration, refresh, extension=".mp3")

    return tracks
