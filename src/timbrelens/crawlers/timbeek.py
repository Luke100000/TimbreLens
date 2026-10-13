import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from bs4 import BeautifulSoup

from timbrelens.crawlers.common import (
    get_audio,
    licensed_track,
    parse_license,
    prepare_preview,
    read_robots,
    validate_options,
)
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

BASE = "https://timbeek.com/"
LIBRARY = BASE + "royalty-free-music"
FAQ = BASE + "q-and-a"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
AUDIO_BASE = "https://timbeek-r2-preview.tim-beek666.workers.dev/"


def map_track(item: dict) -> Track | None:
    if item["licenseOffering"] != "cc_and_premium" or not item.get("previewUrl"):
        return None

    audio_url = item["previewUrl"]
    parts = urlsplit(audio_url)
    # Both public CC stream paths contain full audio; paid previews are separate.
    full_audio = parts.path.startswith(f"/cc-downloads/{item['id']}/") or re.fullmatch(
        r"/tracks/[^/]+/versions/[^/]+/legacy-preview/[^/]+\.mp3", parts.path
    )
    if (
        parts.scheme != "https"
        or parts.netloc != urlsplit(AUDIO_BASE).netloc
        or not parts.path.endswith(".mp3")
        or not full_audio
    ):
        return None

    duration = item["durationMs"] / 1000
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Invalid Tim Beek track duration: {item['id']}")

    track = licensed_track(
        "timbeek",
        item["id"],
        item["title"],
        "Tim Beek",
        LIBRARY + "/" + quote(item["slug"], safe=""),
        audio_url,
        LICENSE,
    )
    track["duration"] = duration
    track["genres"] = sorted({genre["name"] for genre in item["genres"]})
    track["moods"] = sorted({mood["name"] for mood in item["moods"]})
    track["tags"] = sorted(set(track["genres"] + track["moods"]))
    track["metadata"] = {
        "creator_url": BASE,
        "license_source": FAQ,
        "license_offering": item["licenseOffering"],
        "loopable": item["isLoopable"],
        "pack": item.get("pack"),
    }

    return track


def crawl(
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> list[Track]:
    validate_options(duration, limit)

    with CachedHTTP(cache / "timbeek") as http:
        age = 0 if refresh else 86400
        robots = read_robots(http, BASE, age)
        if not robots.can_fetch(USER_AGENT, FAQ):
            raise ValueError(f"Tim Beek robots.txt disallows {FAQ}")

        faq = BeautifulSoup(http.get(FAQ, age).read_text(), "html.parser")
        licenses = {parse_license(str(link["href"])) for link in faq.select("a[href]")}
        if ("CC-BY-4.0", LICENSE) not in licenses:
            raise ValueError("Tim Beek's CC BY 4.0 declaration is missing.")

        tracks = {}
        cursor = ""
        cursors = set()

        # The public API uses opaque cursors, not numbered HTML pages.
        while True:
            if cursor in cursors:
                raise ValueError("Tim Beek track index repeats a pagination cursor.")

            cursors.add(cursor)
            query = {"license": "cc"}
            if cursor:
                query["cursor"] = cursor

            url = BASE + "api/v1/tracks?" + urlencode(query)
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError(f"Tim Beek robots.txt disallows {url}")

            data = json.loads(http.get(url, age).read_text())
            if not isinstance(data.get("items"), list) or "nextCursor" not in data:
                raise ValueError("Tim Beek track index is incomplete.")

            for item in data["items"]:
                track = map_track(item)
                if track is None:
                    continue

                existing = tracks.get(track["id"])
                if existing is not None and existing != track:
                    raise ValueError(f"Conflicting Tim Beek track ID: {track['id']}")

                tracks[track["id"]] = track
                if limit is not None and len(tracks) >= limit:
                    break

            cursor = data["nextCursor"]
            if cursor is not None and (not isinstance(cursor, str) or not cursor):
                raise ValueError("Invalid Tim Beek pagination cursor.")

            if cursor is None or (limit is not None and len(tracks) >= limit):
                break

            if not data["items"]:
                raise ValueError("Tim Beek track index has an empty intermediate page.")

        if not tracks:
            raise ValueError("No qualifying Tim Beek tracks found.")

        audio_robots = read_robots(http, AUDIO_BASE, age)
        for index, track in enumerate(tracks.values(), 1):
            url = track["source_url"]
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError(f"Tim Beek robots.txt disallows {url}")

            page = BeautifulSoup(http.get(url, age).read_text(), "html.parser")
            title = page.select_one("main h1")
            license_label = page.find("dt", string="License")
            license_value = license_label.find_next_sibling("dd") if license_label else None
            if (
                title is None
                or title.get_text(strip=True) != track["title"]
                or license_value is None
                or license_value.get_text(strip=True) != "Creative Commons"
            ):
                raise ValueError(f"Tim Beek track page no longer confirms its CC license: {url}")

            description = page.select_one("main .page-head .lead")
            if description:
                track["description"] = description.get_text(" ", strip=True)

            if not audio_robots.can_fetch(USER_AGENT, track["audio_url"]):
                raise ValueError(f"Tim Beek audio robots.txt disallows {track['audio_url']}")

            print(f"[{index}/{len(tracks)}] {track['title']}", file=sys.stderr)
            audio = get_audio(http, track)
            prepare_preview(track, audio, previews, http.cache, duration)

    return list(tracks.values())
