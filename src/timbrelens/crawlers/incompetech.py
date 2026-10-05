from pathlib import Path

from timbrelens.models import Track


def crawl(cache: Path, previews: Path, duration: float = 20.0) -> list[Track]:
    """Cache downloads, write normalized previews, and return track metadata."""
    raise NotImplementedError("The Incompetech crawler is not implemented.")
