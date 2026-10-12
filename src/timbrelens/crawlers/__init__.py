from collections.abc import Callable
from functools import partial
from pathlib import Path

from timbrelens.crawlers import (
    archive,
    bandcamp,
    creatorchords,
    github,
    incompetech,
    kongano,
    silverman,
    soundcloud,
    teknoaxe,
    timbeek,
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
    "ifness": partial(
        bandcamp.crawl,
        "https://justinallanarnold.bandcamp.com/music",
        "ifness",
        artist="Justin Allan Arnold",
        website="https://www.ifnessfreemusic.com/",
    ),
    "incompetech": incompetech.crawl,
    "kingjames": partial(
        soundcloud.crawl,
        "https://soundcloud.com/kingjamesroyaltyfree",
        "kingjames",
        "https://creativecommons.org/licenses/by/3.0/",
        artist="James Richardson",
        website="https://kingjamesroyaltyfreemusic.blogspot.com/",
        license_override_url=(
            "https://kingjamesroyaltyfreemusic.blogspot.com/p/what-does-royalty-free-mean.html"
        ),
    ),
    "kongano": kongano.crawl,
    "ondrosik": partial(
        archive.crawl,
        "Ondrosik-Free-music-catalog",
        "ondrosik",
        artist="Ondrosik",
        website="https://ondrosik.sk/music/",
    ),
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
    "timbeek": timbeek.crawl,
    "timkulig": partial(
        soundcloud.crawl,
        "https://soundcloud.com/timkuligfreemusic",
        "timkulig",
        "https://creativecommons.org/licenses/by/4.0/",
        artist="Tim Kulig",
        website="https://timkulig.com/",
    ),
}
