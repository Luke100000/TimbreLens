from datetime import date
from typing import NotRequired, TypedDict


class Enrichment(TypedDict):
    summary: str
    genres: list[str]
    moods: list[str]
    instruments: list[str]
    texture: list[str]
    model: str
    input_sha256: str


class Preview(TypedDict):
    start: float
    duration: float
    sha256: str
    source_sha256: str


class Track(TypedDict):
    id: str
    source: str
    source_id: str
    source_url: str
    audio_url: str
    title: str
    artist: str
    composer: str
    copyright_holder: str
    description: str
    tags: list[str]
    genres: list[str]
    moods: list[str]
    instruments: list[str]
    isrc: str | None
    uploaded: date | None
    duration: float | None
    bpm: float | None
    license: str
    license_url: str
    attribution: str
    metadata: dict[str, object]
    preview: NotRequired[Preview]
    enrichment: NotRequired[Enrichment]
    duplicates: NotRequired[list["Track"]]


class Catalog(TypedDict):
    schema_version: int
    tracks: list[Track]
