"""Network speed widget — upload/download with colored arrows."""
from __future__ import annotations
from PySide6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from app import theme as t


class NetworkSpeedWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(112, 112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 4)
        lay.setSpacing(0)
        lay.addStretch()

        # Hero: arrows & speeds
        hero_lay = QVBoxLayout()
        hero_lay.setSpacing(t.SPACE_1)

        # Download
        dl_lay = QHBoxLayout()
        self.dl_icon = QLabel("\u2193")
        self.dl_icon.setStyleSheet(
            f"font-size: 24pt; color: {t.TEXT_LOW}; font-weight: 900;"
        )
        self.dl_value = QLabel("0 KB/s")
        self.dl_value.setStyleSheet(
            f"font-size: 16pt; font-weight: 700; color: {t.TEXT_HI};"
        )
        dl_lay.addStretch()
        dl_lay.addWidget(self.dl_icon)
        dl_lay.addSpacing(t.SPACE_2)
        dl_lay.addWidget(self.dl_value)
        dl_lay.addStretch()
        hero_lay.addLayout(dl_lay)

        # Upload
        ul_lay = QHBoxLayout()
        self.ul_icon = QLabel("\u2191")
        self.ul_icon.setStyleSheet(
            f"font-size: 24pt; color: {t.TEXT_LOW}; font-weight: 900;"
        )
        self.ul_value = QLabel("0 KB/s")
        self.ul_value.setStyleSheet(
            f"font-size: 16pt; font-weight: 700; color: {t.TEXT_HI};"
        )
        ul_lay.addStretch()
        ul_lay.addWidget(self.ul_icon)
        ul_lay.addSpacing(t.SPACE_2)
        ul_lay.addWidget(self.ul_value)
        ul_lay.addStretch()
        hero_lay.addLayout(ul_lay)

        lay.addLayout(hero_lay)
        lay.addStretch()

        # Title
        self.title_lbl = QLabel("NETWORK I/O")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet(
            f"font-size: 8pt; font-weight: 700; color: {t.TEXT_MID};"
        )
        lay.addWidget(self.title_lbl)
        lay.addSpacing(30)

    def set_speeds(self, rx_kbps: float, tx_kbps: float):
        self.dl_value.setText(self._format_speed(rx_kbps))
        self.ul_value.setText(self._format_speed(tx_kbps))

        dl_color = t.OK if rx_kbps > 0 else t.TEXT_LOW
        ul_color = t.ACCENT if tx_kbps > 0 else t.TEXT_LOW

        self.dl_icon.setStyleSheet(
            f"font-size: 24pt; color: {dl_color}; font-weight: 900;"
        )
        self.ul_icon.setStyleSheet(
            f"font-size: 24pt; color: {ul_color}; font-weight: 900;"
        )

    def _format_speed(self, kbps: float) -> str:
        if kbps >= 1024:
            return f"{kbps / 1024:.1f} MB/s"
        return f"{kbps:.0f} KB/s"
