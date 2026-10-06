import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from timbrelens.crawlers.common import prepare_previews, validate_options
from timbrelens.http import USER_AGENT, CachedHTTP
from timbrelens.models import Track

BASE = "https://www.silvermansound.com/"
LIBRARY = BASE + "free-music/"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"


def _sitemap(http: CachedHTTP, url: str, age: float) -> ET.Element:
    content = http.get(url, age).read_text(encoding="utf-8-sig").lstrip()
    try:
        return ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError(f"Invalid Silverman sitemap: {url}") from error


def discover(http: CachedHTTP, age: float) -> list[str]:
    index = _sitemap(http, BASE + "sitemap_index.xml", age)
    sitemaps = [
        node.text
        for node in index.findall("{*}sitemap/{*}loc")
        if re.fullmatch(r"product-sitemap\d*\.xml", urlsplit(node.text).path.rsplit("/", 1)[-1])
    ]
    if not sitemaps:
        raise ValueError("Silverman product sitemap not found.")

    urls = set()
    for url in sitemaps:
        sitemap = _sitemap(http, url, age)
        urls.update(node.text for node in sitemap.findall("{*}url/{*}loc"))

    # The complete archive is a shop product, not a track.
    tracks = sorted(
        url for url in urls if url.startswith(LIBRARY) and url != LIBRARY + "download-every-track"
    )
    if not tracks:
        raise ValueError("No Silverman tracks found in the product sitemap.")

    return tracks


def map_track(html: str, url: str) -> Track:
    page = BeautifulSoup(html, "html.parser")
    recording = {}
    for script in page.select('script[type="application/ld+json"]'):
        data = json.loads(script.get_text())
        for item in data.get("@graph", [data]):
            if "MusicRecording" in item.get("@type", []):
                recording = item

    download = page.select_one("a.mp3-download[href]")
    attribution = page.select_one("#attribution-text")
    if not recording or download is None or attribution is None:
        raise ValueError(f"Missing Silverman track metadata: {url}")

    if not any(
        license["url"].rstrip("/") == LICENSE.rstrip("/") for license in recording["license"]
    ):
        raise ValueError(f"Silverman track has no CC BY 4.0 license: {url}")

    genres = sorted(set(recording.get("genre", [])))
    moods = sorted(
        {node.get_text(strip=True) for node in page.select(".detail-item.mood .detail-tag")}
    )
    instruments = sorted(
        {node.get_text(strip=True) for node in page.select(".detail-item.instruments .detail-tag")}
    )
    collections = [
        {"name": node.get_text(" ", strip=True), "url": urljoin(url, str(node["href"]))}
        for node in page.select(".sssc-collection-link a[href]")
    ]
    keywords = {term.strip() for term in recording.get("keywords", "").split(",") if term.strip()}
    tags = keywords | set(genres + moods + instruments) | {row["name"] for row in collections}

    details = {}
    for item in page.select(".detail-item"):
        label = item.select_one(".detail-label")
        value = item.select_one(".detail-value")
        if label is not None and value is not None:
            details[label.get_text(strip=True)] = value.get_text(" ", strip=True)

    duration = None
    if details.get("Length"):
        duration = 0
        for part in details["Length"].split(":"):
            duration = duration * 60 + int(part)

    properties = {row["name"]: row["value"] for row in recording.get("additionalProperty", [])}
    bpm_value = properties.get("BPM") or details.get("BPM")
    bpm = float(bpm_value) if bpm_value else None
    if bpm is not None and (not math.isfinite(bpm) or bpm <= 0):
        bpm = None

    canonical = page.select_one('link[rel="canonical"]')
    source_url = urljoin(url, str(canonical["href"])) if canonical else url
    isrc = recording.get("identifier", {}).get("value") or details.get("ISRC") or None
    source_id = isrc or urlsplit(source_url).path.rstrip("/").rsplit("/", 1)[-1]
    artist = recording["byArtist"]["name"]
    published = recording.get("datePublished")

    return {
        "id": f"silverman:{source_id}",
        "source": "silverman",
        "source_id": source_id,
        "source_url": source_url,
        "audio_url": urljoin(url, str(download["href"])),
        "title": recording["name"].strip(),
        "artist": artist,
        "composer": recording.get("recordingOf", {}).get("composer", {}).get("name", artist),
        "copyright_holder": artist,
        "description": recording.get("description", "").strip(),
        "tags": sorted(tags),
        "genres": genres,
        "moods": moods,
        "instruments": instruments,
        "isrc": isrc,
        "uploaded": date.fromisoformat(published[:10]) if published else None,
        "duration": duration,
        "bpm": bpm,
        "license": "CC-BY-4.0",
        "license_url": LICENSE,
        "attribution": attribution.get_text(" ", strip=True),
        "metadata": {
            "released": details.get("Released", ""),
            "collections": collections,
            "stems": "Stem Tracks" in properties,
            "links": [str(node["href"]) for node in page.select(".platform-buttons a[href]")],
        },
    }


def crawl(
    cache: Path,
    previews: Path,
    duration: float = 20.0,
    limit: int | None = None,
    refresh: bool = False,
) -> list[Track]:
    validate_options(duration, limit)

    with CachedHTTP(cache / "silverman") as http:
        age = 0 if refresh else 86400
        robots = RobotFileParser()
        robots.parse(http.get(BASE + "robots.txt", age).read_text().splitlines())
        urls = discover(http, age)[:limit]
        tracks = []
        for index, url in enumerate(urls, 1):
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError(f"Silverman robots.txt disallows {url}")

            print(f"[{index}/{len(urls)}] Fetching {url}", file=sys.stderr)
            tracks.append(map_track(http.get(url, age).read_text(encoding="utf-8"), url))

        tracks.sort(key=lambda track: track["id"])
        if len({track["id"] for track in tracks}) != len(tracks):
            raise ValueError("Silverman returned duplicate track IDs.")

        prepare_previews(tracks, http, previews, duration, refresh)

    return tracks
