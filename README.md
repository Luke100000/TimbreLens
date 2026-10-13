# TimbreLens

**[Open TimbreLens](https://luke100000.github.io/TimbreLens/)** to search music by keywords, mood, instruments, or
similar tracks.

The [Music sources page](https://luke100000.github.io/TimbreLens/sources.html) lists collected artists and libraries,
plus larger external catalogs.

## Local setup

Requires Python 3.13+, [uv](https://docs.astral.sh/uv/), FFmpeg/ffprobe, and Node.js 20+. Run commands from the repo
root. `uv sync` installs [yt-dlp](https://github.com/yt-dlp/yt-dlp) and the other Python dependencies.

```sh
uv sync
npm ci
```

Set `OPENROUTER_API_KEY` in `.env` or the environment for enrichment. Override the default `xiaomi/mimo-v2.6-flash`
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
uv run timbrelens crawl freepd
...
```

SoundCloud crawls report and skip individual track extraction failures so the remaining tracks can finish.
Failure to load the artist's track index still stops the crawl.

Other tools:

```sh
uv run timbrelens evaluate
uv run timbrelens normalize .cache/track.mp3 .cache/normalized.wav
uv run timbrelens --help
```

`evaluate` writes model comparisons to `data/evaluation.md`.

Crawling groups byte-identical original audio into one catalog entry, keeping the other source records in
`duplicates`. The entry with the first ID alphabetically supplies the displayed metadata; each source's links, credits,
and license remain available in the catalog and local originals. Different encodings stay separate.

## GitHub Pages

Pushes to `master` run the [Pages workflow](.github/workflows/pages.yml), which exports and deploys the site.
Commit the catalog, previews and embeddings. Set the Pages source to **GitHub Actions**.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
```
