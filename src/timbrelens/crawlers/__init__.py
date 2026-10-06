from collections.abc import Callable
from pathlib import Path

from timbrelens.crawlers import creatorchords, incompetech
from timbrelens.models import Track

CRAWLERS: dict[str, Callable[[Path, Path, float, int | None, bool], list[Track]]] = {
    "creatorchords": creatorchords.crawl,
    "incompetech": incompetech.crawl,
}
