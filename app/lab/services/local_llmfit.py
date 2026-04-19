"""Thin wrapper around a locally-installed llmfit binary."""
from __future__ import annotations

import shutil
import sys


class LocalLLMFit:
    binary_name = "llmfit"

    def is_installed(self) -> bool:
        return shutil.which(self.binary_name) is not None

    def install_commands(self) -> list[list[str]]:
        """Return ordered install attempts. Caller runs each until one works."""
        return [
            [sys.executable, "-m", "pip", "install", "--user", "-U", "llmfit"],
        ]
