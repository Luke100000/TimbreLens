import filecmp
import re
import shutil
from pathlib import Path

from timbrelens import state as catalog_state
from timbrelens.files import atomic_output
from timbrelens.models import Track


def save(track: Track, audio: Path, output: Path, extension: str | None = None) -> Path:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", track["title"]).strip(" .")
    title = title.encode("utf-8")[:160].decode("utf-8", errors="ignore") or "Untitled"
    directory = output / track["source"]
    name = title
    number = 1

    while True:
        target = directory / (name + (extension or audio.suffix))
        metadata = directory / (name + ".json")
        if metadata.is_file():
            archived = catalog_state.load(metadata)["tracks"][0]
            if archived["id"] == track["id"]:
                break
        elif not target.exists():
            break

        number += 1
        name = f"{title} ({number})"

    if not target.is_file() or not filecmp.cmp(audio, target, shallow=False):
        with atomic_output(target) as temporary:
            shutil.copyfile(audio, temporary)

    source = {key: value for key, value in track.items() if key not in ("preview", "enrichment")}
    catalog_state.save({"schema_version": 1, "tracks": [source]}, metadata)
    return target
