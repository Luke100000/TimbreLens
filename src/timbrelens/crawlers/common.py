import sys
from pathlib import Path

from timbrelens.audio import preview
from timbrelens.http import CachedHTTP
from timbrelens.models import Track


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
        track["preview"] = preview(audio, previews, http.cache, duration)
