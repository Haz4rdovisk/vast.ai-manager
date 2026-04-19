from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from app.models import AppConfig


DEFAULT_CONFIG_PATH = Path.home() / ".vastai-app" / "config.json"


class ConfigStore:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH):
        self.path = Path(path)

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppConfig()
        try:
            data = self._migrate(data)
            allowed = AppConfig.__dataclass_fields__
            return AppConfig(**{k: v for k, v in data.items() if k in allowed})
        except (TypeError, ValueError):
            return AppConfig()

    @staticmethod
    def _migrate(raw: dict) -> dict:
        v = int(raw.get("schema_version", 1) or 1)
        if v < 3:
            raw.setdefault("port_map", {})
            raw.setdefault("instance_filters", {})
            raw.setdefault("bulk_confirm_threshold", 1)
            raw["schema_version"] = 3
        pm = raw.get("port_map") or {}
        raw["port_map"] = {int(k): int(v) for k, v in pm.items()}
        return raw

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
