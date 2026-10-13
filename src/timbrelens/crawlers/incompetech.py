import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlencode

from timbrelens.crawlers.common import licensed_track, prepare_previews, validate_options
from timbrelens.http import CachedHTTP
from timbrelens.models import Track

BASE = "https://incompetech.com/music/royalty-free/"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"


def _terms(value: str | None) -> list[str]:
    return sorted({term.strip() for term in (value or "").split(",") if term.strip()})


def map_track(piece: dict, genres: dict[str, str], collections: dict[str, str]) -> Track:
    source_id = str(piece.get("isrc") or piece.get("uuid") or piece["filename"])
    filename = str(piece["filename"])
    title = str(piece["title"]).strip()
    length = piece.get("length")
    duration = None
    if length:
        parts = [int(part) for part in str(length).split(":")]
        if len(parts) not in (2, 3) or any(part < 0 for part in parts):
            raise ValueError(f"Invalid duration for {title}: {length}")

        duration = 0
        for part in parts:
            duration = duration * 60 + part

    bpm = float(piece["bpm"]) if piece.get("bpm") else None
    if bpm is not None and (not math.isfinite(bpm) or bpm <= 0):
        bpm = None

    genre = [genres[str(piece["genre"])]] if piece.get("genre") else []
    collection = [collections[str(piece["collection"])]] if piece.get("collection") else []
    moods = _terms(piece.get("feel"))
    instruments = _terms(piece.get("instruments"))
    source_url = (
        BASE + "index.html?" + urlencode({"isrc": piece.get("isrc")}) if piece.get("isrc") else BASE
    )

    track = licensed_track(
        "incompetech",
        source_id,
        title,
        "Kevin MacLeod",
        source_url,
        BASE + "mp3-royaltyfree/" + quote(filename, safe=""),
        LICENSE,
    )
    track.update(
        {
            "composer": "Kevin MacLeod",
            "copyright_holder": "Kevin MacLeod",
            "description": (piece.get("description") or "").strip(),
            "tags": sorted(set(genre + collection + moods + instruments)),
            "genres": genre,
            "moods": moods,
            "instruments": instruments,
            "isrc": piece.get("isrc") or None,
            "uploaded": date.fromisoformat(piece["uploaded"]) if piece.get("uploaded") else None,
            "duration": duration,
            "bpm": bpm,
            "attribution": (
                f'"{title}" Kevin MacLeod (incompetech.com)\n'
                f"Licensed under Creative Commons: By Attribution 4.0 License\n{LICENSE}"
            ),
            "metadata": dict(piece),
        }
    )

    return track


def crawl(
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> list[Track]:
    validate_options(duration, limit)

    with CachedHTTP(cache / "incompetech") as http:
        age = 0 if refresh else 86400
        pieces = json.loads(http.get(BASE + "pieces.json", age).read_text(encoding="utf-8-sig"))
        genres = {
            str(row["id"]): row["genre"]
            for row in json.loads(
                http.get(BASE + "genre.json", age).read_text(encoding="utf-8-sig")
            )
        }
        collections = {
            str(row["code"]): row["collection_name"]
            for row in json.loads(
                http.get(BASE + "collections.json", age).read_text(encoding="utf-8-sig")
            )
        }
        tracks = sorted(
            [map_track(piece, genres, collections) for piece in pieces],
            key=lambda track: track["id"],
        )

        if len({track["id"] for track in tracks}) != len(tracks):
            raise ValueError("Incompetech returned duplicate track IDs.")

        tracks = tracks[:limit]

        prepare_previews(tracks, http, previews, duration)

    return tracks
