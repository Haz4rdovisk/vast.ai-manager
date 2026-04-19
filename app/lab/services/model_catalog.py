"""Bundled model catalog used as hardware-agnostic input for local scoring."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CatalogEntry:
    name: str
    provider: str = ""
    params_b: float = 0.0
    context_length: int = 0
    use_case: str = ""
    category: str = ""
    best_quant: str = ""
    memory_required_gb: float = 0.0
    estimated_tps_7b: float = 0.0
    gguf_sources: list[str] = field(default_factory=list)


def _asset_path() -> Path:
    return Path(__file__).parent.parent / "assets" / "models_catalog.json"


@dataclass
class ModelCatalog:
    entries: list[CatalogEntry]

    @classmethod
    def bundled(cls) -> "ModelCatalog":
        raw = json.loads(_asset_path().read_text(encoding="utf-8"))
        return cls(entries=[CatalogEntry(**entry) for entry in raw])

    def filter(self, use_case: str = "", search: str = "") -> list[CatalogEntry]:
        entries = list(self.entries)

        if use_case and use_case != "all":
            entries = [
                entry
                for entry in entries
                if entry.use_case.lower() == use_case.lower()
            ]

        if search:
            needle = search.lower()
            entries = [
                entry
                for entry in entries
                if needle in entry.name.lower() or needle in entry.provider.lower()
            ]

        return entries
