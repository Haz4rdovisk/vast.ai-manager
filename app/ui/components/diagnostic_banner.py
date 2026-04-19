"""Inline banner for actionable llama-server diagnostics."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import theme as t


class DiagnosticBanner(QWidget):
    fix_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible_hint = False
        self._action: str | None = None
        self.setStyleSheet(
            f"background: rgba(255,80,80,0.12); border: 1px solid {t.ERR};"
            f" border-radius: 8px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        layout.setSpacing(t.SPACE_2)

        self._title = QLabel("")
        self._title.setStyleSheet(f"color: {t.ERR}; font-weight: 700;")
        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(f"color: {t.TEXT_MID};")
        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color: {t.TEXT_HI};")

        layout.addWidget(self._title)
        layout.addWidget(self._detail)
        layout.addWidget(self._hint)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self._fix_btn = QPushButton("Apply Fix")
        self._fix_btn.setVisible(False)
        self._fix_btn.clicked.connect(self._emit_fix)
        button_row.addWidget(self._fix_btn)
        layout.addLayout(button_row)

        self.setVisible(False)

    def set_diagnostic(self, diagnostic) -> None:
        self._title.setText(diagnostic.title)
        self._detail.setText(diagnostic.detail)
        self._hint.setText(diagnostic.fix_hint)
        self._action = diagnostic.fix_action
        self._fix_btn.setVisible(bool(diagnostic.fix_action))
        self._visible_hint = True
        self.setVisible(True)

    def clear(self) -> None:
        self._title.setText("")
        self._detail.setText("")
        self._hint.setText("")
        self._action = None
        self._fix_btn.setVisible(False)
        self._visible_hint = False
        self.setVisible(False)

    def title_text(self) -> str:
        return self._title.text()

    def fix_button_visible(self) -> bool:
        return self._fix_btn.isVisible()

    def is_visible_hint(self) -> bool:
        return self._visible_hint

    def _emit_fix(self) -> None:
        if self._action:
            self.fix_requested.emit(self._action)
