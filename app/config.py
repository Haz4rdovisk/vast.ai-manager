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
            allowed = AppConfig.__dataclass_fields__
            return AppConfig(**{k: v for k, v in data.items() if k in allowed})
        except (json.JSONDecodeError, OSError, TypeError):
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
