from pathlib import Path

from timbrelens import state as catalog_state
from timbrelens.crawlers import CRAWLERS


def crawl(
    source: str,
    state: Path,
    cache: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> None:
    catalog = catalog_state.load(state)
    tracks = CRAWLERS[source](cache, state.parent / "previews", duration, limit, refresh)
    catalog_state.save(catalog_state.merge(catalog, tracks), state)
    print(f"Synced {len(tracks)} tracks from {source} to {state}")


def sync(
    state: Path,
    cache: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> None:
    for source in sorted(CRAWLERS):
        crawl(source, state, cache, duration, limit, refresh)
