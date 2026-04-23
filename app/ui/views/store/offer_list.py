"""Scrollable list/grid of marketplace offers."""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.models_rental import Offer
from app.ui.components import icons
from app.ui.components.primitives import GlassCard, IconButton, SkeletonBlock
from app.ui.views.store.offer_card import OfferCard


_CARD_RENDER_BATCH_SIZE = 16
_SCROLL_PREFETCH_PX = 900


class OfferList(QWidget):
    rent_clicked = Signal(object)       # Offer
    details_clicked = Signal(object)    # Offer
    gpu_count_selected = Signal(object, object)
    market_filters_reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: list[OfferCard] = []
        self.gpu_count_buttons: dict[str, QPushButton] = {}
        self._gpu_button_values: dict[QPushButton, tuple[object, object]] = {}
        self._offers: list[Offer] = []
        self._next_offer_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_3)

        self.toolbar = QHBoxLayout()
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        self.toolbar.setSpacing(t.SPACE_5)
        self._build_gpu_count_picker()
        root.addLayout(self.toolbar)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Offers")
        title.setProperty("role", "title")
        self.count_lbl = QLabel("Ready")
        self.count_lbl.setProperty("role", "muted")
        header.addWidget(title)
        header.addWidget(self.count_lbl)
        header.addStretch()
        root.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.container = QWidget()
        self.col = QVBoxLayout(self.container)
        self.col.setContentsMargins(0, 0, t.SPACE_4, 0)
        self.col.setSpacing(t.SPACE_3)
        self.col.addStretch()
        self.scroll.setWidget(self.container)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_render_more)
        root.addWidget(self.scroll, 1)

        self.set_empty("Choose filters, then search Vast.ai offers.")

    def _build_gpu_count_picker(self) -> None:
        label = QLabel("#GPUs:")
        label.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 850;"
        )
        self.toolbar.addWidget(label)

        group = QButtonGroup(self)
        group.setExclusive(True)
        for text, min_count, max_count in [
            ("ANY", None, None),
            ("1X", 1, 1),
            ("2X", 2, 2),
            ("4X", 4, 4),
            ("8X", 8, 8),
            ("9+", 9, None),
        ]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {t.TEXT_MID};"
                f" border: none; border-bottom: 2px solid transparent;"
                f" border-radius: 0; padding: 8px 9px;"
                f" font-size: 13px; font-weight: 850; min-width: 28px; }}"
                f"QPushButton:hover {{ color: {t.TEXT_HI}; background: rgba(255,255,255,0.04); }}"
                f"QPushButton:checked {{ color: {t.ACCENT}; border-bottom: 2px solid {t.ACCENT}; background: transparent; }}"
            )
            btn.clicked.connect(
                lambda _checked=False, lo=min_count, hi=max_count: self.gpu_count_selected.emit(lo, hi)
            )
            group.addButton(btn)
            self.toolbar.addWidget(btn)
            self.gpu_count_buttons[text] = btn
            self._gpu_button_values[btn] = (min_count, max_count)
        self.gpu_count_buttons["ANY"].setChecked(True)

    def set_market_filters(
        self,
        type_widget: QComboBox,
        gpu_widget: QComboBox,
        region_widget: QComboBox,
        sort_widget: QComboBox,
    ) -> None:
        for widget, width in [
            (type_widget, 176),
            (gpu_widget, 154),
            (region_widget, 162),
            (sort_widget, 188),
        ]:
            self.toolbar.addWidget(self._market_select(widget, width))
        self.market_reset = IconButton(icons.CLOSE, "Reset store filters")
        self.market_reset.clicked.connect(self.market_filters_reset_requested.emit)
        self.toolbar.addWidget(self.market_reset)
        self.toolbar.addStretch()

    def set_gpu_count_choice(self, min_count: object, max_count: object) -> None:
        target = (min_count, max_count)
        match = None
        for btn, values in self._gpu_button_values.items():
            if values == target:
                match = btn
                break
        if match is not None:
            match.setChecked(True)

    def _market_select(self, widget: QComboBox, width: int) -> QWidget:
        widget.setMinimumWidth(width)
        widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Clear local style to let global theme (SURFACE_3 rounded chips) take over
        widget.setStyleSheet("")
        return widget

    def set_loading(self) -> None:
        self._clear()
        self.count_lbl.setText("Loading offers...")
        for _ in range(4):
            self.col.insertWidget(self.col.count() - 1, self._skeleton_card())

    def _skeleton_card(self) -> GlassCard:
        card = GlassCard(raised=True)
        card.setMinimumHeight(318)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.body().setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        card.body().setSpacing(t.SPACE_4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(t.SPACE_5)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(10)
        title_col.addWidget(SkeletonBlock(230, 14))
        title_col.addWidget(SkeletonBlock(360, 30))
        top.addLayout(title_col, 1)

        price_col = QVBoxLayout()
        price_col.setContentsMargins(0, 0, 0, 0)
        price_col.setSpacing(7)
        price_col.addWidget(SkeletonBlock(130, 30), 0, Qt.AlignRight)
        price_col.addWidget(SkeletonBlock(104, 13), 0, Qt.AlignRight)
        price_col.addWidget(SkeletonBlock(120, 12), 0, Qt.AlignRight)
        top.addLayout(price_col)
        card.body().addLayout(top)

        badges = QHBoxLayout()
        badges.setContentsMargins(0, 0, 0, 0)
        badges.setSpacing(t.SPACE_4)
        for width in (84, 80, 78):
            badges.addWidget(SkeletonBlock(width, 14))
        badges.addStretch(1)
        card.body().addLayout(badges)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(t.SPACE_4)
        grid.setVerticalSpacing(t.SPACE_5)
        block_widths = [158, 138, 158, 190, 126]
        for row in range(2):
            for col, width in enumerate(block_widths):
                if row == 1 and col == 4:
                    continue
                cell = QWidget()
                cell_lay = QVBoxLayout(cell)
                cell_lay.setContentsMargins(0, 0, 0, 0)
                cell_lay.setSpacing(7)
                cell_lay.addWidget(SkeletonBlock(max(76, width - 34), 12))
                cell_lay.addWidget(SkeletonBlock(width, 19))
                cell_lay.addWidget(SkeletonBlock(max(92, width - 18), 12))
                grid.addWidget(cell, row, col)
                grid.setColumnStretch(col, 1)

        actions = QWidget()
        actions_lay = QHBoxLayout(actions)
        actions_lay.setContentsMargins(0, t.SPACE_3, 0, 0)
        actions_lay.setSpacing(t.SPACE_2)
        actions_lay.addWidget(SkeletonBlock(90, 38))
        actions_lay.addWidget(SkeletonBlock(128, 38))
        grid.addWidget(actions, 1, 4, Qt.AlignRight | Qt.AlignBottom)
        card.body().addLayout(grid)
        return card

    def set_results(self, offers: list[Offer]) -> None:
        if not offers:
            self.set_empty("No offers matched those filters.")
            return
        self._clear()
        self._offers = list(offers)
        self._next_offer_index = 0
        self._update_render_count()
        self._render_next_batch(_CARD_RENDER_BATCH_SIZE)

    def set_error(self, message: str) -> None:
        self._clear()
        self.count_lbl.setText("Search failed")
        card = GlassCard()
        title = QLabel("Marketplace request failed")
        title.setProperty("role", "title")
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setProperty("role", "muted")
        retry_hint = QLabel("Check the API key and network connection, then search again.")
        retry_hint.setWordWrap(True)
        retry_hint.setProperty("role", "muted")
        card.body().addWidget(title)
        card.body().addWidget(msg)
        card.body().addWidget(retry_hint)
        self.col.insertWidget(self.col.count() - 1, card)

    def set_empty(self, message: str) -> None:
        self._clear()
        self.count_lbl.setText("0 offers")
        card = GlassCard()
        card.setMinimumHeight(180)
        title = QLabel("Store search")
        title.setAlignment(Qt.AlignCenter)
        title.setProperty("role", "title")
        msg = QLabel(message)
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        msg.setProperty("role", "muted")
        card.body().addStretch()
        card.body().addWidget(title)
        card.body().addWidget(msg)
        card.body().addStretch()
        self.col.insertWidget(self.col.count() - 1, card)

    def _clear(self) -> None:
        self._offers.clear()
        self._next_offer_index = 0
        self.cards.clear()
        self.container.setUpdatesEnabled(False)
        try:
            while self.col.count() > 1:
                item = self.col.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
        finally:
            self.container.setUpdatesEnabled(True)

    def _render_next_batch(self, count: int = _CARD_RENDER_BATCH_SIZE) -> None:
        if self._next_offer_index >= len(self._offers):
            return

        end = min(self._next_offer_index + count, len(self._offers))
        self.container.setUpdatesEnabled(False)
        try:
            for offer in self._offers[self._next_offer_index:end]:
                card = OfferCard(offer)
                card.rent_clicked.connect(self.rent_clicked)
                card.details_clicked.connect(self.details_clicked)
                self.cards.append(card)
                self.col.insertWidget(self.col.count() - 1, card)
        finally:
            self.container.setUpdatesEnabled(True)
        self._next_offer_index = end

    def _maybe_render_more(self) -> None:
        if self._next_offer_index >= len(self._offers):
            return
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() - bar.value() <= _SCROLL_PREFETCH_PX:
            self._render_next_batch()

    def _update_render_count(self) -> None:
        total = len(self._offers)
        if total <= 0:
            self.count_lbl.setText("0 offers")
            return
        self.count_lbl.setText(f"{total} offers")
