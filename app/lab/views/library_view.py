"""Library view \u2014 grid of installed GGUF models + import/scan controls."""
from __future__ import annotations
import os
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QScrollArea, QGridLayout, QMessageBox,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import SectionHeader, GlassCard
from app.lab.components.model_card import ModelCard
from app.lab.state.store import LabStore
from app.lab.workers.library_scanner import LibraryScannerWorker


class LibraryView(QWidget):
    model_detail_requested = Signal(str)
    benchmark_requested = Signal(str)
    navigate_requested = Signal(str)
    models_dir_changed = Signal(str)

    def __init__(self, store: LabStore, models_dir: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.models_dir = models_dir
        self._worker: LibraryScannerWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        head.addWidget(SectionHeader("MODELS", "Library"))
        head.addStretch()
        self.dir_lbl = QLabel(self.models_dir or "No directory configured")
        self.dir_lbl.setProperty("role", "muted")
        head.addWidget(self.dir_lbl)
        self.pick_btn = QPushButton("Change folder\u2026")
        self.pick_btn.setProperty("variant", "ghost")
        self.pick_btn.clicked.connect(self._pick_folder)
        head.addWidget(self.pick_btn)
        self.import_btn = QPushButton("Import GGUF")
        self.import_btn.clicked.connect(self._import_file)
        head.addWidget(self.import_btn)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(t.SPACE_4)
        self.grid.setVerticalSpacing(t.SPACE_4)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        self.empty = GlassCard()
        e_title = QLabel("Your library is empty")
        e_title.setProperty("role", "display")
        e_body = QLabel(
            "Install a recommended model from Discover, import a GGUF you "
            "already have, or point the Library at an existing folder."
        )
        e_body.setWordWrap(True)
        e_body.setProperty("role", "muted")
        e_row = QHBoxLayout()
        e_discover = QPushButton("Go to Discover")
        e_discover.clicked.connect(lambda: self._emit_nav("discover"))
        e_pick = QPushButton("Pick folder")
        e_pick.setProperty("variant", "ghost")
        e_pick.clicked.connect(self._pick_folder)
        e_row.addWidget(e_discover)
        e_row.addWidget(e_pick)
        e_row.addStretch()
        self.empty.body().addWidget(e_title)
        self.empty.body().addWidget(e_body)
        self.empty.body().addLayout(e_row)
        root.addWidget(self.empty)

        self.store.library_changed.connect(self._render)

    def set_models_dir(self, path: str):
        self.models_dir = path
        self.dir_lbl.setText(path or "No directory configured")
        self.models_dir_changed.emit(path)
        self.rescan()

    def rescan(self):
        if not self.models_dir:
            self.store.set_library([])
            return
        if self._worker and self._worker.isRunning():
            return
        self._worker = LibraryScannerWorker(self.models_dir, self)
        self._worker.scanned.connect(self.store.set_library)
        self._worker.start()

    def _render(self, items: list):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not items:
            self.empty.setVisible(True)
            return
        self.empty.setVisible(False)
        for i, m in enumerate(items):
            card = ModelCard(m)
            card.open_requested.connect(self.model_detail_requested.emit)
            card.benchmark_requested.connect(self.benchmark_requested.emit)
            self.grid.addWidget(card, i // 2, i % 2)

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose models folder", self.models_dir)
        if path:
            self.set_models_dir(path)

    def _import_file(self):
        if not self.models_dir:
            QMessageBox.warning(self, "Choose a folder first",
                                "Pick a models folder before importing.")
            return
        src, _ = QFileDialog.getOpenFileName(
            self, "Import GGUF file", "", "GGUF files (*.gguf)",
        )
        if not src:
            return
        dst = os.path.join(self.models_dir, os.path.basename(src))
        if os.path.exists(dst):
            QMessageBox.warning(self, "Already exists",
                                f"{os.path.basename(src)} is already in the library.")
            return
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        self.rescan()

    def _emit_nav(self, key: str):
        self.navigate_requested.emit(key)
