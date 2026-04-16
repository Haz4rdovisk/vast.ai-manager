"""Loads the bundled curated model catalog."""
from __future__ import annotations
import json
import os
from app.lab.state.models import CatalogEntry


_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "assets", "catalog.json",
)


def load_catalog() -> list[CatalogEntry]:
    try:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    out: list[CatalogEntry] = []
    for item in raw:
        try:
            out.append(CatalogEntry(**item))
        except TypeError:
            continue
    return out
