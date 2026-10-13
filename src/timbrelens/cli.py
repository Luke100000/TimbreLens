import sys
from pathlib import Path
from typing import Annotated, Literal

from cyclopts import App, Parameter
from httpx import HTTPError
from openai import OpenAIError

from timbrelens import audio, embeddings, enrichment, evaluation, pipeline, server
from timbrelens import export as page_export
from timbrelens.crawlers import CRAWLERS

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
):
    """Enrich track metadata through OpenRouter."""
    enrichment.enrich(state, model, cache, limit, reasoning_effort)


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
