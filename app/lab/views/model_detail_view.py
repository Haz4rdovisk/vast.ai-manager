"""Model detail \u2014 full panel for a single GGUF file."""
from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, KeyValueRow, StatusPill,
)
from app.lab.state.models import ModelFile
from app.lab.state.store import LabStore


class ModelDetailView(QWidget):
    back_requested = Signal()
    benchmark_requested = Signal(str)
    removed = Signal(str)    # path

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._model: ModelFile | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        self.back_btn = QPushButton("\u2190 Library")
        self.back_btn.setProperty("variant", "ghost")
        self.back_btn.clicked.connect(self.back_requested.emit)
        head.addWidget(self.back_btn)
        head.addStretch()
        root.addLayout(head)

        self.title_row = QHBoxLayout()
        self.title = QLabel("\u2014")
        self.title.setProperty("role", "display")
        self.pill = StatusPill("GGUF", "info")
        self.title_row.addWidget(self.title)
        self.title_row.addStretch()
        self.title_row.addWidget(self.pill)
        root.addLayout(self.title_row)

        self.card = GlassCard()
        self.card.body().addWidget(SectionHeader("TECHNICAL", "Metadata"))
        self.row_arch = KeyValueRow("Architecture", "\u2014")
        self.row_params = KeyValueRow("Parameters", "\u2014")
        self.row_ctx = KeyValueRow("Context length", "\u2014")
        self.row_quant = KeyValueRow("Quantization", "\u2014")
        self.row_size = KeyValueRow("File size", "\u2014")
        self.row_path = KeyValueRow("Path", "\u2014")
        for r in [self.row_arch, self.row_params, self.row_ctx,
                   self.row_quant, self.row_size, self.row_path]:
            self.card.body().addWidget(r)
        root.addWidget(self.card)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_3)
        self.bench_btn = QPushButton("Run benchmark")
        self.bench_btn.clicked.connect(
            lambda: self._model and self.benchmark_requested.emit(self._model.path))
        self.remove_btn = QPushButton("Remove file")
        self.remove_btn.setProperty("variant", "danger")
        self.remove_btn.clicked.connect(self._remove)
        actions.addWidget(self.bench_btn)
        actions.addStretch()
        actions.addWidget(self.remove_btn)
        root.addLayout(actions)
        root.addStretch()

    def show_model_by_path(self, path: str):
        m = next((x for x in self.store.library if x.path == path), None)
        if m is None:
            return
        self._model = m
        self.title.setText(m.name)
        self.pill.set_status(m.quant or "GGUF", "info" if m.valid else "err")
        self.row_arch.set_value(m.architecture or "\u2014")
        self.row_params.set_value(f"{m.param_count_b:.2f} B" if m.param_count_b else "\u2014")
        self.row_ctx.set_value(f"{m.context_length:,}" if m.context_length else "\u2014")
        self.row_quant.set_value(m.quant or "\u2014")
        self.row_size.set_value(f"{m.size_bytes / (1024 ** 3):.2f} GB")
        self.row_path.set_value(m.path)

    def _remove(self):
        if self._model is None:
            return
        reply = QMessageBox.question(
            self, "Remove model",
            f"Delete {self._model.name} from disk?\n\n{self._model.path}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            os.remove(self._model.path)
        except OSError as e:
            QMessageBox.critical(self, "Remove failed", str(e))
            return
        self.removed.emit(self._model.path)
        self.back_requested.emit()
