"""Diagnostics view \u2014 lists all current issues with severity, detail, and fix."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, HealthDot,
)
from app.lab.services.diagnostics import collect_diagnostics
from app.lab.state.store import LabStore


class DiagnosticsView(QWidget):
    navigate_requested = Signal(str)     # nav key, e.g. "runtime"
    rescan_library_requested = Signal()

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)
        root.addWidget(SectionHeader("HEALTH", "Diagnostics"))

        self.body_lay = QVBoxLayout()
        self.body_lay.setSpacing(t.SPACE_3)
        root.addLayout(self.body_lay)
        root.addStretch()

        for sig in (self.store.hardware_changed, self.store.runtime_changed,
                    self.store.library_changed):
            sig.connect(lambda *_: self._refresh())
        self._refresh()

    def _refresh(self):
        items = collect_diagnostics(
            self.store.hardware, self.store.runtime, self.store.library,
        )
        self.store.set_diagnostics(items)

        while self.body_lay.count():
            w = self.body_lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        if not items:
            card = GlassCard()
            lbl = QLabel("All clear. Nothing to fix right now.")
            lbl.setProperty("role", "title")
            card.body().addWidget(lbl)
            self.body_lay.addWidget(card)
            return

        for it in items:
            card = GlassCard()
            head = QHBoxLayout()
            head.setSpacing(t.SPACE_3)
            head.addWidget(HealthDot(it.level))
            title = QLabel(it.title)
            title.setProperty("role", "title")
            head.addWidget(title)
            head.addStretch()
            card.body().addLayout(head)
            det = QLabel(it.detail)
            det.setWordWrap(True)
            det.setProperty("role", "muted")
            card.body().addWidget(det)
            if it.fix_action:
                actions = QHBoxLayout()
                actions.addStretch()
                btn = QPushButton(self._label_for(it.fix_action))
                btn.clicked.connect(lambda _=False, a=it.fix_action: self._run_fix(a))
                actions.addWidget(btn)
                card.body().addLayout(actions)
            self.body_lay.addWidget(card)

    def _label_for(self, action: str) -> str:
        return {
            "open_runtime": "Open Runtime",
            "rescan_library": "Rescan Library",
        }.get(action, "Fix")

    def _run_fix(self, action: str):
        if action == "open_runtime":
            self.navigate_requested.emit("runtime")
        elif action == "rescan_library":
            self.rescan_library_requested.emit()
