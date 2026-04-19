"""Discover view — LLMfit model recommendations. Glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QScrollArea, QPushButton, QLineEdit,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import GlassCard, StatusPill


_FIT_LEVEL = {"perfect": "ok", "good": "info", "marginal": "warn", "too_tight": "err"}

USE_CASES = [
    ("all", "All"), ("general", "General"), ("coding", "Coding"),
    ("reasoning", "Reasoning"), ("chat", "Chat"),
    ("multimodal", "Multimodal"), ("embedding", "Embedding"),
]


class DiscoverView(QWidget):
    download_requested = Signal(str, str)
    refresh_requested = Signal(str, str)
    back_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        # Breadcrumb
        breadcrumb = QHBoxLayout()
        breadcrumb.setSpacing(t.SPACE_2)
        back_btn = QPushButton("\u2190  Back")
        back_btn.setProperty("variant", "ghost")
        back_btn.setFixedWidth(80)
        back_btn.clicked.connect(self.back_requested.emit)
        breadcrumb.addWidget(back_btn)
        self.ctx_lbl = QLabel("Studio \u203a Discover Models")
        self.ctx_lbl.setStyleSheet(
            f"color: {t.TEXT_MID}; font-weight: 500;"
            f" font-size: {t.FONT_SIZE_SMALL}px;"
        )
        breadcrumb.addWidget(self.ctx_lbl)
        breadcrumb.addStretch()
        root.addLayout(breadcrumb)

        # Header
        head = QHBoxLayout()
        head.setSpacing(t.SPACE_3)
        title_group = QVBoxLayout()
        title_group.setSpacing(4)
        title = QLabel("Model Recommendations")
        title.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 24px; font-weight: 700;"
        )
        sub = QLabel("Locally ranked models for your rented hardware")
        sub.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px;"
        )
        title_group.addWidget(title)
        title_group.addWidget(sub)
        head.addLayout(title_group)
        head.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("\U0001F50D Search models...")
        self.search_input.setFixedWidth(220)
        self.search_input.returnPressed.connect(self._refresh)
        head.addWidget(self.search_input)

        self.filter = QComboBox()
        for key, label in USE_CASES:
            self.filter.addItem(label, key)
        self.filter.currentIndexChanged.connect(lambda _: self._refresh())
        head.addWidget(self.filter)

        self.refresh_btn = QPushButton("\u21BB")
        self.refresh_btn.setFixedWidth(38)
        self.refresh_btn.setFixedHeight(38)
        self.refresh_btn.clicked.connect(self._refresh)
        head.addWidget(self.refresh_btn)
        root.addLayout(head)

        # Status
        self.status_lbl = QLabel(
            "Select an instance and refresh to score the local catalog."
        )
        self.status_lbl.setProperty("role", "muted")
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl)

        # Model list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(t.SPACE_3)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        # Store connections
        self.store.instance_changed.connect(self._on_instance_changed)
        self.store.scored_models_changed.connect(self._render)
        self.store.instance_state_updated.connect(self._on_instance_state_updated)

    def _check_busy(self, iid: int):
        if iid == self.store.selected_instance_id:
            busy = "discover" in self.store.get_state(iid).busy_keys
            self.refresh_btn.setEnabled(not busy)
            self.search_input.setEnabled(not busy)
            self.filter.setEnabled(not busy)

    def _on_instance_changed(self, iid: int):
        if iid:
            self.ctx_lbl.setText(
                f"Studio \u203a Instance #{iid} \u203a Discover"
            )
            self._render(self.store.get_state(iid).scored_models)
        else:
            self.ctx_lbl.setText("Studio \u203a Discover Models")
            self._render([])

    def _on_instance_state_updated(self, iid: int, _state):
        self._check_busy(iid)
        selected = self.store.selected_instance_id
        if selected:
            self._render(self.store.get_state(selected).scored_models)

    def _refresh(self):
        iid = self.store.selected_instance_id
        if iid and "discover" in self.store.get_state(iid).busy_keys:
            return
        uc = self.filter.currentData() or "all"
        search = self.search_input.text().strip()
        self.refresh_requested.emit(uc, search)

    def _render(self, models):
        if models is None:
            models = []

        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not models:
            lbl = QLabel("No models scored yet. Select an instance to refresh.")
            lbl.setProperty("role", "muted")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("padding: 60px 0; font-size: 12pt;")
            self.list_lay.addWidget(lbl)
            self.list_lay.addStretch()
            return

        other_ids = [
            iid for iid in self.store.all_instance_ids()
            if iid != self.store.selected_instance_id
        ]

        for m in models:
            card = GlassCard()

            header = QHBoxLayout()
            title = QLabel(m.name)
            title.setStyleSheet(
                f"color: {t.TEXT_HI}; font-size: 14pt; font-weight: 700;"
            )
            header.addWidget(title)
            header.addStretch()
            level = _FIT_LEVEL.get(m.fit_level, "info")
            header.addWidget(
                StatusPill(m.fit_label or m.fit_level.upper(), level)
            )
            card.body().addLayout(header)

            meta_parts = [m.provider, f"{m.params_b:.1f}B", m.best_quant, m.use_case]
            if m.estimated_tps:
                meta_parts.append(f"~{m.estimated_tps:.0f} tok/s")
            meta = QLabel("  \u00b7  ".join([part for part in meta_parts if part]))
            meta.setProperty("role", "muted")
            card.body().addWidget(meta)

            chip_row = QHBoxLayout()
            iid = self.store.selected_instance_id
            chip_row.addWidget(
                self._chip(
                    f"#{iid} \u2022 {m.score:.0f}",
                    _FIT_LEVEL.get(m.fit_level, "info"),
                )
            )
            for other in other_ids:
                other_models = self.store.get_state(other).scored_models
                other_entry = next((entry for entry in other_models if entry.name == m.name), None)
                if other_entry is None:
                    continue
                chip_row.addWidget(
                    self._chip(
                        f"#{other} \u2022 {other_entry.score:.0f}",
                        _FIT_LEVEL.get(other_entry.fit_level, "info"),
                    )
                )
            chip_row.addStretch()

            dl_btn = QPushButton("Install")
            dl_btn.setEnabled(m.fit_level != "too_tight")
            dl_btn.clicked.connect(
                lambda _=False, name=m.name, q=m.best_quant:
                    self.download_requested.emit(name, q)
            )
            chip_row.addWidget(dl_btn)
            card.body().addLayout(chip_row)

            self.list_lay.addWidget(card)

        self.list_lay.addStretch()

    def _chip(self, text: str, level: str) -> QLabel:
        palette = {
            "ok": (t.OK, "rgba(80,200,120,0.15)"),
            "info": (getattr(t, "INFO", t.ACCENT), "rgba(124,92,255,0.15)"),
            "warn": (t.WARN, "rgba(255,176,46,0.15)"),
            "err": (t.ERR, "rgba(255,80,80,0.15)"),
        }
        fg, bg = palette.get(level, palette["info"])
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 8px;"
            f" padding: 3px 8px; font-weight: 600; font-size: 10pt;"
        )
        return label
