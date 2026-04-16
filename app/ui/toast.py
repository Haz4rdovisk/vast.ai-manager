from __future__ import annotations
from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtCore import Qt, QTimer
from app import theme


class Toast(QLabel):
    COLORS = {
        "info": theme.INFO,
        "success": theme.SUCCESS,
        "warning": theme.WARNING,
        "error": theme.DANGER,
    }

    _stack: list["Toast"] = []

    def __init__(self, parent: QWidget, message: str, kind: str = "info", duration_ms: int = 3000):
        super().__init__(parent)
        self.setText(message)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        color = self.COLORS.get(kind, theme.INFO)
        self.setStyleSheet(
            f"background-color: {theme.CARD_BG}; color: {theme.TEXT};"
            f" border-left: 4px solid {color};"
            f" border-radius: 8px; padding: 12px 16px; font-weight: 500;"
        )
        self.setFixedWidth(340)
        self.adjustSize()
        Toast._stack.append(self)
        self._reposition_stack()
        self.show()
        self.raise_()
        QTimer.singleShot(duration_ms, self._close)

    def mousePressEvent(self, event):
        self._close()

    def _close(self):
        if self in Toast._stack:
            Toast._stack.remove(self)
        self.close()
        self._reposition_stack()

    def _reposition_stack(self):
        parent = self.parent()
        if parent is None:
            return
        margin = 20
        y = parent.height() - margin
        for t in reversed(Toast._stack):
            y -= t.height() + 8
            x = parent.width() - t.width() - margin
            t.move(x, y)
