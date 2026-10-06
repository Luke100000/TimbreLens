import hashlib
import math
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from diskcache import Cache

from timbrelens.files import atomic_output

USER_AGENT = "TimbreLens/0.1.0 (mailto:conczin@gmail.com)"


def _retry_delay(value: str | None, attempt: int) -> float:
    if value is None:
        return 2**attempt

    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError):
            return 2**attempt

    if not math.isfinite(delay):
        return 2**attempt

    return max(0, delay)


class CachedHTTP:
    def __init__(self, directory: Path, transport: httpx.BaseTransport | None = None):
        self.directory = directory
        self.cache = Cache(str(directory / "index"))
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=60,
            transport=transport or httpx.HTTPTransport(retries=2),
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()
        self.cache.close()

    def get(self, url: str, max_age: float = 86400) -> Path:
        if max_age < 0:
            raise ValueError("Cache age must be nonnegative.")

        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.directory / "downloads" / (key + Path(urlsplit(url).path).suffix)
        metadata = self.cache.get(url) if path.is_file() else None
        if metadata and time.time() - metadata["checked_at"] < max_age:
            return path

        headers = {}
        if metadata:
            if metadata.get("etag"):
                headers["If-None-Match"] = metadata["etag"]
            if metadata.get("last_modified"):
                headers["If-Modified-Since"] = metadata["last_modified"]

        for attempt in range(4):
            with self.client.stream("GET", url, headers=headers) as response:
                retry_after = response.headers.get("Retry-After")
                if response.status_code == 429 or (
                    response.status_code == 503 and retry_after is not None
                ):
                    if attempt == 3:
                        response.raise_for_status()

                    delay = _retry_delay(retry_after, attempt)
                else:
                    if response.status_code == 304 and metadata:
                        metadata["checked_at"] = time.time()
                        self.cache[url] = metadata
                        return path

                    response.raise_for_status()

                    with atomic_output(path) as temporary, temporary.open("wb") as stream:
                        for chunk in response.iter_bytes():
                            stream.write(chunk)

                    self.cache[url] = {
                        "checked_at": time.time(),
                        "etag": response.headers.get("etag"),
                        "last_modified": response.headers.get("last-modified"),
                    }
                    return path

            # Close the response before waiting so the connection can be reused.
            time.sleep(delay)

        raise RuntimeError("Cannot continue, website refused.")
