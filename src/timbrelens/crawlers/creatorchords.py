import math
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from timbrelens.crawlers.common import (
    licensed_track,
    prepare_previews,
    read_robots,
    validate_options,
)
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

BASE = "https://creatorchords.com/"
LIBRARY = BASE + "music/"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
ARTIST = "Alexander Nakarada"


def map_track(row: Tag) -> Track:
    source_id = str(row["data-id"])
    title = str(row["data-title"]).strip()
    link = row.select_one("a.tr-name")
    if link is None:
        raise ValueError(f"Missing CreatorChords track link: {title}")

    genres = set()
    moods = set()
    for tag in row.select("a.tr-tag[href]"):
        query = parse_qs(urlsplit(str(tag["href"])).query)
        genres.update(query.get("genre", []))
        moods.update(query.get("mood", []))

    duration = 0
    for part in str(row["data-dur"]).split(":"):
        duration = duration * 60 + int(part)

    bpm = float(row["data-bpm"]) if row["data-bpm"] else None
    if bpm is not None and (not math.isfinite(bpm) or bpm <= 0):
        bpm = None

    track = licensed_track(
        "creatorchords",
        source_id,
        title,
        ARTIST,
        urljoin(BASE, str(link["href"])),
        urljoin(BASE, str(row["data-src"])),
        LICENSE,
    )
    track.update(
        {
            "composer": ARTIST,
            "copyright_holder": ARTIST,
            "tags": sorted(genres | moods),
            "genres": sorted(genres),
            "moods": sorted(moods),
            "duration": duration,
            "bpm": bpm,
            "attribution": (
                f"Music: {title} by {ARTIST} (https://creatorchords.com)\n"
                "Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0)\n"
                f"{LICENSE}"
            ),
            "metadata": {
                "id": source_id,
                "title": title,
                "bpm": str(row["data-bpm"]),
                "duration": str(row["data-dur"]),
                "genres": sorted(genres),
                "moods": sorted(moods),
            },
        }
    )

    return track


def catalog(http: CachedHTTP, refresh: bool = False) -> list[Track]:
    age = 0 if refresh else 86400
    robots = read_robots(http, BASE, age)

    tracks = []
    seen = set()
    pages = set()
    url = LIBRARY
    while url:
        if url in pages or urlsplit(url).hostname != urlsplit(BASE).hostname:
            raise ValueError(f"Invalid CreatorChords pagination link: {url}")

        pages.add(url)
        if not robots.can_fetch(USER_AGENT, url):
            raise ValueError(f"CreatorChords robots.txt disallows {url}")

        page = BeautifulSoup(http.get(url, age).read_text(encoding="utf-8"), "html.parser")
        rows = page.select(".track[data-id]")
        if not rows:
            raise ValueError(f"No CreatorChords tracks found at {url}")

        # Track metadata is in the index, so we can skip detail pages.
        for row in rows:
            track = map_track(row)
            if track["id"] in seen:
                raise ValueError(f"Repeated CreatorChords track: {track['id']}")

            seen.add(track["id"])
            tracks.append(track)

        more = page.select_one(".load-more-btn[hx-get]")
        url = urljoin(url, str(more["hx-get"])) if more else ""

    return sorted(tracks, key=lambda track: track["id"])


def crawl(
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> list[Track]:
    validate_options(duration, limit)

    with CachedHTTP(cache / "creatorchords") as http:
        tracks = catalog(http, refresh)[:limit]

        prepare_previews(tracks, http, previews, duration)

    return tracks
