from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar, QSizePolicy
from PySide6.QtCore import Qt
from app import theme


class MetricBar(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.label = QLabel(label)
        self.label.setFixedWidth(60)
        self.label.setObjectName("secondary")

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.value_label = QLabel("—")
        self.value_label.setMinimumWidth(140)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lay.addWidget(self.label)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.value_label)

        self._apply_color(theme.TEXT_SECONDARY)

    def set_value(self, percent: float | None, text: str | None = None):
        if percent is None:
            self.bar.setValue(0)
            self.value_label.setText("—")
            self._apply_color(theme.TEXT_SECONDARY)
            return
        p = max(0.0, min(100.0, percent))
        self.bar.setValue(int(p))
        self.value_label.setText(text if text is not None else f"{p:.0f}%")
        self._apply_color(theme.metric_color(p))

    def _apply_color(self, color: str):
        self.bar.setStyleSheet(
            f"QProgressBar {{ background-color: {theme.BG}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}"
        )
