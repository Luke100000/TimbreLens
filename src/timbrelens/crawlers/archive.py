import json
import math
import re
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from timbrelens.crawlers.common import (
    attribution,
    licensed_track,
    parse_license,
    prepare_previews,
    read_robots,
    validate_options,
)
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

BASE = "https://archive.org/"
FORMATS = (".mp3", ".ogg", ".flac", ".wav", ".m4a", ".opus", ".aac", ".aiff")


def map_tracks(data: dict, identifier: str, source: str, artist: str, website: str) -> list[Track]:
    metadata = data["metadata"]
    license = parse_license(metadata.get("licenseurl", ""))
    if license is None:
        raise ValueError(f"Archive collection has no supported license: {identifier}")

    source_url = BASE + "details/" + quote(identifier, safe="")
    creator = artist or metadata.get("creator", "")
    if isinstance(creator, list):
        creator = ", ".join(creator)

    subjects = metadata.get("subject", [])
    if isinstance(subjects, str):
        subjects = [subjects]
    tags = sorted(
        {term.strip() for subject in subjects for term in re.split("[;,]", subject) if term.strip()}
    )

    files = {entry["name"]: entry for entry in data["files"]}
    candidates = [
        entry
        for entry in files.values()
        if PurePosixPath(entry["name"]).suffix.lower() in FORMATS and not entry.get("private")
    ]
    candidates.sort(
        key=lambda entry: (
            FORMATS.index(PurePosixPath(entry["name"]).suffix.lower()),
            entry["name"],
        )
    )

    # Prefer a playable MP3 over its FLAC original or other derived copies.
    tracks = {}
    for entry in candidates:
        original = entry.get("original") or entry["name"]
        if original not in files:
            raise ValueError(f"Archive derivative has no original: {entry['name']}")

        source_id = str(PurePosixPath(original).with_suffix(""))
        if source_id in tracks:
            continue

        audio_url = (
            BASE + "download/" + quote(identifier, safe="") + "/" + quote(entry["name"], safe="/")
        )
        track = licensed_track(
            source,
            source_id,
            entry.get("title") or PurePosixPath(original).stem,
            creator,
            source_url,
            audio_url,
            license[1],
        )
        track["description"] = metadata.get("description", "")
        track["tags"] = tags[:]

        length = entry.get("length")
        if length:
            duration = 0.0
            for part in str(length).split(":"):
                duration = duration * 60 + float(part)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"Invalid Archive duration: {entry['name']}")
            track["duration"] = duration

        published = metadata.get("publicdate")
        if published:
            track["uploaded"] = date.fromisoformat(published[:10])

        track["attribution"] = attribution(track, website or source_url)
        track["metadata"] = {
            "identifier": identifier,
            "filename": entry["name"],
            "original": original,
            "license_source": source_url,
            "creator_url": website or source_url,
            "collections": [{"name": metadata.get("title", identifier), "url": source_url}],
        }
        tracks[source_id] = track

    if not tracks:
        raise ValueError(f"No audio files found in Archive collection: {identifier}")

    return sorted(tracks.values(), key=lambda track: track["id"])


def crawl(
    identifier: str,
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

    with CachedHTTP(cache / source) as http:
        age = 0 if refresh else 86400
        robots = read_robots(http, BASE, age)
        url = BASE + "metadata/" + quote(identifier, safe="")
        if not robots.can_fetch(USER_AGENT, url):
            raise ValueError(f"Archive robots.txt disallows {url}")

        data = json.loads(http.get(url, age).read_text())
        if data.get("is_dark") or data.get("metadata", {}).get("access-restricted-item"):
            raise ValueError(f"Archive collection is restricted: {identifier}")
        if len(data["files"]) != data["files_count"]:
            raise ValueError(f"Archive returned an incomplete file index: {identifier}")

        tracks = map_tracks(data, identifier, source, artist, website)[:limit]
        for track in tracks:
            if not robots.can_fetch(USER_AGENT, track["audio_url"]):
                raise ValueError(f"Archive robots.txt disallows {track['audio_url']}")

        prepare_previews(tracks, http, previews, duration, refresh)

    return tracks
