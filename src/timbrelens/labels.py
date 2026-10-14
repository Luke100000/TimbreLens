import json
from pathlib import Path

FIELDS = ("tags", "genres", "moods", "instruments", "texture")
DEFAULT_ALIASES = Path(__file__).with_name("label-aliases.json")


def load_aliases() -> dict:
    return json.loads(DEFAULT_ALIASES.read_text(encoding="utf-8"))


def track_labels(track: dict, aliases: dict) -> dict[str, list[str]]:
    enrichment = track.get("enrichment") or {}
    result = {}
    for field in FIELDS:
        rules = {**aliases.get("*", {}), **aliases.get(field, {})}
        values = {
            value.strip().casefold()
            for value in [*track.get(field, []), *enrichment.get(field, [])]
            if value.strip()
        }
        result[field] = sorted({rules.get(value, value) for value in values} - {""})

    return result
