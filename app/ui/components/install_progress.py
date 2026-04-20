"""Install progress widget: bar, stage checklist, and collapsible log."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import theme as t


STAGES = ["apt", "clone", "cmake", "build", "download", "verify"]
_STAGE_LABELS = {
    "apt": "apt deps",
    "clone": "clone llama.cpp",
    "cmake": "cmake config",
    "build": "build",
    "download": "download GGUF",
    "verify": "verify size",
}


class InstallProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict[str, str] = {stage: "pending" for stage in STAGES}
        self._percent = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_3)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFixedHeight(18)
        root.addWidget(self._bar)

        box = QFrame()
        box.setStyleSheet(f"background: {t.SURFACE_1}; border-radius: 6px;")
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        box_lay.setSpacing(4)
        self._labels: dict[str, QLabel] = {}
        for stage in STAGES:
            label = QLabel()
            self._labels[stage] = label
            box_lay.addWidget(label)
        root.addWidget(box)

        toggle_row = QHBoxLayout()
        self._toggle = QPushButton("> Show live log")
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.setStyleSheet(
            "border: none; background: transparent; color: #888; text-align: left;"
        )
        self._toggle.clicked.connect(self._toggle_log)
        toggle_row.addWidget(self._toggle)
        toggle_row.addStretch()
        root.addLayout(toggle_row)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(200)
        self._log.setFixedHeight(120)
        self._log.setVisible(False)
        self._log.setStyleSheet(
            f"background: {t.BG_VOID}; color: {t.TEXT_MID};"
            f" font-family: {t.FONT_MONO}; font-size: 10px;"
            f" border: 1px solid {t.BORDER_LOW}; border-radius: 4px;"
        )
        root.addWidget(self._log)
        self._refresh_labels()

    def set_stage(self, stage: str, percent: int | None = None) -> None:
        if percent is not None:
            self._percent = max(0, min(100, int(percent)))
            self._bar.setValue(self._percent)

        if stage == "done":
            for item in STAGES:
                self._state[item] = "done"
        elif stage == "failed":
            for item in STAGES:
                if self._state[item] == "running":
                    self._state[item] = "failed"
                    break
            else:
                for item in STAGES:
                    if self._state[item] == "pending":
                        self._state[item] = "failed"
                        break
        elif stage in STAGES:
            seen = False
            for item in STAGES:
                if item == stage:
                    self._state[item] = "running"
                    seen = True
                elif not seen:
                    self._state[item] = "done"
                else:
                    self._state[item] = "pending"
        self._refresh_labels()

    def stage_state(self, stage: str) -> str:
        return self._state[stage]

    def percent(self) -> int:
        return self._percent

    def append_log(self, line: str) -> None:
        self._log.appendPlainText(line.rstrip("\n"))

    def log_text(self) -> str:
        return self._log.toPlainText()

    def _toggle_log(self) -> None:
        visible = not self._log.isVisible()
        self._log.setVisible(visible)
        self._toggle.setText(("v Hide" if visible else "> Show") + " live log")

    def _refresh_labels(self) -> None:
        glyph = {"pending": "o", "running": "*", "done": "x", "failed": "!"}
        colors = {
            "pending": t.TEXT_LOW,
            "running": t.ACCENT,
            "done": t.OK,
            "failed": t.ERR,
        }
        for stage in STAGES:
            state = self._state[stage]
            self._labels[stage].setText(f"[{glyph[state]}] {_STAGE_LABELS[stage]}")
            self._labels[stage].setStyleSheet(
                f"color: {colors[state]}; font-size: 12px;"
            )
