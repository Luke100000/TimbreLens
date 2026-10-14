import sys
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from cyclopts import App, Parameter
from httpx import HTTPError
from openai import OpenAIError

from timbrelens import (
    audio,
    dedup,
    embeddings,
    enrichment,
    evaluation,
    fallbacks,
    labels,
    pipeline,
    server,
)
from timbrelens import export as page_export
from timbrelens import state as catalog_state
from timbrelens.crawlers import CRAWLERS
from timbrelens.crawlers.common import attribution

app = App(name="timbrelens", help="Offline audio catalog and static search.")


@app.command
def crawl(
    source: Annotated[str, Parameter(choices=CRAWLERS)] = "incompetech",
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache/crawlers"),
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
):
    """Fetch source audio, generate previews and signatures, and sync metadata."""
    pipeline.crawl(source, state, cache, duration, limit, refresh)


@app.command
def sync(
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache/crawlers"),
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
):
    """Run all crawlers, including preview preparation."""
    pipeline.sync(state, cache, duration, limit, refresh)


@app.command
def enrich(
    model: str | None = None,
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache"),
    limit: int | None = None,
    reasoning_effort: Literal["minimal", "none"] = "minimal",
    workers: int = 32,
):
    """Enrich track metadata through OpenRouter."""
    enrichment.enrich(state, model, cache, limit, reasoning_effort, workers)


@app.command
def evaluate():
    """Compare audio enrichment models and write evaluation.md."""
    evaluation.evaluate()


@app.command
def embed(
    text_model: str = embeddings.TEXT_MODEL,
    audio_model: str = embeddings.AUDIO_MODEL,
    state: Path = Path("data/catalog.json"),
    output: Path = Path("data/embeddings"),
    cache: Path = Path(".cache"),
    text_revision: str | None = None,
    audio_revision: str | None = None,
):
    """Generate text and CLAP embeddings."""
    embeddings.embed(state, output, text_model, audio_model, cache, text_revision, audio_revision)


@app.command
def export(
    state: Path = Path("data/catalog.json"),
    embeddings: Path = Path("data/embeddings"),
    site: Path = Path("site"),
    output: Path = Path("dist"),
):
    """Export the static page, search indexes, embeddings, and previews."""
    page_export.export(state=state, embeddings=embeddings, site=site, output=output)


@app.command
def tags(
    state: Path = Path("data/catalog.json"),
    field: Literal["tags", "genres", "moods", "instruments", "texture"] | None = None,
    mapped: bool = False,
):
    """Print every label and its track count, grouped by field."""
    aliases = labels.load_aliases() if mapped else {}
    tracks = [labels.track_labels(track, aliases) for track in catalog_state.load(state)["tracks"]]
    print("field\tcount\tlabel")
    for name in (field,) if field else labels.FIELDS:
        counts = Counter(value for track in tracks for value in track[name])
        for label, count in sorted(counts.items(), key=lambda item: (item[1], item[0])):
            print(f"{name}\t{count}\t{label}")


@app.command
def apply_fallbacks(
    state: Path = Path("data/catalog.json"),
):
    """Fill missing catalog fields from handwritten metadata without crawling."""
    values = fallbacks.load(state.parent / "catalog-fallback.json")
    catalog = catalog_state.load(state)
    updated = 0
    for record in catalog["tracks"]:
        changed = fallbacks.apply(record, values)
        if not changed:
            continue

        if changed & {"title", "artist"} and "attribution" not in changed:
            creator_url = record.get("metadata", {}).get("creator_url") or record["source_url"]
            record["attribution"] = attribution(record, creator_url)
        updated += 1

    if updated:
        catalog_state.save(catalog, state)

    print(f"Applied fallback metadata to {updated} source records.")


@app.command
def deduplicate(
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache/crawlers"),
):
    """Remove duplicate recordings using full original audio fingerprints."""
    catalog = catalog_state.load(state)
    merged = dedup.merge(catalog, state.parent / "originals", cache)
    catalog_state.save(merged, state)
    print(f"Deduplicated catalog: {len(merged['tracks'])} tracks.")


@app.command
def normalize(input: Path, output: Path):
    """Normalize a local audio file."""
    audio.normalize(input, output)


@app.command
def serve(
    site: Path = Path("dist"),
    data: Path = Path("dist/data"),
    host: str = "127.0.0.1",
    port: int = 8000,
):
    """Serve the page and data locally."""
    server.serve(site, data, host, port)


def main() -> None:
    try:
        app()
    except (OSError, ValueError, HTTPError, OpenAIError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
