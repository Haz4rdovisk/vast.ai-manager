"""Benchmark view \u2014 pick a model, run a short generation, record tokens/s."""
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QScrollArea,
)
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, MetricTile, StatusPill,
)
from app.lab.state.models import BenchmarkResult
from app.lab.state.store import LabStore
from app.lab.workers.bench_worker import BenchmarkWorker


class BenchmarkView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._worker: BenchmarkWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)
        root.addWidget(SectionHeader("PERFORMANCE", "Benchmark"))

        controls = GlassCard()
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(t.SPACE_3)
        self.model_pick = QComboBox()
        self.model_pick.setMinimumWidth(300)
        self.run_btn = QPushButton("Run benchmark")
        self.run_btn.clicked.connect(self._run)
        self.pill = StatusPill("Idle", "info")
        ctrl_row.addWidget(QLabel("Model:"))
        ctrl_row.addWidget(self.model_pick, 1)
        ctrl_row.addWidget(self.run_btn)
        ctrl_row.addWidget(self.pill)
        controls.body().addLayout(ctrl_row)
        root.addWidget(controls)

        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(t.SPACE_4)
        self.tps_tile = MetricTile("Tokens / sec", "\u2014", "generation")
        self.ttft_tile = MetricTile("TTFT", "\u2014", "ms to first token")
        self.prompt_tile = MetricTile("Prompt eval", "\u2014", "tokens / sec")
        tiles_row.addWidget(self.tps_tile)
        tiles_row.addWidget(self.ttft_tile)
        tiles_row.addWidget(self.prompt_tile)
        root.addLayout(tiles_row)

        self.history_card = GlassCard()
        self.history_card.body().addWidget(SectionHeader("HISTORY", "Past runs"))
        self.history_lay = QVBoxLayout()
        self.history_lay.setSpacing(4)
        self.history_card.body().addLayout(self.history_lay)
        root.addWidget(self.history_card)
        root.addStretch()

        self.store.library_changed.connect(self._refresh_models)
        self.store.benchmarks_changed.connect(self._render_history)
        self._refresh_models(self.store.library)

    def select_model(self, path: str):
        idx = self.model_pick.findData(path)
        if idx >= 0:
            self.model_pick.setCurrentIndex(idx)

    def _refresh_models(self, items):
        self.model_pick.clear()
        for m in items:
            if m.valid:
                self.model_pick.addItem(m.name, m.path)
        self.run_btn.setEnabled(self.model_pick.count() > 0)

    def _run(self):
        path = self.model_pick.currentData()
        if not path:
            return
        if self._worker and self._worker.isRunning():
            return
        if not self.store.runtime.installed:
            self.pill.set_status("Runtime missing", "err")
            return
        self.pill.set_status("Running\u2026", "warn")
        self.run_btn.setEnabled(False)
        self._worker = BenchmarkWorker(self.store.runtime, path, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, r: BenchmarkResult):
        self.tps_tile.set_value(f"{r.tokens_per_sec:.1f}", "generation")
        self.ttft_tile.set_value(f"{r.ttft_ms:.0f} ms", "prompt eval time")
        self.prompt_tile.set_value(f"{r.prompt_eval_tok_per_sec:.1f}", "tokens / sec")
        self.pill.set_status("Done", "ok")
        self.run_btn.setEnabled(True)
        self.store.add_benchmark(r)

    def _on_failed(self, msg: str):
        self.pill.set_status("Failed", "err")
        self.run_btn.setEnabled(True)
        err = QLabel(f"! {msg}")
        err.setStyleSheet(f"color: {t.ERR};")
        err.setWordWrap(True)
        self.history_lay.insertWidget(0, err)

    def _render_history(self, items):
        while self.history_lay.count():
            w = self.history_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for r in reversed(items[-10:]):
            ts = datetime.fromtimestamp(r.timestamp).strftime("%H:%M:%S")
            row = QLabel(
                f"[{ts}]  {r.model_name}  \u2014  {r.tokens_per_sec:.1f} tok/s  "
                f"\u00b7  TTFT {r.ttft_ms:.0f} ms"
            )
            row.setProperty("role", "mono")
            self.history_lay.addWidget(row)
