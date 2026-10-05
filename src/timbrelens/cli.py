import sys
from pathlib import Path
from typing import Literal

from cyclopts import App

from timbrelens import audio, embeddings, enrichment, pipeline
from timbrelens import export as page_export

app = App(name="timbrelens", help="Offline audio catalog and static search (scaffold).")


@app.command
def crawl(
    source: Literal["incompetech"] = "incompetech",
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache"),
    previews: Path = Path("audio-previews"),
    duration: float = 20.0,
):
    """Fetch and cache source audio, prepare previews, and sync metadata."""
    pipeline.crawl(source, state=state, cache=cache, previews=previews, duration=duration)


@app.command
def sync(
    state: Path = Path("data/catalog.json"),
    cache: Path = Path(".cache"),
    previews: Path = Path("audio-previews"),
    duration: float = 20.0,
):
    """Run all crawlers, including preview preparation."""
    pipeline.sync(state=state, cache=cache, previews=previews, duration=duration)


@app.command
def enrich(model: str, state: Path = Path("data/catalog.json")):
    """Enrich track metadata through OpenRouter."""
    enrichment.enrich(state=state, model=model)


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
    previews: Path = Path("audio-previews"),
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


def main() -> None:
    try:
        app()
    except NotImplementedError as error:
        print(f"Scaffold: {error}", file=sys.stderr)
        raise SystemExit(1) from None
