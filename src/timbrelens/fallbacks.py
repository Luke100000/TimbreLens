from pathlib import Path

from timbrelens import state


def load(path: Path) -> dict:
    return {track["id"]: track for track in state.load(path)["tracks"]}


def apply(track: dict, catalog: dict) -> set[str]:
    changed = set()
    for field, value in catalog.get(track["id"], {}).items():
        if field != "id" and value and not track.get(field):
            track[field] = value
            changed.add(field)

    return changed
