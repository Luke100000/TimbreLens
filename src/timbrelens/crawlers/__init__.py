from collections.abc import Callable
from pathlib import Path

from timbrelens.crawlers import incompetech
from timbrelens.models import Track

CRAWLERS: dict[str, Callable[[Path, Path, float], list[Track]]] = {
    "incompetech": incompetech.crawl,
}
