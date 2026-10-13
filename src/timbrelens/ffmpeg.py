import subprocess
from functools import cache


def run(arguments: list[str]) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *arguments],
        capture_output=True,
    )
    if result.returncode:
        raise ValueError(f"FFmpeg failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


@cache
def version() -> str:
    return run(["-version"]).decode()
