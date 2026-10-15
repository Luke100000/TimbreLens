import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from timbrelens.models import Catalog, Track


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def preview_path(track: Track, state: Path) -> Path:
    preview = track.get("preview")

    if not preview:
        raise ValueError(f"Missing preview for {track['id']}; run the crawler first.")

    return (state.parent / "previews" / f"{preview['sha256']}.mp3").resolve()


def prune_previews(catalog: Catalog, directory: Path) -> int:
    used = {track["preview"]["sha256"] for track in catalog["tracks"] if track.get("preview")}
    removed = 0
    for path in directory.glob("*"):
        if path.suffix in {".mp3", ".png"} and path.stem not in used and path.is_file():
            path.unlink()
            removed += 1

    return removed


@contextmanager
def atomic_output(path: Path) -> Iterator[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        yield temporary
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
