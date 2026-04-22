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
        self._current_stage = "apt"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_3)

        hero = QFrame()
        hero.setStyleSheet(
            f"background: {t.SURFACE_1}; border: 1px solid {t.BORDER_LOW}; border-radius: 14px;"
        )
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        hero_lay.setSpacing(t.SPACE_4)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(2)
        self._eyebrow = QLabel("REMOTE OPERATION")
        self._eyebrow.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: 800; letter-spacing: 1.4px;"
        )
        self._title = QLabel("Preparing operation...")
        self._title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 16px; font-weight: 800;")
        self._subtitle = QLabel("Remote sync active.")
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 12px;")
        hero_text.addWidget(self._eyebrow)
        hero_text.addWidget(self._title)
        hero_text.addWidget(self._subtitle)
        hero_lay.addLayout(hero_text, 1)

        hero_right = QVBoxLayout()
        hero_right.setContentsMargins(0, 0, 0, 0)
        hero_right.setSpacing(4)
        self._percent_label = QLabel("0%")
        self._percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._percent_label.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 28px; font-weight: 900;")
        self._state_chip = QLabel("Pending")
        self._state_chip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._state_chip.setStyleSheet(
            f"color: {t.ACCENT_SOFT}; background: rgba(124,92,255,0.12); border: 1px solid rgba(124,92,255,0.24);"
            "border-radius: 999px; padding: 4px 10px; font-size: 11px; font-weight: 800;"
        )
        hero_right.addWidget(self._percent_label)
        hero_right.addWidget(self._state_chip, 0, Qt.AlignRight)
        hero_lay.addLayout(hero_right)
        root.addWidget(hero)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,0.05); border: none; border-radius: 5px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {t.ACCENT}, stop:1 {t.ACCENT_HI}); border-radius: 5px; }}"
        )
        root.addWidget(self._bar)

        box = QFrame()
        box.setStyleSheet(
            f"background: {t.SURFACE_1}; border: 1px solid {t.BORDER_LOW}; border-radius: 14px;"
        )
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        box_lay.setSpacing(8)
        stage_title = QLabel("Timeline")
        stage_title.setProperty("role", "section")
        box_lay.addWidget(stage_title)
        self._labels: dict[str, QLabel] = {}
        for stage in STAGES:
            label = QLabel()
            self._labels[stage] = label
            box_lay.addWidget(label)
        root.addWidget(box)

        toggle_row = QHBoxLayout()
        log_title = QLabel("Remote log")
        log_title.setProperty("role", "section")
        toggle_row.addWidget(log_title)

        self._toggle = QPushButton("Hide log")
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.setStyleSheet(
            f"border: none; background: transparent; color: {t.TEXT_MID}; text-align: left; font-weight: 700;"
        )
        toggle_row.addStretch()
        self._toggle.clicked.connect(self._toggle_log)
        toggle_row.addWidget(self._toggle)
        root.addLayout(toggle_row)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(200)
        self._log.setFixedHeight(200)
        self._log.setVisible(True)
        self._log.setStyleSheet(
            f"background: #0B0F16; color: {t.TEXT_HI};"
            f" selection-background-color: {t.ACCENT}; selection-color: white;"
            f" font-family: {t.FONT_MONO}; font-size: 11px;"
            f" border: 1px solid {t.BORDER_MED}; border-radius: 12px; padding: 12px;"
        )
        root.addWidget(self._log)
        self._refresh_labels()
        self._refresh_header()

    def set_stage(self, stage: str, percent: int | None = None) -> None:
        if percent is not None:
            self._percent = max(0, min(100, int(percent)))
            self._bar.setValue(self._percent)
            self._percent_label.setText(f"{self._percent}%")

        if stage == "done":
            for item in STAGES:
                self._state[item] = "done"
            self._current_stage = STAGES[-1]
        elif stage == "failed":
            for item in STAGES:
                if self._state[item] == "running":
                    self._state[item] = "failed"
                    self._current_stage = item
                    break
            else:
                for item in STAGES:
                    if self._state[item] == "pending":
                        self._state[item] = "failed"
                        self._current_stage = item
                        break
        elif stage in STAGES:
            self._current_stage = stage
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
        self._refresh_header(stage)

    def stage_state(self, stage: str) -> str:
        return self._state[stage]

    def percent(self) -> int:
        return self._percent

    def append_log(self, line: str) -> None:
        self._log.appendPlainText(line.rstrip("\n"))
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def log_text(self) -> str:
        return self._log.toPlainText()

    def _toggle_log(self) -> None:
        visible = not self._log.isVisible()
        self._log.setVisible(visible)
        self._toggle.setText("Hide log" if visible else "Show log")

    def _refresh_labels(self) -> None:
        glyph = {"pending": "○", "running": "◔", "done": "●", "failed": "✕"}
        colors = {
            "pending": t.TEXT_LOW,
            "running": t.ACCENT,
            "done": t.OK,
            "failed": t.ERR,
        }
        for stage in STAGES:
            state = self._state[stage]
            label = _STAGE_LABELS[stage]
            suffix = {
                "pending": "Queued",
                "running": "Running",
                "done": "Done",
                "failed": "Failed",
            }[state]
            self._labels[stage].setText(f"{glyph[state]}  {label}  ·  {suffix}")
            self._labels[stage].setStyleSheet(
                f"color: {colors[state]}; font-size: 12px; font-weight: 700; padding: 4px 0;"
            )

    def _refresh_header(self, stage: str | None = None) -> None:
        current = stage or self._current_stage
        if current == "done":
            title = "Operation complete"
            subtitle = "Complete."
            chip_text, chip_style = "Complete", (
                f"color: {t.OK}; background: rgba(59,212,136,0.12); border: 1px solid rgba(59,212,136,0.24);"
            )
        elif current == "failed":
            title = "Operation failed"
            subtitle = "Check log."
            chip_text, chip_style = "Failed", (
                f"color: {t.ERR}; background: rgba(240,85,106,0.12); border: 1px solid rgba(240,85,106,0.24);"
            )
        else:
            title = _STAGE_LABELS.get(current, "Preparing operation").title()
            subtitle = "Remote sync active."
            chip_text, chip_style = "In progress", (
                f"color: {t.ACCENT_SOFT}; background: rgba(124,92,255,0.12); border: 1px solid rgba(124,92,255,0.24);"
            )
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self._state_chip.setText(chip_text)
        self._state_chip.setStyleSheet(
            chip_style + "border-radius: 999px; padding: 4px 10px; font-size: 11px; font-weight: 800;"
        )
