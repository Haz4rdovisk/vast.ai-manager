"""Dashed wireframe placeholder for the hardware grid — glassmorphism polish."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt
from app import theme as t


class HardwarePlaceholderCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(360)
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Wireframe style: dashed border, no glass fills
        self.setStyleSheet(f"""
            QFrame {{
                border: 2px dashed {t.BORDER_HI};
                border-radius: {t.RADIUS_LG}px;
                background-color: rgba(255, 255, 255, 0.02);
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        lay.setSpacing(t.SPACE_2)
        lay.setAlignment(Qt.AlignCenter)

        icon = QLabel("\u2726")
        icon.setStyleSheet(
            f"font-size: 32pt; color: {t.TEXT_LOW};"
            f" margin-bottom: 8px; border: none; background: transparent;"
        )
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)

        tip = QLabel("Connect a machine to see live metrics here.")
        tip.setStyleSheet(
            f"font-size: 10pt; color: {t.TEXT_LOW};"
            f" font-weight: 500; border: none; background: transparent;"
        )
        tip.setWordWrap(True)
        tip.setMaximumWidth(240)
        tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(tip)
