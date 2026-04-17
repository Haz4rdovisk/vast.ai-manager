"""Custom integrated title bar for frameless window — glassmorphism edition."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QPoint
from app import theme as t


class TitleBar(QWidget):
    def __init__(self, parent_window: QWidget):
        super().__init__(parent_window)
        self.win = parent_window
        self.setObjectName("title-bar")
        self.setFixedHeight(t.TITLEBAR_HEIGHT)

        self._drag_pos = QPoint()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Page title (centered label)
        lay.addSpacing(16)
        self._page_label = QLabel("")
        self._page_label.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: 10pt; font-weight: 500;"
            f" letter-spacing: 0.5px;"
        )
        lay.addWidget(self._page_label)
        lay.addStretch()

        # Control Buttons
        self.btn_min = QPushButton("\u2500")  # ─
        self.btn_min.setObjectName("title-btn")
        self.btn_min.clicked.connect(self.win.showMinimized)
        lay.addWidget(self.btn_min)

        self.btn_max = QPushButton("\u25A1")  # □
        self.btn_max.setObjectName("title-btn")
        self.btn_max.clicked.connect(self._toggle_max)
        lay.addWidget(self.btn_max)

        self.btn_close = QPushButton("\u2715")  # ✕
        self.btn_close.setObjectName("title-btn-close")
        self.btn_close.clicked.connect(self.win.close)
        lay.addWidget(self.btn_close)

    # ── Public API ──────────────────────────────────────────────────────
    def setPageTitle(self, text: str):
        """Update the page title shown in the center of the bar."""
        self._page_label.setText(text)

    # ── Window controls ─────────────────────────────────────────────────
    def _toggle_max(self):
        if self.win.isMaximized():
            self.win.showNormal()
            self.btn_max.setText("\u25A1")
        else:
            self.win.showMaximized()
            self.btn_max.setText("\u2750")

    # ── Drag ────────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_max()
