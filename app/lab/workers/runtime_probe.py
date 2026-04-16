from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.runtime import detect_runtime


class RuntimeProbeWorker(QThread):
    detected = Signal(object)

    def __init__(self, configured_path: str | None = None, parent=None):
        super().__init__(parent)
        self.configured_path = configured_path

    def run(self):
        self.detected.emit(detect_runtime(self.configured_path))
