import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from timbrelens.crawlers.common import prepare_previews, validate_options
from timbrelens.http import CachedHTTP
from timbrelens.models import Track

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".aiff"}


def map_track(
    repository: str, source: str, commit: str, path: str, license: str, license_url: str
) -> Track:
    file = PurePosixPath(path)
    encoded = quote(path, safe="/")
    category = file.parent.as_posix()
    collections = []
    if category != ".":
        collections.append(
            {
                "name": category,
                "url": f"https://github.com/{repository}/tree/{commit}/{quote(category, safe='/')}",
            }
        )

    return {
        "id": f"{source}:{path}",
        "source": source,
        "source_id": path,
        "source_url": f"https://github.com/{repository}/blob/{commit}/{encoded}",
        "audio_url": f"https://raw.githubusercontent.com/{repository}/{commit}/{encoded}",
        "title": "",
        "artist": "",
        "composer": "",
        "copyright_holder": "",
        "description": "",
        "tags": [row["name"] for row in collections],
        "genres": [],
        "moods": [],
        "instruments": [],
        "isrc": None,
        "uploaded": None,
        "duration": None,
        "bpm": None,
        "license": license,
        "license_url": license_url,
        "attribution": "",
        "metadata": {
            "repository": repository,
            "commit": commit,
            "path": path,
            "collections": collections,
        },
    }


def crawl(
    repository: str,
    source: str,
    license: str,
    license_url: str,
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
    ref: str | None = None,
) -> list[Track]:
    validate_options(duration, limit)
    api = f"https://api.github.com/repos/{repository}"

    with CachedHTTP(cache / source) as http:
        age = 0 if refresh else 86400
        if ref is None:
            info = json.loads(http.get(api, age).read_text())
            ref = info["default_branch"]

        revision = json.loads(http.get(f"{api}/commits/{quote(ref, safe='')}", age).read_text())
        commit = revision["sha"]
        tree = json.loads(http.get(f"{api}/git/trees/{commit}?recursive=1", age).read_text())
        if tree["truncated"]:
            raise ValueError(f"GitHub returned an incomplete file index for {repository}.")

        paths = sorted(
            entry["path"]
            for entry in tree["tree"]
            if entry["type"] == "blob"
            and entry["mode"] in ("100644", "100755")
            and PurePosixPath(entry["path"]).suffix.lower() in AUDIO_EXTENSIONS
        )
        if not paths:
            raise ValueError(f"No audio files found in {repository}.")

        # Pin downloads to the indexed commit so a branch update cannot mix snapshots.
        tracks = [
            map_track(repository, source, commit, path, license, license_url)
            for path in paths[:limit]
        ]
        prepare_previews(tracks, http, previews, duration, refresh)

    return tracks
