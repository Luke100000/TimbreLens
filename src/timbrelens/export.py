import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from timbrelens import labels
from timbrelens.files import preview_path, sha256
from timbrelens.state import load

RUNNER = Path(__file__).with_name("export-runner.mjs")
SEARCH_VERSION = "7.2.0"
SEARCH_OPTIONS = {
    "fields": [
        "title",
        "artist",
        "description",
        "summary",
        "tags",
        "genres",
        "moods",
        "instruments",
        "texture",
    ],
    "searchOptions": {"boost": {"title": 3, "artist": 2}, "prefix": True, "fuzzy": 0.2},
}
DISPLAY_FIELDS = (
    "id",
    "source_url",
    "title",
    "artist",
    "description",
    "duration",
    "license",
    "license_url",
    "attribution",
)


def _public_track(track: dict, aliases: dict | None = None) -> dict:
    result = {field: track[field] for field in DISPLAY_FIELDS if field in track}
    enrichment = track.get("enrichment") or {}
    result["summary"] = enrichment.get("summary", "").strip()

    result.update(labels.track_labels(track, labels.load_aliases() if aliases is None else aliases))

    # Shuffle by track and label so repeated exports keep the same card order.
    display_labels = {label for field in labels.FIELDS for label in result[field]}
    result["display_tags"] = sorted(
        display_labels,
        key=lambda label: hashlib.sha256(f"{track['id']}\0{label}".encode()).digest(),
    )

    result["preview"] = {
        "sha256": track["preview"]["sha256"],
        "start": track["preview"]["start"],
        "duration": track["preview"]["duration"],
    }
    return result


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n",
        encoding="utf-8",
    )


def _build_index(tracks: list[dict], path: Path, runtime_version: str) -> None:
    documents = [
        {
            "id": track["id"],
            **{
                field: " ".join(track[field])
                if isinstance(track.get(field), list)
                else track.get(field, "")
                for field in SEARCH_OPTIONS["fields"]
            },
        }
        for track in tracks
    ]
    process = subprocess.run(
        ["node", str(RUNNER)],
        input=json.dumps(
            {
                "documents": documents,
                "options": SEARCH_OPTIONS,
                "version": SEARCH_VERSION,
                "runtime_version": runtime_version,
                "output": str(path),
            }
        ),
        text=True,
        capture_output=True,
    )

    if process.returncode:
        raise ValueError(f"Search export failed; run npm ci.\n{process.stderr.strip()}")


def export(state: Path, embeddings: Path, site: Path, output: Path) -> None:
    output = output.resolve()

    for source in (site, embeddings, state):
        source = source.resolve()

        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError("Export output must not overlap its input directories.")

    catalog_hash = sha256(state)
    tracks = sorted(load(state)["tracks"], key=lambda track: track["id"])
    alias_rules = labels.load_aliases()

    if not tracks:
        raise ValueError("No tracks to export; run a crawler first.")

    manifest = json.loads((embeddings / "manifest.json").read_text(encoding="utf-8"))

    if manifest.get("catalog_sha256") != catalog_hash or manifest.get("track_ids") != [
        track["id"] for track in tracks
    ]:
        raise ValueError("Embeddings are stale; run embed after updating the catalog.")

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".timbrelens-export-", dir=output.parent) as temporary:
        staging = Path(temporary) / "site"
        shutil.copytree(site, staging)
        (staging / ".nojekyll").touch()
        data = staging / "data"
        audio = data / "previews"
        audio.mkdir(parents=True)
        public = []

        for track in tracks:
            path = preview_path(track, state)

            destination = audio / path.name
            shutil.copyfile(path, destination)
            image_path = path.with_suffix(".png")
            shutil.copyfile(image_path, audio / image_path.name)
            public.append(_public_track(track, alias_rules))

        _write_json(data / "catalog.json", {"schema_version": 1, "tracks": public})
        _build_index(public, data / "minisearch.json", manifest["runtime_version"])
        exported = {
            "track_ids": manifest["track_ids"],
            "catalog": "catalog.json",
            "lexical": {
                "file": "minisearch.json",
                "options": SEARCH_OPTIONS,
            },
        }

        for kind in ("text", "audio"):
            exported[kind] = manifest[kind]

            for name in (manifest[kind]["file"], manifest[kind]["inverse_norms"]):
                shutil.copyfile(embeddings / name, data / name)

        _write_json(data / "manifest.json", exported)

        previous = Path(temporary) / "previous"

        if output.exists():
            output.replace(previous)

        try:
            staging.replace(output)
        except OSError:
            if previous.exists():
                previous.replace(output)

            raise

    print(f"Exported {len(tracks)} tracks to {output}.")
