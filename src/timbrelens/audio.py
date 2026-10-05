import hashlib
import json
import math
import subprocess
import sys
from array import array
from functools import cache
from pathlib import Path

from diskcache import Cache

from timbrelens.files import atomic_output, sha256
from timbrelens.models import Preview

RECIPE_VERSION = "energy-window-loudnorm-v2"
FADE_DURATION = 0.005
NORMALIZATION = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "2"]
MP3_ENCODING = [
    "-c:a",
    "libmp3lame",
    "-b:a",
    "96k",
    "-write_xing",
    "0",
    "-id3v2_version",
    "0",
]


def _ffmpeg(arguments: list[str]) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *arguments],
        capture_output=True,
    )
    if result.returncode:
        raise ValueError(f"FFmpeg failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


@cache
def _ffmpeg_version() -> str:
    return _ffmpeg(["-version"]).decode()


def normalize(input: Path, output: Path) -> None:
    encoding = MP3_ENCODING if output.suffix.lower() == ".mp3" else []
    with atomic_output(output) as temporary:
        _ffmpeg(
            [
                "-y",
                "-i",
                str(input.resolve()),
                "-vn",
                *NORMALIZATION,
                *encoding,
                "-map_metadata",
                "-1",
                "-fflags",
                "+bitexact",
                str(temporary.resolve()),
            ]
        )


def _window(input: Path, duration: float) -> tuple[int, int]:
    sample_rate = 8000
    samples = array(
        "h",
        _ffmpeg(
            [
                "-i",
                str(input.resolve()),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-f",
                "s16le",
                "pipe:1",
            ]
        ),
    )
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise ValueError(f"No audio samples: {input}")
    duration = min(duration, len(samples) / sample_rate)
    energy = [0]
    for offset in range(0, len(samples), sample_rate):
        energy.append(
            energy[-1] + sum(value * value for value in samples[offset : offset + sample_rate])
        )
    window = math.ceil(duration)
    starts = range(math.floor(len(samples) / sample_rate - duration) + 1)
    start = max(
        starts, key=lambda offset: energy[min(offset + window, len(energy) - 1)] - energy[offset]
    )
    return start * 1000, round(duration * 1000)


def _preview_filters(duration: float) -> str:
    fade = min(FADE_DURATION, duration / 2)
    return ",".join(
        [
            f"atrim=duration={duration}",
            "asetpts=PTS-STARTPTS",
            NORMALIZATION[1],
            f"afade=t=in:st=0:d={fade}",
            f"afade=t=out:st={duration - fade}:d={fade}",
        ]
    )


def preview(
    input: Path, output: Path, track_id: str, store: Cache, duration: float = 20.0
) -> Preview:
    if not math.isfinite(duration) or duration < 0.001:
        raise ValueError("Preview duration must be finite and at least 0.001 seconds.")

    duration = round(duration * 1000) / 1000
    source_hash = sha256(input)
    recipe = {
        "source_sha256": source_hash,
        "duration_ms": round(duration * 1000),
        "version": RECIPE_VERSION,
        "ffmpeg": _ffmpeg_version(),
        "normalization": NORMALIZATION,
        "encoding": MP3_ENCODING,
        "fade": FADE_DURATION,
    }
    recipe_hash = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
    relative = Path(hashlib.sha256(track_id.encode()).hexdigest() + ".mp3")
    target = output / relative
    key = ("preview", track_id, recipe_hash)

    existing = store.get(key)
    if not (existing and target.is_file() and sha256(target) == existing["sha256"]):
        start_ms, duration_ms = _window(input, duration)
        with atomic_output(target) as temporary:
            _ffmpeg(
                [
                    "-y",
                    "-ss",
                    str(start_ms / 1000),
                    "-i",
                    str(input.resolve()),
                    "-t",
                    str(duration_ms / 1000),
                    "-vn",
                    "-af",
                    _preview_filters(duration_ms / 1000),
                    *NORMALIZATION[2:],
                    *MP3_ENCODING,
                    "-map_metadata",
                    "-1",
                    "-fflags",
                    "+bitexact",
                    str(temporary.resolve()),
                ]
            )

        existing = {
            "start_ms": start_ms,
            "duration_ms": duration_ms,
            "sha256": sha256(target),
        }
        store[key] = existing

    return {
        "path": relative.as_posix(),
        "start": existing["start_ms"] / 1000,
        "duration": existing["duration_ms"] / 1000,
        "sha256": existing["sha256"],
    }
