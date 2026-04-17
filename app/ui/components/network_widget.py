"""Custom widget for displaying real-time Network Upload/Download speeds with arrows."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from app import theme as t

class NetworkSpeedWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 160)
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 20, 0, 5)
        lay.setSpacing(0)
        
        lay.addStretch()

        # Hero Area: Arrows & Speeds
        hero_lay = QVBoxLayout()
        hero_lay.setSpacing(t.SPACE_1)

        # Download Row
        self.dl_lay = QHBoxLayout()
        self.dl_icon = QLabel("↓")
        self.dl_icon.setStyleSheet(f"font-size: 22pt; color: {t.TEXT_LOW}; font-weight: 900;")
        self.dl_value = QLabel("0 KB/s")
        self.dl_value.setStyleSheet(f"font-size: 15pt; font-weight: 700; color: {t.TEXT_HI};")
        self.dl_lay.addStretch()
        self.dl_lay.addWidget(self.dl_icon)
        self.dl_lay.addSpacing(t.SPACE_2)
        self.dl_lay.addWidget(self.dl_value)
        self.dl_lay.addStretch()
        hero_lay.addLayout(self.dl_lay)
        
        # Upload Row
        self.ul_lay = QHBoxLayout()
        self.ul_icon = QLabel("↑")
        self.ul_icon.setStyleSheet(f"font-size: 22pt; color: {t.TEXT_LOW}; font-weight: 900;")
        self.ul_value = QLabel("0 KB/s")
        self.ul_value.setStyleSheet(f"font-size: 15pt; font-weight: 700; color: {t.TEXT_HI};")
        self.ul_lay.addStretch()
        self.ul_lay.addWidget(self.ul_icon)
        self.ul_lay.addSpacing(t.SPACE_2)
        self.ul_lay.addWidget(self.ul_value)
        self.ul_lay.addStretch()
        hero_lay.addLayout(self.ul_lay)
        
        lay.addLayout(hero_lay)
        lay.addStretch()

        # Label Area (Matching Gauge titles)
        self.title_lbl = QLabel("NETWORK I/O")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {t.TEXT_MID};")
        lay.addWidget(self.title_lbl)
        
        # Bottom spacer to match Gauge subtext area
        lay.addSpacing(20)

    def set_speeds(self, rx_kbps: float, tx_kbps: float):
        self.dl_value.setText(self._format_speed(rx_kbps))
        self.ul_value.setText(self._format_speed(tx_kbps))
        
        # Visual feedback: dim if zero
        dl_color = t.OK if rx_kbps > 0 else t.TEXT_LOW
        ul_color = t.ACCENT if tx_kbps > 0 else t.TEXT_LOW
        
        self.dl_icon.setStyleSheet(f"font-size: 22pt; color: {dl_color}; font-weight: 900;")
        self.ul_icon.setStyleSheet(f"font-size: 22pt; color: {ul_color}; font-weight: 900;")

    def _format_speed(self, kbps: float) -> str:
        if kbps >= 1024:
            return f"{kbps/1024:.1f} MB/s"
        return f"{kbps:.0f} KB/s"
