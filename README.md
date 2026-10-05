# TimbreLens

Static music search with an offline Python pipeline.

## Setup

Python 3.13+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run timbrelens --help
```

Install FFmpeg and ffprobe for audio processing. Run commands from the repo root.

## Commands

```sh
uv run timbrelens crawl incompetech --limit 2
uv run timbrelens sync
uv run timbrelens normalize .cache/track.mp3 .cache/normalized.wav
uv run timbrelens serve
uv run timbrelens enrich --model AUDIO_MODEL_ID
uv run timbrelens embed --text-model TEXT_MODEL_ID --audio-model CLAP_MODEL_ID
uv run timbrelens export --output dist
```

## GitHub Pages

Pushes to `main` trigger the [workflow](.github/workflows/pages.yml): export
`dist/`, upload it as an Actions artifact, and deploy that artifact to Pages. Crawling, enrichment, and embedding
generation run locally.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
```
