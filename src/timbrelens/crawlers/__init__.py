from collections.abc import Callable
from functools import partial
from pathlib import Path

from timbrelens.crawlers import (
    bandcamp,
    creatorchords,
    github,
    incompetech,
    kongano,
    silverman,
    soundcloud,
    teknoaxe,
)
from timbrelens.models import Track

CRAWLERS: dict[str, Callable[[Path, Path, float, int | None, bool], list[Track]]] = {
    "creatorchords": creatorchords.crawl,
    "darrencurtis": partial(
        soundcloud.crawl,
        "https://soundcloud.com/desperate-measurez",
        "darrencurtis",
        "https://creativecommons.org/licenses/by/3.0/",
        artist="Darren Curtis",
        website="https://www.darrencurtismusic.com/",
        strict_license=True,
    ),
    "freepd": partial(
        github.crawl,
        "0lhi/FreePD",
        "freepd",
        "CC0-1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    ),
    "incompetech": incompetech.crawl,
    "ifness": partial(
        bandcamp.crawl,
        "https://justinallanarnold.bandcamp.com/music",
        "ifness",
        artist="Justin Allan Arnold",
        website="https://www.ifnessfreemusic.com/",
    ),
    "kongano": kongano.crawl,
    "scottbuckley": partial(
        soundcloud.crawl,
        "https://soundcloud.com/scottbuckley",
        "scottbuckley",
        "https://creativecommons.org/licenses/by/4.0/",
        artist="Scott Buckley",
        website="https://www.scottbuckley.com.au/",
        strict_license=True,
        exclude=r"\bremix\b",
    ),
    "silverman": silverman.crawl,
    "tannerhelland": partial(
        github.crawl,
        "tannerhelland/free-music",
        "tannerhelland",
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
        path_prefix="mp3/",
        artist="Tanner Helland",
        website="https://tannerhelland.com/music.html",
        exclude=r"\b(?:arrangement|Castlevania|Final Fantasy|DragonFyre)\b",
    ),
    "teknoaxe": teknoaxe.crawl,
    "timkulig": partial(
        soundcloud.crawl,
        "https://soundcloud.com/timkuligfreemusic",
        "timkulig",
        "https://creativecommons.org/licenses/by/4.0/",
        artist="Tim Kulig",
        website="https://timkulig.com/",
    ),
}
