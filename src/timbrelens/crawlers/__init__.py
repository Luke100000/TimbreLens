from collections.abc import Callable
from functools import partial
from pathlib import Path

from timbrelens.crawlers import creatorchords, github, incompetech, silverman, soundcloud
from timbrelens.models import Track

CRAWLERS: dict[str, Callable[[Path, Path, float, int | None, bool], list[Track]]] = {
    "creatorchords": creatorchords.crawl,
    "freepd": partial(
        github.crawl,
        "0lhi/FreePD",
        "freepd",
        "CC0-1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    ),
    "incompetech": incompetech.crawl,
    "silverman": silverman.crawl,
    "timkulig": partial(
        soundcloud.crawl,
        "https://soundcloud.com/timkuligfreemusic",
        "timkulig",
        "https://creativecommons.org/licenses/by/4.0/",
        artist="Tim Kulig",
        website="https://timkulig.com/",
    ),
}
