from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton

from app.theme import ACCENT, BORDER_LOW, FONT_DISPLAY, TEXT, TEXT_LOW


class LabelTabs(QFrame):
    """Tab strip for All, No Label, and custom labels."""

    label_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"LabelTabs {{ border-bottom: 1px solid {BORDER_LOW}; }}")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self._lay.addStretch(1)
        self._btns: dict[str, QPushButton] = {}
        self._active = ""

    def update_labels(self, counts: dict[str, int]) -> None:
        keys = [""]
        if "__none__" in counts:
            keys.append("__none__")
        keys.extend(sorted(k for k in counts if k not in ("", "__none__")))
        self._rebuild(keys, counts)
        self._set_active(self._active if self._active in self._btns else "")

    def _rebuild(self, keys: list[str], counts: dict[str, int]) -> None:
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._btns.clear()

        for idx, key in enumerate(keys):
            btn = QPushButton(self._label_for(key, counts.get(key, 0)))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            font = btn.font()
            font.setFamily(FONT_DISPLAY)
            font.setPointSize(10)
            btn.setFont(font)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
            self._lay.insertWidget(idx, btn)
            self._btns[key] = btn

    @staticmethod
    def _label_for(key: str, count: int) -> str:
        if key == "":
            return f"All ({count})"
        if key == "__none__":
            return f"No Label ({count})"
        return f"{key} ({count})"

    def _on_click(self, key: str) -> None:
        self._set_active(key)
        self.label_selected.emit(key)

    def _set_active(self, key: str) -> None:
        self._active = key
        for tab_key, btn in self._btns.items():
            color = ACCENT if tab_key == key else TEXT_LOW
            border = f"2px solid {ACCENT}" if tab_key == key else "2px solid transparent"
            btn.setStyleSheet(
                f"QPushButton {{ color: {color}; background: transparent;"
                f" border: none; border-bottom: {border}; padding: 6px 10px;"
                f" border-radius: 0; }}"
                f"QPushButton:hover {{ color: {TEXT}; }}"
            )

    def click_label(self, key: str) -> None:
        if key in self._btns:
            self._on_click(key)

    def tab_texts(self) -> list[str]:
        return [self._btns[key].text() for key in self._btns]
