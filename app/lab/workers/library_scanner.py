from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.library import scan_directory


class LibraryScannerWorker(QThread):
    scanned = Signal(list)   # list[ModelFile]

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        self.scanned.emit(scan_directory(self.path))
