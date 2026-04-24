"""Reusable Lock Screen component to guard views that require an active SSH connection."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
import qtawesome as qta

from app import theme as t

class LockScreen(QWidget):
    """Placeholder view shown when no remote instance is connected."""
    instances_requested = Signal()

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setObjectName("lock-screen")
        self.setStyleSheet(
            f"""
            QWidget#lock-screen QPushButton#lock-screen-cta {{
                min-width: 220px;
                max-width: 220px;
                min-height: 44px;
                max-height: 44px;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 700;
                padding: 0;
            }}
            """
        )
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_8, t.SPACE_8, t.SPACE_8, t.SPACE_8)
        lay.setSpacing(t.SPACE_4)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignCenter)
        center.setSpacing(t.SPACE_4)

        self.lock_icon = QLabel()
        self.lock_icon.setAlignment(Qt.AlignCenter)
        try:
            self.lock_icon.setPixmap(qta.icon("mdi.lock-outline", color=t.ACCENT_SOFT).pixmap(48, 48))
        except Exception:
            self.lock_icon.hide()

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 24px; font-weight: 700;")
        self.title_lbl.setAlignment(Qt.AlignCenter)

        self.msg_lbl = QLabel(message)
        self.msg_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 14px;")
        self.msg_lbl.setAlignment(Qt.AlignCenter)
        self.msg_lbl.setFixedWidth(420)
        self.msg_lbl.setWordWrap(True)

        self.goto_btn = QPushButton("Go to Instances")
        self.goto_btn.setObjectName("lock-screen-cta")
        self.goto_btn.setFixedSize(220, 44)
        self.goto_btn.setProperty("variant", "primary")
        self.goto_btn.clicked.connect(self.instances_requested.emit)

        center.addStretch()
        center.addWidget(self.lock_icon)
        center.addWidget(self.title_lbl)
        center.addWidget(self.msg_lbl)
        center.addSpacing(t.SPACE_4)
        center.addWidget(self.goto_btn, 0, Qt.AlignCenter)
        center.addStretch()

        lay.addLayout(center, 1)

    def set_title(self, text: str):
        self.title_lbl.setText(text)

    def set_message(self, text: str):
        self.msg_lbl.setText(text)
