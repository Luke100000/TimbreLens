from typing import NotRequired, TypedDict


class Enrichment(TypedDict):
    summary: str
    genres: list[str]
    moods: list[str]
    energy: list[str]
    tempo: list[str]
    instruments: list[str]
    vocals: list[str]
    useCases: list[str]
    texture: list[str]
    model: str
    prompt_version: str
    input_sha256: str


class Preview(TypedDict):
    path: str
    start_ms: int
    duration_ms: int
    source_sha256: str
    recipe_version: str
    sha256: str


class Track(TypedDict):
    id: str
    source: str
    source_id: str
    source_url: str
    audio_url: str
    title: str
    artist: str
    creator_id: str
    description: str
    tags: list[str]
    duration_ms: int | None
    bpm: float | None
    license: str
    license_url: str
    attribution: str
    download_allowed: bool | None
    ai_generated: bool | None
    metadata: dict[str, object]
    preview: NotRequired[Preview]
    enrichment: NotRequired[Enrichment]


class Catalog(TypedDict):
    schema_version: int
    tracks: list[Track]
