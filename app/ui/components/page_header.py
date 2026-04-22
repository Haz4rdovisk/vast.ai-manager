"""Shared top header for primary app sections."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app import theme as t
from app.ui.brand_manager import BrandManager


class PageHeader(QWidget):
    """Consistent page title, subtitle, and optional right-side actions."""

    HEIGHT = 58

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_3)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title_col.setAlignment(Qt.AlignVCenter)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: {t.FONT_SIZE_DISPLAY}px;"
            f" font-weight: 700; font-family: {t.FONT_DISPLAY};"
        )
        title_col.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setWordWrap(False)
        self.subtitle_label.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px;"
            f" font-family: {t.FONT_DISPLAY};"
        )
        title_col.addWidget(self.subtitle_label)
        root.addLayout(title_col, 1)

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(t.SPACE_2)
        self.actions.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addLayout(self.actions)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)
