from collections.abc import Callable
from functools import partial
from pathlib import Path

from timbrelens.crawlers import (
    bandcamp,
    creatorchords,
    github,
    incompetech,
    kongano,
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
    ),
    "freepd": partial(
        github.crawl,
        "0lhi/FreePD",
        "freepd",
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
    "scottbuckley": partial(
        soundcloud.crawl,
        "https://soundcloud.com/scottbuckley",
        "scottbuckley",
        "https://creativecommons.org/licenses/by/4.0/",
        artist="Scott Buckley",
        website="https://www.scottbuckley.com.au/",
        exclude=r"\bremix\b",
    ),
    "tannerhelland": partial(
        github.crawl,
        "tannerhelland/free-music",
        "tannerhelland",
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
        license_override_url="https://timkulig.com/faq",
    ),
}
