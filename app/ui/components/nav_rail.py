"""Left nav rail — full navigation with sections. Emits `selected(key)` on click."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt
from app import theme as t


# (key, label, glyph, section)
NAV_ITEMS = [
    # ── CLOUD ──
    ("instances",  "Instances",     "\u25A3", "CLOUD"),
    ("analytics",  "Analytics",     "\u25C6", "CLOUD"),
    # ── AI LAB ──
    ("dashboard",  "Dashboard",     "\u25C9", "AI LAB"),
    ("hardware",   "Hardware",      "\u2B21", "AI LAB"),
    ("discover",   "Discover",      "\u2726", "AI LAB"),
    ("models",     "Models",        "\u25A4", "AI LAB"),
    ("monitor",    "Monitor",       "\u25D4", "AI LAB"),
    # ── SYSTEM ──
    ("settings",   "Settings",      "\u2699", "SYSTEM"),
]


class NavRail(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nav-rail")
        self.setFixedWidth(240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_4, t.SPACE_5, t.SPACE_4, t.SPACE_4)
        lay.setSpacing(2)

        # Brand
        brand = QLabel("\u2726  VAST.AI")
        brand.setStyleSheet(
            f"color: {t.TEXT_HI}; font-weight: 800; letter-spacing: 3px;"
            f" font-size: 12pt; padding: 4px 8px 28px 8px;"
        )
        lay.addWidget(brand)

        self._buttons: dict[str, QPushButton] = {}
        current_section = ""

        for key, label, glyph, section in NAV_ITEMS:
            # Section header (only when section changes)
            if section != current_section:
                current_section = section
                if len(self._buttons) > 0:
                    lay.addSpacing(16)
                sec_lbl = QLabel(section)
                sec_lbl.setStyleSheet(
                    f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: 600;"
                    f" letter-spacing: 1.5px; padding: 4px 16px 4px 16px;"
                )
                lay.addWidget(sec_lbl)

            btn = QPushButton(f"  {glyph}   {label}")
            btn.setProperty("role", "nav-item")
            btn.setProperty("active", "false")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
            lay.addWidget(btn)
            self._buttons[key] = btn

        lay.addStretch()

        foot = QLabel("v2.1 \u2022 remote inference")
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 8pt; padding: 8px;")
        lay.addWidget(foot)

        self.set_active("instances")

    def _on_click(self, key: str):
        self.set_active(key)
        self.selected.emit(key)

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
