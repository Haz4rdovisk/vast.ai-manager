from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import QTextEdit


class LogPanel(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("log")
        self.setReadOnly(True)
        self.setFixedHeight(130)

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.append(f"[{ts}] {message}")
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())
