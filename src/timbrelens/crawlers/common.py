import math
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from diskcache import Cache

from timbrelens import audio_metadata, fallbacks, originals
from timbrelens.audio import preview
from timbrelens.http import CachedHTTP
from timbrelens.models import Track


def parse_license(url: str) -> tuple[str, str] | None:
    parts = urlsplit(url if "://" in url else "https://" + url)
    if parts.hostname not in {"creativecommons.org", "www.creativecommons.org"}:
        return None

    if parts.path.rstrip("/") == "/publicdomain/zero/1.0":
        return "CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/"

    match = re.fullmatch(
        r"/licenses/by/(\d\.\d)(?:/(?:deed|legalcode)(?:\.[\w-]+)?)?/?", parts.path
    )
    if match:
        version = match[1]
        return f"CC-BY-{version}", f"https://creativecommons.org/licenses/by/{version}/"

    return None


def attribution(track: Track, creator_url: str) -> str:
    if not track["license"].startswith("CC-BY-"):
        return ""

    version = track["license"].removeprefix("CC-BY-")
    return (
        f'Title: "{track["title"]}"\nArtist: {track["artist"]} ({creator_url})\n'
        f"Licensed under Creative Commons By Attribution {version}\n{track['license_url']}"
    )


def licensed_track(
    source: str,
    source_id: str,
    title: str,
    artist: str,
    source_url: str,
    audio_url: str,
    license_url: str,
) -> Track:
    license = parse_license(license_url)
    if license is None:
        raise ValueError(f"Unsupported license: {license_url}")

    track: Track = {
        "id": f"{source}:{source_id}",
        "source": source,
        "source_id": source_id,
        "source_url": source_url,
        "audio_url": audio_url,
        "title": title.strip(),
        "artist": artist.strip(),
        "composer": "",
        "copyright_holder": "",
        "description": "",
        "tags": [],
        "genres": [],
        "moods": [],
        "instruments": [],
        "isrc": None,
        "uploaded": None,
        "duration": None,
        "bpm": None,
        "license": license[0],
        "license_url": license[1],
        "attribution": "",
        "metadata": {},
    }
    track["attribution"] = attribution(track, source_url)

    return track


def read_robots(http: CachedHTTP, base: str, age: float) -> RobotFileParser:
    robots = RobotFileParser()
    url = urljoin(base, "/robots.txt")
    missing_key = f"missing-robots:{url}"
    if age and http.cache.get(missing_key):
        robots.parse([])
        return robots

    try:
        content = http.get(url, age).read_text()
        http.cache.delete(missing_key)
    except httpx.HTTPStatusError as error:
        if error.response.status_code not in (404, 410):
            raise

        # Cache absent robots files as well as successful downloads.
        http.cache.set(missing_key, True, expire=age or 86400)
        content = ""

    robots.parse(content.splitlines())
    return robots


def validate_options(duration: float, limit: int | None) -> None:
    if limit is not None and limit <= 0:
        raise ValueError("Track limit must be positive.")

    if not math.isfinite(duration) or duration < 0.001:
        raise ValueError("Preview duration must be finite and at least 0.001 seconds.")


def get_audio(
    http: CachedHTTP,
    track: Track,
    url: str | None = None,
) -> Path:
    return http.get(url or track["audio_url"], None, cache_key=f"audio:{track['id']}")


def prepare_previews(
    tracks: list[Track],
    http: CachedHTTP,
    previews: Path,
    duration: float,
    extension: str | None = None,
) -> None:
    for index, track in enumerate(tracks, 1):
        title = track["title"] or unquote(Path(urlsplit(track["audio_url"]).path).stem)
        print(f"[{index}/{len(tracks)}] {title}", file=sys.stderr)
        audio = get_audio(http, track)
        prepare_preview(track, audio, previews, http.cache, duration, extension)


def prepare_preview(
    track: Track,
    audio: Path,
    previews: Path,
    cache: Cache,
    duration: float,
    extension: str | None = None,
) -> None:
    # Fill the title from audio tags before generating missing credits.
    changed = audio_metadata.fill_missing(
        track, audio, fallbacks.load(previews.parent / "catalog-fallback.json")
    )

    if not track["attribution"] or (changed & {"title", "artist"} and "attribution" not in changed):
        creator_url = track["metadata"].get("creator_url") or track["source_url"]
        track["attribution"] = attribution(track, creator_url)

    originals.save(track, audio, previews.parent / "originals", extension)
    track["preview"] = preview(audio, previews, cache, duration)
