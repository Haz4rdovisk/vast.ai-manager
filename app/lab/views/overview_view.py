"""Overview \u2014 first view users see. Hero + quick status + top recommendation."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, MetricTile, StatusPill, HealthDot,
)
from app.lab.services.capacity import estimate_capacity
from app.lab.state.store import LabStore


class OverviewView(QWidget):
    navigate_requested = Signal(str)
    install_requested = Signal(str)   # entry id

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        # Hero
        hero = GlassCard(raised=True)
        htitle = QLabel("Local AI Lab")
        htitle.setProperty("role", "display")
        hsub = QLabel("Your workstation, your models. Offline inference with llama.cpp.")
        hsub.setProperty("role", "muted")
        hsub.setWordWrap(True)
        hero.body().addWidget(htitle)
        hero.body().addWidget(hsub)

        cta_row = QHBoxLayout()
        self.cta_primary = QPushButton("Discover models")
        self.cta_primary.clicked.connect(lambda: self.navigate_requested.emit("discover"))
        self.cta_secondary = QPushButton("Check runtime")
        self.cta_secondary.setProperty("variant", "ghost")
        self.cta_secondary.clicked.connect(lambda: self.navigate_requested.emit("runtime"))
        cta_row.addWidget(self.cta_primary)
        cta_row.addWidget(self.cta_secondary)
        cta_row.addStretch()
        hero.body().addLayout(cta_row)
        root.addWidget(hero)

        # Status strip
        strip = QHBoxLayout()
        strip.setSpacing(t.SPACE_4)
        self.hw_tile = MetricTile("Machine", "Detecting\u2026", "")
        self.rt_tile = MetricTile("Runtime", "Detecting\u2026", "")
        self.lib_tile = MetricTile("Library", "\u2014", "")
        self.health_tile = MetricTile("Health", "\u2014", "")
        strip.addWidget(self.hw_tile)
        strip.addWidget(self.rt_tile)
        strip.addWidget(self.lib_tile)
        strip.addWidget(self.health_tile)
        root.addLayout(strip)

        # Top recommendation card
        self.rec_card = GlassCard()
        self.rec_title = QLabel("Loading recommendation\u2026")
        self.rec_title.setProperty("role", "title")
        self.rec_body = QLabel("")
        self.rec_body.setWordWrap(True)
        self.rec_body.setProperty("role", "muted")
        self.rec_install = QPushButton("Install")
        self.rec_install.setVisible(False)
        self._rec_id: str | None = None
        self.rec_install.clicked.connect(
            lambda: self._rec_id and self.install_requested.emit(self._rec_id))
        rr = QHBoxLayout()
        rr.addWidget(SectionHeader("BEST FIT", "Top pick"))
        rr.addStretch()
        self.rec_card.body().addLayout(rr)
        self.rec_card.body().addWidget(self.rec_title)
        self.rec_card.body().addWidget(self.rec_body)
        rb = QHBoxLayout()
        rb.addStretch()
        rb.addWidget(self.rec_install)
        self.rec_card.body().addLayout(rb)
        root.addWidget(self.rec_card)

        root.addStretch()

        for sig in (self.store.hardware_changed, self.store.runtime_changed,
                    self.store.library_changed, self.store.recommendations_changed,
                    self.store.diagnostics_changed):
            sig.connect(lambda *_: self._render())
        self._render()

    def _render(self):
        hw = self.store.hardware
        rt = self.store.runtime
        cap = estimate_capacity(hw) if hw.cpu_name else None
        if cap:
            self.hw_tile.set_value(cap.tier.upper(), cap.headline)
        else:
            self.hw_tile.set_value("\u2014", "")
        if rt.installed and rt.validated:
            self.rt_tile.set_value("READY", f"{rt.version}  \u00b7  {rt.backend}")
        elif rt.installed:
            self.rt_tile.set_value("PARTIAL", "version unknown")
        else:
            self.rt_tile.set_value("MISSING", "install required")
        valid = [m for m in self.store.library if m.valid]
        self.lib_tile.set_value(str(len(valid)), f"of {len(self.store.library)} files")
        issues = self.store.diagnostics
        err_n = sum(1 for i in issues if i.level == "err")
        warn_n = sum(1 for i in issues if i.level == "warn")
        if err_n:
            self.health_tile.set_value("ATTENTION", f"{err_n} critical, {warn_n} warnings")
        elif warn_n:
            self.health_tile.set_value("OK", f"{warn_n} warnings")
        else:
            self.health_tile.set_value("HEALTHY", "everything looks good")

        recs = self.store.recommendations
        top = next((r for r in recs if r.fit in ("excellent", "good")), None)
        if top:
            self._rec_id = top.entry.id
            self.rec_title.setText(top.entry.display_name)
            self.rec_body.setText(
                f"{top.entry.notes}  "
                f"Needs ~{top.entry.approx_vram_gb:.0f} GB VRAM \u2014 "
                f"{top.fit} fit on your machine."
            )
            self.rec_install.setVisible(True)
        else:
            self._rec_id = None
            self.rec_title.setText("No recommendation yet")
            self.rec_body.setText("Finish hardware detection to see a top pick.")
            self.rec_install.setVisible(False)
