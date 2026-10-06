import hashlib
import json
import math
import re
import subprocess
import sys
from array import array
from pathlib import Path

from diskcache import Cache

from timbrelens.audio import _ffmpeg_version
from timbrelens.files import atomic_output, preview_path, sha256
from timbrelens.http import CachedHTTP
from timbrelens.state import load

TEXT_MODEL = "Xenova/bge-small-en-v1.5"
AUDIO_MODEL = "Xenova/clap-htsat-unfused"
REVISIONS = {
    TEXT_MODEL: "ea104dacec62c0de699686887e3f920caeb4f3e3",
    AUDIO_MODEL: "c28f2883575e590e04d3146ff0713c2448d691ba",
}
RUNTIME_VERSION = "4.3.0"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RUNNER = Path(__file__).with_name("embedding-runner.mjs")


def document(track: dict) -> str:
    enrichment = track.get("enrichment") or {}
    lines = [
        track.get("title"),
        track.get("artist"),
        track.get("description"),
        enrichment.get("summary"),
    ]

    for field in ("genres", "moods", "instruments", "texture", "tags"):
        values = {
            value.strip().casefold()
            for value in [*track.get(field, []), *enrichment.get(field, [])]
            if value.strip()
        }

        if values:
            lines.append(f"{field}: {', '.join(sorted(values))}")

    return "\n".join(line.strip() for line in lines if line and line.strip())


def _revision(model: str, revision: str | None, cache: Path) -> str:
    if revision:
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Model revisions must be full commit hashes.")

        return revision

    if model in REVISIONS:
        return REVISIONS[model]

    with CachedHTTP(cache / "models") as http:
        return json.loads(http.get(f"https://huggingface.co/api/models/{model}").read_text())["sha"]


def _vector(values: list[float]) -> bytes:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("Invalid embedding vector.")

    norm = math.sqrt(math.fsum(value * value for value in values))

    if norm == 0:
        raise ValueError("Zero embedding vector.")

    vector = array("f", (value / norm for value in values))

    if sys.byteorder != "little":
        vector.byteswap()

    return vector.tobytes()


def _encode(tasks: list[dict], models: dict, cache: Path, store: Cache) -> None:
    with subprocess.Popen(
        ["node", str(RUNNER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as process:
        process.stdin.write(
            json.dumps(
                {
                    "tasks": tasks,
                    "models": models,
                    "cache": str((cache / "models").resolve()),
                    "runtime_version": RUNTIME_VERSION,
                }
            )
        )
        process.stdin.close()

        for line in process.stdout:
            result = json.loads(line)
            store[result["key"]] = _vector(result["vector"])

        if process.wait():
            raise ValueError("Embedding generation failed; completed vectors remain cached.")


def embed(
    state: Path,
    output: Path,
    text_model: str = TEXT_MODEL,
    audio_model: str = AUDIO_MODEL,
    cache: Path = Path(".cache"),
    text_revision: str | None = None,
    audio_revision: str | None = None,
) -> None:
    tracks = sorted(load(state)["tracks"], key=lambda track: track["id"])

    if not tracks:
        raise ValueError("No tracks to embed; run a crawler first.")

    catalog_hash = sha256(state)
    models = {
        "text": {
            "model": text_model,
            "revision": _revision(text_model, text_revision, cache),
            "dtype": "q8",
            "pooling": "cls",
            "query_prefix": QUERY_PREFIX if text_model == TEXT_MODEL else "",
        },
        "audio": {
            "model": audio_model,
            "revision": _revision(audio_model, audio_revision, cache),
            "dtype": "q8",
            "query_model_class": "ClapTextModelWithProjection",
            "query_prefix": "",
            "sample_rate": 48000,
            "window_seconds": 10,
            "aggregation": "duration_weighted_mean_of_normalized_windows",
        },
    }
    recipe = {"runtime_version": RUNTIME_VERSION, "runner_sha256": sha256(RUNNER)}
    tasks = {}
    keys = {"text": [], "audio": []}

    for track in tracks:
        path = preview_path(track, state)

        for kind, inputs in (
            ("text", {"text": document(track)}),
            ("audio", {"preview_sha256": track["preview"]["sha256"], "ffmpeg": _ffmpeg_version()}),
        ):
            key = hashlib.sha256(
                json.dumps(
                    {**recipe, "kind": kind, "model": models[kind], "inputs": inputs},
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            keys[kind].append(key)
            tasks[key] = {
                "key": key,
                "kind": kind,
                **({"text": inputs["text"]} if kind == "text" else {"path": str(path)}),
            }

    with Cache(str(cache / "embeddings")) as store:
        missing = [task for key, task in tasks.items() if key not in store]

        if missing:
            _encode(missing, models, cache, store)

        matrices = {}

        for kind, ordered_keys in keys.items():
            vectors = [store[key] for key in ordered_keys]
            dimensions = len(vectors[0]) // 4

            if not dimensions or any(len(vector) != dimensions * 4 for vector in vectors):
                raise ValueError(f"Inconsistent {kind} embedding dimensions.")

            matrices[kind] = b"".join(vectors)
            models[kind]["dimensions"] = dimensions

    if sha256(state) != catalog_hash:
        raise ValueError("Catalog changed while embedding; rerun to use the updated tracks.")

    for kind, content in matrices.items():
        digest = hashlib.sha256(content).hexdigest()
        filename = f"{kind}-{digest}.f32.bin"
        models[kind].update({"file": filename, "sha256": digest})
        target = output / filename

        if not target.exists() or target.read_bytes() != content:
            with atomic_output(target) as temporary:
                temporary.write_bytes(content)

    manifest = {
        "schema_version": 1,
        "catalog_sha256": catalog_hash,
        "track_ids": [track["id"] for track in tracks],
        "runtime": {
            "name": "@huggingface/transformers",
            "version": RUNTIME_VERSION,
            "browser_device": "wasm",
        },
        "dtype": "float32",
        "byte_order": "little",
        "normalized": True,
        **models,
    }
    content = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    target = output / "manifest.json"

    if not target.exists() or target.read_text(encoding="utf-8") != content:
        with atomic_output(target) as temporary:
            temporary.write_text(content, encoding="utf-8")

    print(
        f"Embedded {len(tracks)} tracks; generated {len(missing)}, "
        f"reused {len(tasks) - len(missing)} vectors."
    )
