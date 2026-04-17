"""Discover view — LLMfit model recommendations. Glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QScrollArea, QPushButton, QLineEdit,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, StatusPill


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
        self.ctx_lbl = QLabel("Dashboard \u203a Discover Models")
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
        sub = QLabel("Powered by LLMfit \u2014 AI-ranked models for your hardware")
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
            "LLMfit must be running. Go to Dashboard \u2192 Setup."
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
        self.store.remote_models_changed.connect(self._render)
        self.store.setup_status_changed.connect(self._update_status)
        self.store.instance_state_updated.connect(
            lambda iid, _: self._check_busy(iid)
        )

    def _check_busy(self, iid: int):
        if iid == self.store.selected_instance_id:
            busy = "discover" in self.store.get_state(iid).busy_keys
            self.refresh_btn.setEnabled(not busy)
            self.search_input.setEnabled(not busy)
            self.filter.setEnabled(not busy)

    def _on_instance_changed(self, iid: int):
        if iid:
            self.ctx_lbl.setText(
                f"Dashboard \u203a Instance #{iid} \u203a Discover"
            )
        else:
            self.ctx_lbl.setText("Dashboard \u203a Discover Models")

    def _refresh(self):
        iid = self.store.selected_instance_id
        if iid and "discover" in self.store.get_state(iid).busy_keys:
            return
        uc = self.filter.currentData() or "all"
        search = self.search_input.text().strip()
        self.refresh_requested.emit(uc, search)

    def _update_status(self, s):
        if s.llmfit_serving:
            self.status_lbl.setText(
                "\u2714 LLMfit active \u00b7 Showing models ranked for "
                "this machine\u2019s hardware."
            )
            self.status_lbl.setStyleSheet(f"color: {t.OK};")
        else:
            self.status_lbl.setText(
                "\u26A0 LLMfit not running. Install from Dashboard setup."
            )
            self.status_lbl.setStyleSheet(f"color: {t.WARN};")

    def _render(self, models):
        if models is None:
            models = []

        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not models:
            iid = self.store.selected_instance_id
            st = self.store.get_state(iid) if iid else None
            is_busy = st and (
                "discover" in st.busy_keys
                or "setup" in st.busy_keys
                or "probe" in st.busy_keys
            )
            if is_busy:
                msg = "Searching for models matching your hardware..."
                if st and "setup" in st.busy_keys:
                    msg = "Waking up Model Advisor (LLMfit)... almost there."
                lbl = QLabel(msg)
            else:
                lbl = QLabel(
                    "No models found. Try a different filter or search."
                )
            lbl.setProperty("role", "muted")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"padding: 60px 0; font-size: 12pt;")
            self.list_lay.addWidget(lbl)
            self.list_lay.addStretch()
            return

        for m in models:
            card = GlassCard()

            # Row 1: Title + Fit pill
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

            # Row 2: Meta
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
            meta = QLabel("  \u00b7  ".join(meta_parts))
            meta.setProperty("role", "muted")
            card.body().addWidget(meta)

            # Row 3: Score + Download
            score_row = QHBoxLayout()
            score_lbl = QLabel(f"Rank Score: {m.score:.0f}")
            score_lbl.setStyleSheet(
                f"color: {t.ACCENT}; font-weight: bold; font-size: 12pt;"
            )
            score_row.addWidget(score_lbl)
            score_row.addStretch()

            dl_btn = QPushButton("Download")
            dl_btn.setEnabled(m.fit_level != "too_tight")
            dl_btn.clicked.connect(
                lambda _=False, name=m.name, q=m.best_quant:
                    self.download_requested.emit(name, q)
            )
            score_row.addWidget(dl_btn)
            card.body().addLayout(score_row)

            self.list_lay.addWidget(card)

        self.list_lay.addStretch()
