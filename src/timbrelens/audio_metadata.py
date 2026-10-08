import json
import math
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from timbrelens.models import Track


def _number(value: str | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isfinite(number) and number > 0:
        return number
    return None


def read_metadata(input: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "format=duration:format_tags:stream=duration:stream_tags",
            "-of",
            "json",
            str(input.resolve()),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"ffprobe failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    format = data.get("format", {})
    stream = next(iter(data.get("streams", [])), {})
    tags = {
        key.lower(): value.strip()
        for key, value in {**stream.get("tags", {}), **format.get("tags", {})}.items()
    }

    metadata = {
        "title": tags.get("title", ""),
        "artist": tags.get("artist", ""),
        "composer": tags.get("composer") or tags.get("tcom") or tags.get("tcm", ""),
        "copyright_holder": tags.get("copyright", ""),
        "description": tags.get("description") or tags.get("comment", ""),
        "duration": _number(format.get("duration")) or _number(stream.get("duration")),
        "bpm": _number(tags.get("bpm") or tags.get("tbpm")),
        "isrc": tags.get("isrc") or tags.get("tsrc") or None,
        "audio_tags": tags,
    }

    for field, tag in (("genres", "genre"), ("moods", "mood"), ("instruments", "instruments")):
        metadata[field] = sorted(
            {value.strip() for value in re.split(r"[;,]", tags.get(tag, "")) if value.strip()}
        )

    metadata["tags"] = sorted(
        set(metadata["genres"] + metadata["moods"] + metadata["instruments"])
        | {value.strip() for value in tags.get("keywords", "").split(";") if value.strip()}
    )

    return metadata


def fill_missing(track: Track, input: Path) -> None:
    metadata = read_metadata(input)
    track["metadata"]["audio_tags"] = metadata.pop("audio_tags")

    # Source metadata takes precedence over embedded tags.
    for field, value in metadata.items():
        if not track[field] and value:
            track[field] = value

    if not track["title"]:
        track["title"] = unquote(Path(urlsplit(track["audio_url"]).path).stem)
