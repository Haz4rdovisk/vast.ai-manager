"""Dashed wireframe placeholder for the hardware grid."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
from PySide6.QtCore import Qt
from app import theme as t

class HardwarePlaceholderCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(650)
        self.setMinimumHeight(450) 
        
        # Restore dashed wireframe
        self.setStyleSheet(f"""
            QFrame {{
                border: 2px dashed {t.BORDER_LOW};
                border-radius: {t.RADIUS_LG}px;
                background-color: transparent;
            }}
        """)
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_2)
        lay.setAlignment(Qt.AlignCenter)
        
        icon = QLabel("\u2726") # Sparkle/Star
        icon.setStyleSheet(f"font-size: 32pt; color: {t.SURFACE_3}; margin-bottom: 10px; border: none;")
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        
        tip = QLabel("Connect a remote machine to see live metrics here.")
        tip.setStyleSheet(f"font-size: 10pt; color: {t.TEXT_LOW}; font-weight: 500; border: none;")
        tip.setWordWrap(True)
        tip.setFixedWidth(280)
        tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(tip)
