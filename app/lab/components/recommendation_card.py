"""RecommendationCard \u2014 used in Discover view. One per catalog entry."""
from __future__ import annotations
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import GlassCard, StatusPill
from app.lab.state.models import Recommendation


_FIT_LEVEL = {"excellent": "ok", "good": "info", "tight": "warn", "not_recommended": "err"}


class RecommendationCard(GlassCard):
    install_requested = Signal(str)   # emits catalog entry id

    def __init__(self, rec: Recommendation, parent=None):
        super().__init__(parent=parent)
        self.rec = rec

        header = QHBoxLayout()
        title = QLabel(rec.entry.display_name)
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(StatusPill(rec.fit.replace("_", " ").upper(),
                                    _FIT_LEVEL[rec.fit]))
        self.body().addLayout(header)

        meta = QLabel(
            f"{rec.entry.family}  \u00b7  {rec.entry.params_b:.1f}B  \u00b7  "
            f"{rec.entry.quant}  \u00b7  ctx {rec.entry.context_length:,}  \u00b7  "
            f"~{rec.entry.approx_size_gb:.1f} GB"
        )
        meta.setProperty("role", "muted")
        self.body().addWidget(meta)

        if rec.entry.notes:
            note = QLabel(rec.entry.notes)
            note.setWordWrap(True)
            self.body().addWidget(note)

        if rec.reasons:
            reasons = QVBoxLayout()
            reasons.setSpacing(2)
            for r in rec.reasons:
                lbl = QLabel(f"\u2192  {r}")
                lbl.setProperty("role", "muted")
                reasons.addWidget(lbl)
            self.body().addLayout(reasons)

        actions = QHBoxLayout()
        stars = "\u2605" * rec.entry.quality_tier + "\u2606" * (5 - rec.entry.quality_tier)
        quality = QLabel(stars)
        quality.setStyleSheet(f"color: {t.ACCENT}; font-size: 11pt;")
        actions.addWidget(quality)
        actions.addStretch()
        self.install_btn = QPushButton("Install")
        self.install_btn.setEnabled(rec.fit != "not_recommended")
        self.install_btn.clicked.connect(
            lambda: self.install_requested.emit(rec.entry.id))
        actions.addWidget(self.install_btn)
        self.body().addLayout(actions)
