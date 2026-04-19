"""Step-list, live log, and percent bar used by long-running Lab flows."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.ui.components.primitives import GlassCard


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


_GLYPH = {
    StepState.PENDING: "[ ]",
    StepState.RUNNING: "[>]",
    StepState.DONE: "[x]",
    StepState.FAILED: "[!]",
}

_COLOR = {
    StepState.PENDING: t.TEXT_LOW,
    StepState.RUNNING: t.INFO,
    StepState.DONE: t.OK,
    StepState.FAILED: t.ERR,
}


class ProgressPanel(QWidget):
    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self._states: dict[str, StepState] = {}
        self._labels: dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = GlassCard()
        card.body().setSpacing(t.SPACE_3)
        root.addWidget(card)

        self._step_row = QHBoxLayout()
        self._step_row.setContentsMargins(0, 0, 0, 0)
        self._step_row.setSpacing(t.SPACE_2)
        card.body().addLayout(self._step_row)

        for step in steps:
            self._states[step] = StepState.PENDING
            label = QLabel()
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._labels[step] = label
            self._step_row.addWidget(label)
            self._sync_step_label(step)
        self._step_row.addStretch(1)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        card.body().addWidget(self._bar)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setObjectName("progress-log")
        self._log.setStyleSheet(
            f"QPlainTextEdit#progress-log {{ background: {t.BG_VOID};"
            f" color: {t.TEXT}; border: 1px solid {t.BORDER_LOW};"
            f" border-radius: {t.RADIUS_SM}px; font-family: {t.FONT_MONO};"
            f" font-size: {t.FONT_SIZE_MONO}px; padding: 8px; }}"
        )
        card.body().addWidget(self._log)

    def step_state(self, step: str) -> StepState:
        return self._states[step]

    def set_step(self, step: str, state: StepState) -> None:
        if step not in self._states:
            self._states[step] = StepState.PENDING
            label = QLabel()
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._labels[step] = label
            self._step_row.insertWidget(len(self._labels) - 1, label)

        self._states[step] = state
        self._sync_step_label(step)

    def append_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    def log_text(self) -> str:
        return self._log.toPlainText()

    def set_percent(self, value: int) -> None:
        self._bar.setValue(max(0, min(100, int(value))))

    def percent(self) -> int:
        return self._bar.value()

    def _sync_step_label(self, step: str) -> None:
        state = self._states[step]
        label = self._labels[step]
        color = _COLOR[state]
        label.setText(f"{_GLYPH[state]} {step}")
        label.setStyleSheet(
            f"color: {color}; font-family: {t.FONT_MONO};"
            f" font-size: {t.FONT_SIZE_SMALL}px; font-weight: 700;"
        )
