# TimbreLens

Static music search with an offline Python pipeline.

## Setup

Requires Python 3.13+, [uv](https://docs.astral.sh/uv/), FFmpeg/ffprobe, and Node.js 20+. Run commands from the repo
root. `uv sync` installs [yt-dlp](https://github.com/yt-dlp/yt-dlp) and the other Python dependencies.

```sh
uv sync
npm ci
```

Set `OPENROUTER_API_KEY` in `.env` or the environment for enrichment. Override the default `google/gemini-3.8-flash`
model with `--model` or `OPENROUTER_AUDIO_MODEL`.

## Commands

```sh
uv run timbrelens sync
uv run timbrelens enrich
uv run timbrelens embed
uv run timbrelens export
uv run timbrelens serve
```

The local site is at http://127.0.0.1:8000. To crawl individual sources instead of `sync`:

```sh
uv run timbrelens crawl incompetech --limit 2
uv run timbrelens crawl creatorchords
uv run timbrelens crawl silverman
uv run timbrelens crawl freepd
uv run timbrelens crawl timkulig
```

Other tools:

```sh
uv run timbrelens evaluate
uv run timbrelens normalize .cache/track.mp3 .cache/normalized.wav
uv run timbrelens --help
```

`evaluate` writes model comparisons to `evaluation.md`.

## GitHub Pages

Pushes to `main` run the [Pages workflow](.github/workflows/pages.yml), which exports and deploys `dist/`. Prepare the
catalog, previews, and embeddings locally and include them in the checkout. Originals stay local.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
```
