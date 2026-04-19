"""Dashed wireframe placeholder for the hardware grid — glassmorphism polish."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt
from app import theme as t


from app.ui.components.primitives import GlassCard


class HardwarePlaceholderCard(GlassCard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(360)
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Adfeita a borda tracejada por cima do efeito de vidro
        self.setStyleSheet(f"""
            QFrame {{
                border: 2px dashed {t.BORDER_LOW};
                border-radius: {t.RADIUS_LG}px;
                background-color: transparent;
            }}
        """)

        lay = self.body()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_2)
        lay.setAlignment(Qt.AlignCenter)

        icon = QLabel("\u2726")
        icon.setStyleSheet(
            f"font-size: 36pt; color: {t.TEXT_LOW};"
            f" margin-bottom: 10px; border: none;"
        )
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)

        tip = QLabel("Connect a machine to see live metrics here.")
        tip.setStyleSheet(
            f"font-size: 10pt; color: {t.TEXT_LOW};"
            f" font-weight: 500; border: none;"
        )
        tip.setWordWrap(True)
        tip.setMaximumWidth(280)
        tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(tip)
