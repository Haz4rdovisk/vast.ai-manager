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
        self._stage_rows: dict[str, QWidget] = {}
        self._stage_dots: dict[str, QLabel] = {}
        self._stage_titles: dict[str, QLabel] = {}
        self._stage_subtitles: dict[str, QLabel] = {}
        self._stage_suffixes: dict[str, QLabel] = {}
        self._stage_connectors: dict[str, QFrame] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_3)

        hero = QFrame()
        hero.setObjectName("install-progress-hero")
        hero.setStyleSheet(
            f"QFrame#install-progress-hero {{"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 rgba(255,255,255,0.035),"
            f" stop:1 rgba(255,255,255,0.018));"
            f" border: none; border-radius: 18px; }}"
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
        box.setObjectName("install-progress-timeline")
        box.setStyleSheet(
            f"QFrame#install-progress-timeline {{"
            f"background: rgba(255,255,255,0.022);"
            f" border: none; border-radius: 18px; }}"
        )
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_3)
        box_lay.setSpacing(10)
        stage_title = QLabel("Timeline")
        stage_title.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: 800; letter-spacing: 1.4px;"
        )
        box_lay.addWidget(stage_title)
        timeline = QWidget()
        timeline_lay = QVBoxLayout(timeline)
        timeline_lay.setContentsMargins(0, 0, 0, 0)
        timeline_lay.setSpacing(2)
        for idx, stage in enumerate(STAGES):
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(12)

            rail = QVBoxLayout()
            rail.setContentsMargins(0, 0, 0, 0)
            rail.setSpacing(0)
            spacer_top = QWidget()
            spacer_top.setFixedHeight(6)
            rail.addWidget(spacer_top)
            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setAlignment(Qt.AlignCenter)
            rail.addWidget(dot, 0, Qt.AlignHCenter)
            connector = QFrame()
            connector.setFixedWidth(2)
            connector.setMinimumHeight(24)
            connector.setStyleSheet("background: transparent; border: none;")
            connector.setVisible(idx < len(STAGES) - 1)
            rail.addWidget(connector, 1, Qt.AlignHCenter)
            row_lay.addLayout(rail)

            text_col = QVBoxLayout()
            text_col.setContentsMargins(0, 0, 0, 0)
            text_col.setSpacing(1)
            title = QLabel(_STAGE_LABELS[stage].title())
            title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 700;")
            subtitle = QLabel("")
            subtitle.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 11px;")
            text_col.addWidget(title)
            text_col.addWidget(subtitle)
            row_lay.addLayout(text_col, 1)

            suffix = QLabel()
            suffix.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_lay.addWidget(suffix, 0, Qt.AlignRight | Qt.AlignVCenter)

            self._stage_rows[stage] = row
            self._stage_dots[stage] = dot
            self._stage_titles[stage] = title
            self._stage_subtitles[stage] = subtitle
            self._stage_suffixes[stage] = suffix
            self._stage_connectors[stage] = connector
            timeline_lay.addWidget(row)
        box_lay.addWidget(timeline)
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
        colors = {
            "pending": t.TEXT_LOW,
            "running": t.ACCENT,
            "done": t.OK,
            "failed": t.ERR,
        }
        subtitles = {
            "pending": "Waiting for previous steps",
            "running": "Currently running on the remote machine",
            "done": "Finished successfully",
            "failed": "Stopped before completion",
        }
        chips = {
            "pending": ("Queued", f"color: {t.TEXT_LOW}; background: rgba(255,255,255,0.04); border: none;"),
            "running": ("Running", f"color: {t.ACCENT_SOFT}; background: rgba(124,92,255,0.16); border: 1px solid rgba(124,92,255,0.24);"),
            "done": ("Done", f"color: {t.OK}; background: rgba(59,212,136,0.14); border: 1px solid rgba(59,212,136,0.22);"),
            "failed": ("Failed", f"color: {t.ERR}; background: rgba(240,85,106,0.14); border: 1px solid rgba(240,85,106,0.22);"),
        }
        for stage in STAGES:
            state = self._state[stage]
            dot = self._stage_dots[stage]
            title = self._stage_titles[stage]
            subtitle = self._stage_subtitles[stage]
            suffix = self._stage_suffixes[stage]
            connector = self._stage_connectors[stage]
            color = colors[state]
            chip_text, chip_style = chips[state]

            dot.setStyleSheet(
                f"background: {color}; border: 2px solid rgba(255,255,255,0.06);"
                "border-radius: 6px;"
            )
            title.setStyleSheet(f"color: {color if state != 'pending' else t.TEXT_MID}; font-size: 13px; font-weight: 700;")
            title.setText(_STAGE_LABELS[stage].title())
            subtitle.setText(subtitles[state])
            connector.setStyleSheet(
                f"background: {color if state in ('done', 'running') else 'rgba(255,255,255,0.08)'};"
                "border: none; border-radius: 1px;"
            )
            suffix.setText(chip_text)
            suffix.setStyleSheet(
                chip_style + "border-radius: 999px; padding: 5px 10px; font-size: 11px; font-weight: 800;"
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
