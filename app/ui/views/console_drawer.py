"""Bottom console drawer: collapsible log panel styled via the QTextEdit#console
rule in app.theme. Header row with a caret toggle and a Clear button."""
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
)
from PySide6.QtCore import Qt
from app import theme as t


class ConsoleDrawer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("console-drawer")
        self.setStyleSheet(
            f"#console-drawer {{ background: transparent; border: none; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_2)

        bar = QHBoxLayout()
        self.toggle_btn = QPushButton("▾  Console")
        self.toggle_btn.setProperty("variant", "ghost")
        self.toggle_btn.setFixedHeight(28)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        self.clear_btn = QPushButton("Limpar")
        self.clear_btn.setProperty("variant", "ghost")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.clicked.connect(lambda: self.view.clear())
        bar.addWidget(self.toggle_btn)
        bar.addStretch()
        bar.addWidget(self.clear_btn)
        root.addLayout(bar)

        self.view = QTextEdit()
        self.view.setObjectName("console")
        self.view.setReadOnly(True)
        self.view.setFixedHeight(140)
        root.addWidget(self.view)

        self._expanded = True

    def _toggle(self):
        self._expanded = not self._expanded
        self.view.setVisible(self._expanded)
        self.toggle_btn.setText(("▾  Console" if self._expanded else "▸  Console"))

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.view.append(f"[{ts}] {message}")
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())
