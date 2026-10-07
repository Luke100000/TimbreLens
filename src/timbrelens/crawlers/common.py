import math
import sys
from pathlib import Path

from timbrelens import originals
from timbrelens.audio import preview
from timbrelens.http import CachedHTTP
from timbrelens.models import Track


def validate_options(duration: float, limit: int | None) -> None:
    if limit is not None and limit <= 0:
        raise ValueError("Track limit must be positive.")

    if not math.isfinite(duration) or duration < 0.001:
        raise ValueError("Preview duration must be finite and at least 0.001 seconds.")


def prepare_previews(
    tracks: list[Track],
    http: CachedHTTP,
    previews: Path,
    duration: float,
    refresh: bool = False,
) -> None:
    age = 0 if refresh else 30 * 86400

    for index, track in enumerate(tracks, 1):
        print(f"[{index}/{len(tracks)}] {track['title']}", file=sys.stderr)
        audio = http.get(track["audio_url"], age)
        originals.save(track, audio, previews.parent / "originals")
        track["preview"] = preview(audio, previews, http.cache, duration)
