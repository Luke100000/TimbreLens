from pathlib import Path

from timbrelens.models import Catalog, Track


def load(path: Path) -> Catalog:
    raise NotImplementedError("Catalog loading is not implemented.")


def save(catalog: Catalog, path: Path) -> None:
    raise NotImplementedError("Deterministic catalog serialization is not implemented.")


def merge(catalog: Catalog, tracks: list[Track]) -> Catalog:
    raise NotImplementedError("Catalog merging is not implemented.")
