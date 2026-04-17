"""Discover view \u2014 LLMfit-powered model recommendations from the remote instance."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QScrollArea, QPushButton, QLineEdit,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, StatusPill


_FIT_LEVEL = {"perfect": "ok", "good": "info", "marginal": "warn", "too_tight": "err"}

USE_CASES = [
    ("all", "All"), ("general", "General"), ("coding", "Coding"),
    ("reasoning", "Reasoning"), ("chat", "Chat"),
    ("multimodal", "Multimodal"), ("embedding", "Embedding"),
]


class DiscoverView(QWidget):
    download_requested = Signal(str, str)  # model name, best_quant
    refresh_requested = Signal(str, str)   # use_case, search

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        head.addWidget(SectionHeader("LLMFIT", "Discover Models"))
        head.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search models...")
        self.search_input.setFixedWidth(200)
        self.search_input.returnPressed.connect(self._refresh)
        head.addWidget(self.search_input)

        self.filter = QComboBox()
        for key, label in USE_CASES:
            self.filter.addItem(label, key)
        self.filter.currentIndexChanged.connect(lambda _: self._refresh())
        head.addWidget(self.filter)

        self.refresh_btn = QPushButton("\u21BB")
        self.refresh_btn.setFixedWidth(36)
        self.refresh_btn.clicked.connect(self._refresh)
        head.addWidget(self.refresh_btn)
        root.addLayout(head)

        # Status
        self.status_lbl = QLabel("LLMfit must be running on the instance. Go to Dashboard \u2192 Setup.")
        self.status_lbl.setProperty("role", "muted")
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl)

        # Model list scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(t.SPACE_3)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.store.remote_models_changed.connect(self._render)
        self.store.setup_status_changed.connect(self._update_status)

    def _refresh(self):
        uc = self.filter.currentData() or "all"
        search = self.search_input.text().strip()
        self.refresh_requested.emit(uc, search)

    def _update_status(self, s):
        if s.llmfit_serving:
            self.status_lbl.setText(f"LLMfit active \u2714  \u00b7  Showing models ranked for this instance's hardware.")
            self.status_lbl.setStyleSheet(f"color: {t.OK};")
        else:
            self.status_lbl.setText("LLMfit not running. Go to Dashboard \u2192 Setup first.")
            self.status_lbl.setStyleSheet(f"color: {t.WARN};")

    def _render(self, models):
        while self.list_lay.count():
            w = self.list_lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        if not models:
            lbl = QLabel("No models found. Try a different filter or install LLMfit first.")
            lbl.setProperty("role", "muted")
            self.list_lay.addWidget(lbl)
            self.list_lay.addStretch()
            return

        for m in models:
            card = GlassCard()
            # Header row: name + fit pill
            header = QHBoxLayout()
            title = QLabel(m.name)
            title.setProperty("role", "title")
            header.addWidget(title)
            header.addStretch()
            level = _FIT_LEVEL.get(m.fit_level, "info")
            header.addWidget(StatusPill(m.fit_label or m.fit_level.upper(), level))
            card.body().addLayout(header)

            # Meta row
            meta_parts = []
            if m.provider:
                meta_parts.append(m.provider)
            meta_parts.append(f"{m.params_b:.1f}B")
            if m.best_quant:
                meta_parts.append(m.best_quant)
            if m.use_case:
                meta_parts.append(m.use_case)
            if m.estimated_tps:
                meta_parts.append(f"~{m.estimated_tps:.0f} tok/s")
            if m.memory_required_gb:
                meta_parts.append(f"~{m.memory_required_gb:.1f} GB")
            meta = QLabel("  \u00b7  ".join(meta_parts))
            meta.setProperty("role", "muted")
            card.body().addWidget(meta)

            # Score bar
            score_row = QHBoxLayout()
            score_lbl = QLabel(f"Score: {m.score:.0f}")
            score_lbl.setStyleSheet(f"color: {t.ACCENT}; font-weight: bold;")
            score_row.addWidget(score_lbl)

            if m.run_mode:
                run = QLabel(f"Run: {m.run_mode.upper()}")
                run.setProperty("role", "muted")
                score_row.addWidget(run)

            score_row.addStretch()

            # Download button
            dl_btn = QPushButton("Download to Instance")
            dl_btn.setEnabled(m.fit_level != "too_tight")
            dl_btn.clicked.connect(
                lambda _=False, name=m.name, q=m.best_quant:
                    self.download_requested.emit(name, q))
            score_row.addWidget(dl_btn)
            card.body().addLayout(score_row)

            self.list_lay.addWidget(card)

        self.list_lay.addStretch()
        self.status_lbl.setText(f"{len(models)} models ranked for this instance.")
        self.status_lbl.setStyleSheet(f"color: {t.OK};")
