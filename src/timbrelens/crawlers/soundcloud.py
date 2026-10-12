import io
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
from yt_dlp.networking import Request, Response
from yt_dlp.networking.exceptions import HTTPError
from yt_dlp.utils import DownloadError

from timbrelens.crawlers.common import parse_license, prepare_preview, validate_options
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"


class SoundCloudDL(YoutubeDL):
    def __init__(self, http: CachedHTTP, refresh: bool):
        self.http = http
        self.max_age = 0 if refresh else 3600
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
        if request.method != "GET":
            return super().urlopen(request)

        # Use the shared cache and rate-limit handling for yt-dlp's metadata requests.
        try:
            path = self.http.get(request.url, self.max_age, headers=dict(request.headers))
        except httpx.HTTPStatusError as error:
            response = Response(
                io.BytesIO(), request.url, dict(error.response.headers), error.response.status_code
            )
            raise HTTPError(response) from error

        metadata = self.http.cache[request.url]

        # Keep API license codes available before resolving individual audio streams.
        if urlsplit(request.url).hostname == "api-v2.soundcloud.com":
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
            metadata.get("response_url", request.url),
            {"Content-Length": str(path.stat().st_size)},
        )


def _terms(values: list[str]) -> list[str]:
    return sorted(
        {term.strip() for value in values for term in re.split(r"[,;]", value) if term.strip()}
    )


def _eligible(
    code: str | None,
    website: str,
    strict_license: bool = False,
    license_override_url: str = "",
) -> bool:
    if license_override_url:
        return True

    return code in ("cc-by", "no-rights-reserved", "cc0") or (
        not strict_license and bool(website) and code in (None, "all-rights-reserved")
    )


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

    attribution = ""
    if license_url == CC0:
        license = "CC0-1.0"
    else:
        version = urlsplit(license_url).path.rstrip("/").rsplit("/", 1)[-1]
        license = f"CC-BY-{version}"
        attribution = (
            f'Title: "{title}"\nArtist: {artist} ({creator_url})\n'
            f"Licensed under Creative Commons By Attribution {version}\n{license_url}"
        )

    return {
        "id": f"{source}:{source_id}",
        "source": source,
        "source_id": source_id,
        "source_url": info["webpage_url"],
        "audio_url": info["webpage_url"],
        "title": title,
        "artist": artist,
        "composer": "",
        "copyright_holder": "",
        "description": (info.get("description") or "").strip(),
        "tags": sorted(set(tags + genres)),
        "genres": genres,
        "moods": [],
        "instruments": [],
        "isrc": None,
        "uploaded": date.fromisoformat(info["upload_date"]) if info.get("upload_date") else None,
        "duration": info.get("duration"),
        "bpm": None,
        "license": license,
        "license_url": license_url,
        "attribution": attribution,
        "metadata": {
            "soundcloud_license": info.get("license"),
            "license_source": license_override_url or website or info["webpage_url"],
            "uploader": info.get("uploader", ""),
            "uploader_url": info.get("uploader_url", ""),
            "tags": info.get("tags") or [],
        },
    }


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
    strict_license: bool = False,
    exclude: str = "",
    license_override_url: str = "",
) -> list[Track]:
    validate_options(duration, limit)
    if license_url != CC0 and not re.fullmatch(
        r"https://creativecommons\.org/licenses/by/\d\.\d/", license_url
    ):
        raise ValueError("SoundCloud sources need a CC BY or CC0 license URL.")

    if len(urlsplit(url).path.strip("/").split("/")) == 1:
        url = url.rstrip("/") + "/tracks"

    tracks = []
    skipped = 0
    age = 0 if refresh else 30 * 86400

    with CachedHTTP(cache / source) as http, SoundCloudDL(http, refresh) as downloader:
        # A configured publisher declaration can supersede mislabeled platform tracks.
        if license_override_url:
            policy_age = 0 if refresh else 86400
            html = http.get(license_override_url, policy_age).read_text()
            page = BeautifulSoup(html, "html.parser")
            licenses = {parse_license(str(anchor["href"])) for anchor in page.select("a[href]")}
            if parse_license(license_url) not in licenses:
                raise ValueError(
                    f"Publisher license declaration is missing: {license_override_url}"
                )

        try:
            index = downloader.extract_info(url, download=False)
            entries = index.get("entries", [index])
            entries = {entry["id"]: entry for entry in entries}

            for position, entry in enumerate(entries.values(), 1):
                print(f"[{position}/{len(entries)}] {entry['title']}", file=sys.stderr)
                indexed = downloader.tracks.get(entry["id"])

                if exclude and re.search(exclude, entry["title"], re.IGNORECASE):
                    skipped += 1
                    continue

                if indexed and not _eligible(
                    indexed.get("license"), website, strict_license, license_override_url
                ):
                    skipped += 1
                    continue

                info = downloader.extract_info(
                    entry.get("webpage_url") or entry["url"], download=False
                )

                if not _eligible(
                    info.get("license"), website, strict_license, license_override_url
                ):
                    skipped += 1
                    continue

                track = map_track(info, source, license_url, artist, website, license_override_url)
                audio = http.get(info["url"], age, cache_key=track["audio_url"])
                prepare_preview(track, audio, previews, http.cache, duration)
                tracks.append(track)

                if limit is not None and len(tracks) >= limit:
                    break

        except DownloadError as error:
            raise ValueError(f"SoundCloud extraction failed: {error}") from error

    if skipped:
        print(f"Skipped {skipped} ineligible SoundCloud tracks.", file=sys.stderr)

    return tracks
