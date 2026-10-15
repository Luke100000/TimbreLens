import json
import subprocess
import sys
from pathlib import Path

from diskcache import Cache

from timbrelens import state
from timbrelens.files import sha256
from timbrelens.models import Catalog


def _fingerprint(audio: Path, cache: Cache) -> dict | None:
    key = ("chromaprint-full-v1", sha256(audio))
    result = cache.get(key)
    if result is not None:
        return result

    process = subprocess.run(
        ["fpcalc", "-raw", "-json", "-length", "0", str(audio.resolve())],
        capture_output=True,
        text=True,
    )
    if process.returncode:
        print(f"Skipping fingerprint for {audio}: {process.stderr.strip()}", file=sys.stderr)
        return None

    result = json.loads(process.stdout)
    cache[key] = result
    return result


def _matches(left: dict, right: dict) -> bool:
    if abs(left["duration"] - right["duration"]) > 5:
        return False

    first, second = left["fingerprint"], right["fingerprint"]
    if min(len(first), len(second)) < 80:
        return False

    # Allow small encoding offsets, but compare nearly the entire recording.
    for offset in range(-8, 9):
        pairs = list(zip(first[max(offset, 0) :], second[max(-offset, 0) :]))
        if len(pairs) < 0.95 * max(len(first), len(second)):
            continue

        errors = sum((a ^ b).bit_count() for a, b in pairs)
        if errors <= 0.05 * 32 * len(pairs):
            return True

    return False


def merge(catalog: Catalog, originals: Path, cache: Path) -> Catalog:
    catalog = state.merge(catalog, [])
    candidates = {
        track["id"]: track.get("preview", {}).get("source_sha256") for track in catalog["tracks"]
    }
    if len(candidates) < 2:
        return catalog

    paths = {}
    for audio in originals.glob("*/*"):
        metadata = audio.with_suffix(".json")
        if audio.suffix != ".json" and metadata.is_file():
            identifier = state.load(metadata)["tracks"][0]["id"]
            if identifier in candidates and sha256(audio) == candidates[identifier]:
                paths[identifier] = audio

    unique = []
    representatives = []
    with Cache(str(cache / "fingerprints")) as store:
        for track in catalog["tracks"]:
            audio = paths.get(track["id"])
            fingerprint = _fingerprint(audio, store) if audio else None
            if fingerprint is not None:
                if any(_matches(reference, fingerprint) for reference in representatives):
                    continue

                representatives.append(fingerprint)

            unique.append(track)

    catalog["tracks"] = unique
    return catalog
