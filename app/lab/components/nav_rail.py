"""Left nav rail for the Lab. Emits `selected(key)` on button click."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt
from app.lab import theme as t


NAV_ITEMS = [
    ("overview",    "Overview",    "\u25C8"),
    ("machine",     "Machine",     "\u25A3"),
    ("runtime",     "Runtime",     "\u25E7"),
    ("discover",    "Discover",    "\u2726"),
    ("library",     "Library",     "\u25A4"),
    ("benchmark",   "Benchmark",   "\u25F4"),
    ("diagnostics", "Diagnostics", "\u25C9"),
]


class NavRail(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lab-nav-rail")
        self.setFixedWidth(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_4, t.SPACE_5, t.SPACE_3, t.SPACE_4)
        lay.setSpacing(2)

        brand = QLabel("LOCAL AI LAB")
        brand.setStyleSheet(
            f"color: {t.TEXT_HI}; font-weight: 800; letter-spacing: 2px;"
            f" font-size: 10pt; padding: 4px 8px 20px 8px;"
        )
        lay.addWidget(brand)

        self._buttons: dict[str, QPushButton] = {}
        for key, label, glyph in NAV_ITEMS:
            btn = QPushButton(f"  {glyph}   {label}")
            btn.setProperty("role", "nav-item")
            btn.setProperty("active", "false")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
            lay.addWidget(btn)
            self._buttons[key] = btn

        lay.addStretch()

        foot = QLabel("llama.cpp \u2022 local inference")
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 8pt; padding: 8px;")
        lay.addWidget(foot)

        self.set_active("overview")

    def _on_click(self, key: str):
        self.set_active(key)
        self.selected.emit(key)

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
