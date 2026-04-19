"""Scrollable list/grid of marketplace offers."""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
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
from app.ui.components.primitives import GlassCard, SkeletonBlock
from app.ui.views.store.offer_card import OfferCard


class OfferList(QWidget):
    rent_clicked = Signal(object)       # Offer
    details_clicked = Signal(object)    # Offer
    gpu_count_selected = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: list[OfferCard] = []
        self.gpu_count_buttons: dict[str, QPushButton] = {}
        self._gpu_button_values: dict[QPushButton, tuple[object, object]] = {}

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
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(t.SPACE_3)
        self.col.addStretch()
        self.scroll.setWidget(self.container)
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
                f"QPushButton {{ background: transparent; color: {t.TEXT_HI};"
                f" border: none; border-radius: 0; padding: 8px 9px;"
                f" font-size: 13px; font-weight: 850; min-width: 28px; }}"
                f"QPushButton:hover {{ color: {t.TEXT_HERO}; background: rgba(255,255,255,0.06); }}"
                f"QPushButton:checked {{ color: {t.BG_VOID}; background: {t.TEXT_HERO}; }}"
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
            (type_widget, 124),
            (gpu_widget, 138),
            (region_widget, 132),
            (sort_widget, 136),
        ]:
            self.toolbar.addWidget(self._market_select(widget, width))
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
        widget.setStyleSheet(
            f"QComboBox {{ background: transparent; color: {t.TEXT_HI};"
            f" border: none; border-bottom: 1px solid {t.BORDER_HI};"
            f" border-radius: 0; padding: 6px 24px 7px 0;"
            f" font-size: 14px; font-weight: 750; }}"
            f"QComboBox:hover {{ color: {t.TEXT_HERO}; border-bottom-color: {t.ACCENT_SOFT}; }}"
            f"QComboBox::drop-down {{ border: none; width: 22px; }}"
            f"QComboBox QAbstractItemView {{ background: {t.SURFACE_2};"
            f" color: {t.TEXT_HI}; selection-background-color: {t.ACCENT};"
            f" border: 1px solid {t.BORDER_MED}; }}"
        )
        return widget

    def set_loading(self) -> None:
        self._clear()
        self.count_lbl.setText("Loading offers...")
        for _ in range(4):
            card = GlassCard()
            card.body().addWidget(SkeletonBlock(280, 22))
            card.body().addWidget(SkeletonBlock(520, 14))
            card.body().addWidget(SkeletonBlock(460, 14))
            self.col.insertWidget(self.col.count() - 1, card)

    def set_results(self, offers: list[Offer]) -> None:
        self._clear()
        self.count_lbl.setText(f"{len(offers)} offers")
        if not offers:
            self.set_empty("No offers matched those filters.")
            return
        for offer in offers:
            card = OfferCard(offer)
            card.rent_clicked.connect(self.rent_clicked)
            card.details_clicked.connect(self.details_clicked)
            self.cards.append(card)
            self.col.insertWidget(self.col.count() - 1, card)

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
        self.cards.clear()
        while self.col.count() > 1:
            item = self.col.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
