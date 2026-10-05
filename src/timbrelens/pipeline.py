from pathlib import Path


def crawl(source: str, state: Path, cache: Path, previews: Path, duration: float = 20.0) -> None:
    raise NotImplementedError("Crawler execution and state synchronization are not implemented.")


def sync(state: Path, cache: Path, previews: Path, duration: float = 20.0) -> None:
    raise NotImplementedError("Full catalog synchronization is not implemented.")
