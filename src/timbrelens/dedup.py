import json
import re
import subprocess
import sys
from collections import defaultdict
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
    if abs(left["duration"] - right["duration"]) > 2:
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
        if errors <= 0.01 * 32 * len(pairs):
            return True

    return False


def merge(catalog: Catalog, originals: Path, cache: Path) -> Catalog:
    catalog = state.merge(catalog, [])
    groups = defaultdict(list)
    for track in catalog["tracks"]:
        key = tuple(
            re.sub(r"[\W_]+", "", track.get(field, "").casefold()) for field in ("title", "artist")
        )
        if all(key):
            groups[key].append(track)

    candidates = {
        track["id"]: track.get("preview", {}).get("source_sha256")
        for group in groups.values()
        if len(group) > 1
        for track in group
    }
    if not candidates:
        return catalog

    paths = {}
    for audio in originals.glob("*/*"):
        metadata = audio.with_suffix(".json")
        if audio.suffix != ".json" and metadata.is_file():
            identifier = state.load(metadata)["tracks"][0]["id"]
            if identifier in candidates and sha256(audio) == candidates[identifier]:
                paths[identifier] = audio

    removed = set()
    with Cache(str(cache / "fingerprints")) as store:
        for group in groups.values():
            if len(group) < 2:
                continue

            representatives = []
            for track in group:
                audio = paths.get(track["id"])
                if audio is None:
                    continue

                fingerprint = _fingerprint(audio, store)
                if fingerprint is None:
                    continue

                for reference in representatives:
                    if _matches(reference, fingerprint):
                        removed.add(track["id"])
                        break
                else:
                    representatives.append(fingerprint)

    catalog["tracks"] = [track for track in catalog["tracks"] if track["id"] not in removed]
    return catalog
