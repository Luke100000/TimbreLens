import hashlib
import io
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.networking import Request, Response
from yt_dlp.networking.exceptions import HTTPError
from yt_dlp.utils import DownloadError

from timbrelens.crawlers.common import (
    attribution,
    get_audio,
    licensed_track,
    parse_license,
    prepare_preview,
    validate_options,
)
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"


class SoundCloudDL(YoutubeDL):
    def __init__(self, http: CachedHTTP, refresh: bool):
        self.http = http
        self.max_age = 0 if refresh else 86400
        self.tracks = {}
        super().__init__(
            {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": "in_playlist",
                "format": "bestaudio[protocol=http][ext=mp3][format_id!*=preview]",
                "extractor_args": {"soundcloud": {"formats": ["http_mp3"]}},
                "http_headers": {"User-Agent": USER_AGENT},
                "cachedir": str(http.directory / "yt-dlp"),
            }
        )

    def urlopen(self, request):
        if isinstance(request, str):
            request = Request(request)
        if request.method not in {"GET", "HEAD"}:
            return super().urlopen(request)

        cache_key = request.url
        age = self.max_age
        if request.method == "HEAD":
            cache_key = "HEAD:" + request.url
            cached = self.http.cache.get(cache_key)
            if not cached or cached["status_code"] < 400:
                age = None
        elif re.fullmatch(r"/assets/[^/]+-[a-f0-9]+\.js", urlsplit(request.url).path):
            age = None

        # yt-dlp probes artwork even for a flat playlist; cache those requests too.
        try:
            path = self.http.get(
                request.url, age, headers=dict(request.headers), method=request.method
            )
        except httpx.HTTPStatusError as error:
            response = Response(
                io.BytesIO(), request.url, dict(error.response.headers), error.response.status_code
            )
            raise HTTPError(response) from error

        metadata = self.http.cache[cache_key]
        if metadata["status_code"] >= 400:
            raise HTTPError(
                Response(io.BytesIO(), request.url, metadata["headers"], metadata["status_code"])
            )

        # Keep API license codes available before resolving individual audio streams.
        if request.method == "GET" and urlsplit(request.url).hostname == "api-v2.soundcloud.com":
            data = json.loads(path.read_bytes())
            items = data
            if isinstance(data, dict):
                items = data.get("collection") or [data]

            for item in items:
                track = item.get("track", item)
                if track.get("kind") == "track":
                    self.tracks[str(track["id"])] = track

        return Response(
            path.open("rb"),
            metadata["response_url"],
            metadata["headers"]
            if request.method == "HEAD"
            else {"Content-Length": str(path.stat().st_size)},
        )


def _terms(values: list[str]) -> list[str]:
    return sorted(
        {term.strip() for value in values for term in re.split(r"[,;]", value) if term.strip()}
    )


def _eligible(
    code: str | None,
    license_override_url: str = "",
) -> bool:
    if license_override_url:
        return True

    return code in ("cc-by", "no-rights-reserved", "cc0")


def map_track(
    info: dict,
    source: str,
    license_url: str,
    artist: str = "",
    website: str = "",
    license_override_url: str = "",
) -> Track:
    source_id = str(info["id"])
    title = info["title"].strip()
    artist = artist or ", ".join(info.get("artists") or []) or info.get("uploader", "")
    creator_url = website or info.get("uploader_url", "")
    genres = _terms(info.get("genres") or [])
    tags = _terms(info.get("tags") or [])

    if not license_override_url and info.get("license") in ("no-rights-reserved", "cc0"):
        license_url = CC0

    track = licensed_track(
        source, source_id, title, artist, info["webpage_url"], info["webpage_url"], license_url
    )
    track["description"] = (info.get("description") or "").strip()
    track["tags"] = sorted(set(tags + genres))
    track["genres"] = genres
    track["uploaded"] = date.fromisoformat(info["upload_date"]) if info.get("upload_date") else None
    track["duration"] = info.get("duration")
    track["attribution"] = attribution(track, creator_url)
    track["metadata"] = {
        "soundcloud_license": info.get("license"),
        "license_source": license_override_url or website or info["webpage_url"],
        "uploader": info.get("uploader", ""),
        "uploader_url": info.get("uploader_url", ""),
        "tags": info.get("tags") or [],
    }

    return track


def track_revision(indexed: dict) -> str:
    fields = (
        "title",
        "permalink_url",
        "description",
        "license",
        "genre",
        "tag_list",
        "publisher_metadata",
        "duration",
        "created_at",
        "last_modified",
        "media",
    )
    metadata = {field: indexed.get(field) for field in fields}
    user = indexed.get("user") or {}
    metadata["user"] = {field: user.get(field) for field in ("username", "permalink_url")}
    return hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()


def crawl(
    url: str,
    source: str,
    license_url: str,
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
    artist: str = "",
    website: str = "",
    exclude: str = "",
    license_override_url: str = "",
) -> list[Track]:
    validate_options(duration, limit)
    if parse_license(license_url) is None:
        raise ValueError("SoundCloud sources need a CC BY or CC0 license URL.")

    if len(urlsplit(url).path.strip("/").split("/")) == 1:
        url = url.rstrip("/") + "/tracks"

    tracks = []
    skipped = 0

    with CachedHTTP(cache / source) as http, SoundCloudDL(http, refresh) as downloader:
        try:
            index = downloader.extract_info(url, download=False)
            entries = index.get("entries", [index])
            if not entries:
                raise ValueError("SoundCloud returned an empty track index.")

            entries = {entry["id"]: entry for entry in entries}

            for position, entry in enumerate(entries.values(), 1):
                print(f"[{position}/{len(entries)}] {entry['title']}", file=sys.stderr)
                indexed = downloader.tracks.get(entry["id"])

                if exclude and re.search(exclude, entry["title"], re.IGNORECASE):
                    skipped += 1
                    continue

                if indexed and not _eligible(indexed.get("license"), license_override_url):
                    skipped += 1
                    continue

                fingerprint = track_revision(indexed or entry)
                info_key = f"soundcloud-info:{entry['id']}"
                cached = http.cache.get(info_key)
                audio_key = f"audio:{source}:{entry['id']}"
                audio = http.cached_path(audio_key)

                # Reuse extracted metadata when the catalog entry is unchanged.
                if (
                    cached
                    and cached["fingerprint"] == fingerprint
                    and (indexed is not None or time.time() - cached["checked_at"] < 86400)
                    and audio is not None
                ):
                    info = cached["info"]
                    checked_at = cached["checked_at"]
                else:
                    info = downloader.extract_info(
                        entry.get("webpage_url") or entry["url"], download=False
                    )
                    audio = None
                    checked_at = time.time()

                if not _eligible(info.get("license"), license_override_url):
                    skipped += 1
                    continue

                track = map_track(info, source, license_url, artist, website, license_override_url)
                if audio is None:
                    try:
                        audio = get_audio(http, track, info["url"])
                    except httpx.HTTPStatusError as error:
                        if error.response.status_code not in (401, 403):
                            raise

                        # Signed URLs can expire before their cached metadata does.
                        previous_age = downloader.max_age
                        downloader.max_age = 0
                        try:
                            info = downloader.extract_info(track["source_url"], download=False)
                        finally:
                            downloader.max_age = previous_age

                        if not _eligible(info.get("license"), license_override_url):
                            raise ValueError(
                                "SoundCloud license changed while refreshing audio: "
                                + track["source_url"]
                            )

                        track = map_track(
                            info, source, license_url, artist, website, license_override_url
                        )
                        audio = get_audio(http, track, info["url"])

                info_fields = (
                    "id",
                    "title",
                    "artists",
                    "uploader",
                    "uploader_url",
                    "webpage_url",
                    "license",
                    "description",
                    "genres",
                    "tags",
                    "upload_date",
                    "duration",
                )
                http.cache[info_key] = {
                    "fingerprint": fingerprint,
                    "checked_at": checked_at,
                    "info": {field: info[field] for field in info_fields if field in info},
                }
                prepare_preview(track, audio, previews, http.cache, duration)
                tracks.append(track)

                if limit is not None and len(tracks) >= limit:
                    break

        except DownloadError as error:
            raise ValueError(f"SoundCloud extraction failed: {error}") from error

    if skipped:
        print(f"Skipped {skipped} ineligible SoundCloud tracks.", file=sys.stderr)

    return tracks
