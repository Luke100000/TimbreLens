import sys
from pathlib import Path
from typing import Literal

from cyclopts import App
from httpx import HTTPError
from openai import OpenAIError

from timbrelens import audio, embeddings, enrichment, pipeline, server
from timbrelens import export as page_export

app = App(name="timbrelens", help="Offline audio catalog and static search.")


@app.command
def crawl(
    source: Literal["incompetech"] = "incompetech",
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache"),
    previews: Path = Path("data/audio-previews"),
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
):
    """Fetch and cache source audio, prepare previews, and sync metadata."""
    pipeline.crawl(source, state, cache, previews, duration, limit, refresh)


@app.command
def sync(
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache"),
    previews: Path = Path("data/audio-previews"),
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
):
    """Run all crawlers, including preview preparation."""
    pipeline.sync(state, cache, previews, duration, limit, refresh)


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
def embed(
    text_model: str,
    audio_model: str,
    state: Path = Path("data/catalog.json"),
    output: Path = Path("data/embeddings"),
):
    """Generate text and CLAP embeddings."""
    embeddings.embed(state=state, output=output, text_model=text_model, audio_model=audio_model)


@app.command
def export(
    state: Path = Path("data/catalog.json"),
    embeddings: Path = Path("data/embeddings"),
    site: Path = Path("site"),
    previews: Path = Path("data/audio-previews"),
    output: Path = Path("dist"),
):
    """Export the static page, search indexes, embeddings, and previews."""
    page_export.export(
        state=state, embeddings=embeddings, site=site, previews=previews, output=output
    )


@app.command
def normalize(input: Path, output: Path):
    """Normalize a local audio file."""
    audio.normalize(input, output)


@app.command
def serve(
    site: Path = Path("site"),
    data: Path = Path("data"),
    host: str = "127.0.0.1",
    port: int = 8000,
):
    """Serve the page and data locally."""
    server.serve(site, data, host, port)


def main() -> None:
    try:
        app()
    except NotImplementedError as error:
        print(f"Scaffold: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, HTTPError, OpenAIError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
