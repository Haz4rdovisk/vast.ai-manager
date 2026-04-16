"""ModelCard \u2014 premium card for a local model file."""
from __future__ import annotations
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import GlassCard, StatusPill
from app.lab.state.models import ModelFile


def _fmt_size(n: int) -> str:
    gb = n / (1024 ** 3)
    return f"{gb:.1f} GB" if gb >= 1 else f"{n / (1024**2):.0f} MB"


class ModelCard(GlassCard):
    open_requested = Signal(str)     # emits model path
    benchmark_requested = Signal(str)

    def __init__(self, model: ModelFile, parent=None):
        super().__init__(parent=parent)
        self.model = model

        header = QHBoxLayout()
        name = QLabel(model.name)
        name.setProperty("role", "title")
        header.addWidget(name)
        header.addStretch()
        pill = StatusPill(model.quant or "GGUF", "info" if model.valid else "err")
        header.addWidget(pill)
        self.body().addLayout(header)

        meta_line = []
        if model.architecture:
            meta_line.append(model.architecture.upper())
        if model.context_length:
            meta_line.append(f"ctx {model.context_length:,}")
        if model.param_count_b > 0:
            meta_line.append(f"{model.param_count_b:.1f}B params")
        meta_line.append(_fmt_size(model.size_bytes))
        meta = QLabel("  \u00b7  ".join(meta_line))
        meta.setProperty("role", "muted")
        self.body().addWidget(meta)

        if not model.valid:
            err = QLabel(f"\u26a0  {model.error or 'invalid file'}")
            err.setStyleSheet(f"color: {t.ERR};")
            err.setWordWrap(True)
            self.body().addWidget(err)

        path_lbl = QLabel(model.path)
        path_lbl.setProperty("role", "mono")
        path_lbl.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 8pt;")
        self.body().addWidget(path_lbl)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_3)
        self.open_btn = QPushButton("Details")
        self.open_btn.setProperty("variant", "ghost")
        self.open_btn.clicked.connect(lambda: self.open_requested.emit(model.path))
        self.bench_btn = QPushButton("Benchmark")
        self.bench_btn.clicked.connect(lambda: self.benchmark_requested.emit(model.path))
        self.bench_btn.setEnabled(model.valid)
        actions.addWidget(self.open_btn)
        actions.addStretch()
        actions.addWidget(self.bench_btn)
        self.body().addLayout(actions)
