"""Lab-styled progress bar \u2014 thin, animated, on-brand."""
from __future__ import annotations
from PySide6.QtWidgets import QProgressBar
from app.lab import theme as t


class LabProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(6)
        self.setStyleSheet(
            f"QProgressBar {{ background: {t.SURFACE_3}; border: none;"
            f" border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {t.ACCENT};"
            f" border-radius: 3px; }}"
        )
