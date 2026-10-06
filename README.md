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
uv run timbrelens enrich --limit 1
uv run timbrelens embed
uv run timbrelens export --output dist
```

Enrichment reads `OPENROUTER_API_KEY` from the environment or `.env`. It defaults to `google/gemini-3.8-flash` with flex
and minimal reasoning; override with `--model`
or `OPENROUTER_AUDIO_MODEL`, and `--reasoning-effort none` when supported. Results are cached by all request inputs in
`.cache/enrichment/`.

Run `uv run timbrelens evaluate` to compare the configured models and tracks. It writes `evaluation.md` with reference
descriptions and labels, model predictions, and costs for review.

Embedding uses [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)
for metadata and [CLAP](https://huggingface.co/Xenova/clap-htsat-unfused) for previews.
Local generation needs Node.js 20+ and `npm ci`; query inference runs in the browser.

## GitHub Pages

Pushes to `main` trigger the [workflow](.github/workflows/pages.yml): export
`dist/`, upload it as an Actions artifact, and deploy that artifact to Pages. Crawling, enrichment, and embedding
generation run locally.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
```
