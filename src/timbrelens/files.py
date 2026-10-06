import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from timbrelens.models import Track


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def preview_path(track: Track, state: Path) -> Path:
    preview = track.get("preview")

    if not preview:
        raise ValueError(f"Missing preview for {track['id']}; run the crawler first.")

    path = (state.parent / preview["path"]).resolve()

    if not path.is_relative_to(state.parent.resolve()) or path.suffix != ".mp3":
        raise ValueError(f"Invalid preview path for {track['id']}.")

    if sha256(path) != preview["sha256"]:
        raise ValueError(f"Preview checksum mismatch for {track['id']}; recrawl it.")

    return path


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
