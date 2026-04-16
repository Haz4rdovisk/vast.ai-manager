"""Runtime view \u2014 llama.cpp status + install/validate actions."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
)
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, StatusPill, KeyValueRow,
)
from app.lab.state.models import RuntimeStatus
from app.lab.state.store import LabStore
from app.lab.workers.runtime_probe import RuntimeProbeWorker


INSTALL_INSTRUCTIONS = (
    "Download a prebuilt llama.cpp binary from "
    "https://github.com/ggerganov/llama.cpp/releases \u2014 pick a build "
    "matching your GPU (e.g. llama-bin-win-cuda-x64). Extract and "
    "either add the folder to PATH or point Runtime at llama-server.exe."
)


class RuntimeView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._worker: RuntimeProbeWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)
        root.addWidget(SectionHeader("INFERENCE", "Runtime"))

        self.card = GlassCard(raised=True)
        status_row = QHBoxLayout()
        title = QLabel("llama.cpp")
        title.setProperty("role", "title")
        status_row.addWidget(title)
        status_row.addStretch()
        self.pill = StatusPill("Detecting\u2026", "info")
        status_row.addWidget(self.pill)
        self.card.body().addLayout(status_row)

        self.summary = QLabel("Looking for the llama.cpp runtime on your system.")
        self.summary.setWordWrap(True)
        self.summary.setProperty("role", "muted")
        self.card.body().addWidget(self.summary)

        self.row_version = KeyValueRow("Version", "\u2014")
        self.row_backend = KeyValueRow("Backend", "\u2014")
        self.row_path = KeyValueRow("Binary", "\u2014")
        for r in [self.row_version, self.row_backend, self.row_path]:
            self.card.body().addWidget(r)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(t.SPACE_3)
        self.revalidate_btn = QPushButton("Revalidate")
        self.revalidate_btn.setProperty("variant", "ghost")
        self.revalidate_btn.clicked.connect(lambda: self.kick_probe())
        self.locate_btn = QPushButton("Locate binary\u2026")
        self.locate_btn.setProperty("variant", "ghost")
        self.locate_btn.clicked.connect(self._pick_binary)
        self.install_btn = QPushButton("Install guide")
        self.install_btn.clicked.connect(self._show_install)
        btn_row.addWidget(self.revalidate_btn)
        btn_row.addWidget(self.locate_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.install_btn)
        self.card.body().addLayout(btn_row)
        root.addWidget(self.card)

        self.install_panel = GlassCard()
        self.install_panel.body().addWidget(SectionHeader("SETUP", "Install llama.cpp"))
        guide = QLabel(INSTALL_INSTRUCTIONS)
        guide.setWordWrap(True)
        self.install_panel.body().addWidget(guide)
        self.install_panel.setVisible(False)
        root.addWidget(self.install_panel)

        root.addStretch()
        self.store.runtime_changed.connect(self.render)

    def kick_probe(self, configured_path: str | None = None):
        if self._worker and self._worker.isRunning():
            return
        self._worker = RuntimeProbeWorker(configured_path, self)
        self._worker.detected.connect(self.store.set_runtime)
        self._worker.start()

    def render(self, rs: RuntimeStatus):
        if rs.installed and rs.validated:
            self.pill.set_status("READY", "ok")
            self.summary.setText("Runtime detected and validated.")
        elif rs.installed:
            self.pill.set_status("PARTIAL", "warn")
            self.summary.setText("Binary found but version could not be confirmed.")
        else:
            self.pill.set_status("MISSING", "err")
            self.summary.setText(rs.error or "llama.cpp not found.")
        self.row_version.set_value(rs.version or "\u2014")
        self.row_backend.set_value((rs.backend or "\u2014").upper())
        self.row_path.set_value(rs.binary_path or "\u2014")

    def _pick_binary(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate llama.cpp binary", "",
            "Executables (*.exe);;All files (*)",
        )
        if path:
            self.kick_probe(path)

    def _show_install(self):
        self.install_panel.setVisible(not self.install_panel.isVisible())
