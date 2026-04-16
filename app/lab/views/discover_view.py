"""Discover view \u2014 filterable list of catalog recommendations ranked for the
current hardware. Drives the Download flow."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea, QPushButton,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import SectionHeader
from app.lab.components.recommendation_card import RecommendationCard
from app.lab.services.catalog import load_catalog
from app.lab.services.recommender import recommend
from app.lab.state.store import LabStore


USE_CASES = [
    ("all", "All models"),
    ("chat", "Chat"),
    ("coding", "Coding"),
    ("quality", "Best quality"),
    ("fast", "Fastest"),
    ("long_context", "Long context"),
    ("low_ram", "Low RAM"),
]


class DiscoverView(QWidget):
    install_requested = Signal(str)   # catalog entry id

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.store.set_catalog(load_catalog())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        head.addWidget(SectionHeader("CATALOG", "Discover"))
        head.addStretch()
        self.filter = QComboBox()
        for key, label in USE_CASES:
            self.filter.addItem(label, key)
        self.filter.currentIndexChanged.connect(lambda _: self._rerank())
        head.addWidget(self.filter)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(t.SPACE_4)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.store.hardware_changed.connect(lambda _: self._rerank())
        self.store.catalog_changed.connect(lambda _: self._rerank())
        self._cards: dict[str, RecommendationCard] = {}
        self._rerank()

    def _rerank(self):
        use_case = self.filter.currentData()
        uc = None if use_case == "all" else use_case
        recs = recommend(self.store.hardware, self.store.catalog, uc)
        self.store.set_recommendations(recs)

        while self.list_lay.count():
            w = self.list_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._cards = {}
        for r in recs:
            card = RecommendationCard(r)
            card.install_requested.connect(self.install_requested.emit)
            self.list_lay.addWidget(card)
            self._cards[r.entry.id] = card
        self.list_lay.addStretch()

    def on_progress(self, entry_id: str, d: int, total: int, speed: float):
        card = self._cards.get(entry_id)
        if card and hasattr(card, 'set_progress'):
            card.set_progress(d, total, speed)

    def on_install_result(self, entry_id: str, ok: bool):
        card = self._cards.get(entry_id)
        if card and hasattr(card, 'set_install_state'):
            card.set_install_state("done" if ok else "failed")
