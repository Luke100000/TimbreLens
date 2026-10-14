import json
from datetime import date
from pathlib import Path

from timbrelens.files import atomic_output
from timbrelens.models import Catalog, Track


def load(path: Path) -> Catalog:
    if not path.exists():
        return {"schema_version": 1, "tracks": []}

    catalog = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != 1
        or not isinstance(catalog.get("tracks"), list)
    ):
        raise ValueError(f"Unsupported catalog format: {path}")

    records = catalog["tracks"]
    if any(
        not isinstance(track, dict) or not isinstance(track.get("id"), str) for track in records
    ):
        raise ValueError(f"Invalid track records: {path}")

    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate track IDs: {path}")

    for track in records:
        track.pop("duplicates", None)
        if track.get("uploaded"):
            track["uploaded"] = date.fromisoformat(track["uploaded"])

    return catalog


def _json_value(value):
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def save(catalog: Catalog, path: Path) -> None:
    tracks = []
    for track in sorted(catalog["tracks"], key=lambda track: track["id"]):
        track = dict(track)
        for field in ("tags", "genres", "moods", "instruments"):
            if field in track:
                track[field] = sorted(set(track[field]))
        if "enrichment" in track:
            track["enrichment"] = {
                key: sorted(set(value)) if isinstance(value, list) else value
                for key, value in track["enrichment"].items()
            }
        tracks.append(track)

    content = (
        json.dumps(
            {**catalog, "tracks": tracks},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
            default=_json_value,
        )
        + "\n"
    ).encode("utf-8")

    if path.exists() and path.read_bytes() == content:
        return

    with atomic_output(path) as temporary:
        temporary.write_bytes(content)


def merge(catalog: Catalog, tracks: list[Track]) -> Catalog:
    existing = {track["id"]: dict(track) for track in catalog["tracks"]}

    seen = set()
    for track in tracks:
        if track["id"] in seen:
            raise ValueError(f"Duplicate crawler track ID: {track['id']}")

        seen.add(track["id"])
        old = existing.get(track["id"])
        if old and "enrichment" in old and "enrichment" not in track:
            source_fields = (
                "title",
                "artist",
                "description",
                "tags",
                "genres",
                "moods",
                "instruments",
                "bpm",
                "duration",
            )
            same_audio = old.get("preview", {}).get("sha256") == track.get("preview", {}).get(
                "sha256"
            )
            if same_audio and all(old.get(field) == track.get(field) for field in source_fields):
                track = {**track, "enrichment": old["enrichment"]}

        existing[track["id"]] = dict(track)

    unique = []
    recordings = set()
    for track in sorted(existing.values(), key=lambda track: track["id"]):
        audio_hash = track.get("preview", {}).get("source_sha256")
        if audio_hash and audio_hash in recordings:
            continue

        unique.append(track)
        if audio_hash:
            recordings.add(audio_hash)

    return {"schema_version": 1, "tracks": unique}
