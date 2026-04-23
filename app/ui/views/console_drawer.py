"""Bottom console drawer: collapsible log panel styled via the QTextEdit#console
rule in app.theme. Header row with a caret toggle and a Clear button."""
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
)
from PySide6.QtCore import Qt, Signal
from app import theme as t


class ConsoleDrawer(QFrame):
    expanded_changed = Signal(bool)

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
        bar.setContentsMargins(0, 0, 0, 0)
        self.toggle_btn = QPushButton("▾  Console")
        self.toggle_btn.setFixedHeight(34)
        self.toggle_btn.setMinimumWidth(132)
        self.toggle_btn.setStyleSheet(_console_button_style())
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        self.clear_btn = QPushButton("Limpar")
        self.clear_btn.setFixedHeight(34)
        self.clear_btn.setMinimumWidth(92)
        self.clear_btn.setStyleSheet(_console_button_style())
        self.clear_btn.clicked.connect(lambda: self.view.clear())
        bar.addWidget(self.toggle_btn)
        bar.addStretch()
        bar.addWidget(self.clear_btn)
        root.addLayout(bar)

        self.view = QTextEdit()
        self.view.setObjectName("console")
        self.view.setReadOnly(True)
        self._view_height = 140
        self._bar_height = 34
        self.view.setFixedHeight(self._view_height)
        root.addWidget(self.view)

        self._expanded = True
        self.set_expanded(True)

    def _toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self.view.setVisible(self._expanded)
        self.clear_btn.setVisible(self._expanded)
        self.toggle_btn.setText(("▾  Console" if self._expanded else "▸  Console"))
        panel_height = self._bar_height + (t.SPACE_2 + self._view_height if self._expanded else 0)
        self.setFixedHeight(panel_height)
        self.expanded_changed.emit(self._expanded)

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.view.append(f"[{ts}] {message}")
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())


def _console_button_style() -> str:
    return (
        "QPushButton {"
        f" background: transparent; color: {t.TEXT_HI};"
        f" border: 1px solid {t.BORDER_MED}; border-radius: 10px;"
        " padding: 4px 14px; font-weight: 700; min-height: 18px;"
        "}"
        "QPushButton:hover {"
        f" background: rgba(255,255,255,0.04); border-color: {t.BORDER_HI};"
        "}"
        "QPushButton:pressed {"
        " background: rgba(255,255,255,0.02); padding-top: 5px; padding-bottom: 3px;"
        "}"
    )
