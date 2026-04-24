from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout

from app.services.instance_filter import FilterState
from app.theme import BORDER_LOW
from app import theme as t
from app.ui.components import icons
from app.ui.components.primitives import IconButton


_SORT_OPTIONS = [
    ("Auto Sort", "auto"),
    ("Price ↑", "price_asc"),
    ("Price ↓", "price_desc"),
    ("Uptime ↓", "uptime_desc"),
    ("Uptime ↑", "uptime_asc"),
    ("DLPerf ↓", "dlperf"),
    ("DLPerf / $ ↓", "dlperf_per_dollar"),
    ("Reliability ↓", "reliability"),
    ("Status", "status"),
]

_STATUS_OPTIONS = [
    ("All Statuses", ""),
    ("Running", "running"),
    ("Stopped", "stopped"),
    ("Starting", "starting"),
    ("Stopping", "stopping"),
]


class FilterBar(QFrame):
    """Top bar with GPU, Status, Label, and Sort dropdowns."""

    changed = Signal(object)

    def __init__(self, initial: FilterState, parent=None) -> None:
        super().__init__(parent)
        self.state = FilterState(
            gpu_types=list(initial.gpu_types),
            statuses=list(initial.statuses),
            label=initial.label,
            sort=initial.sort,
        )
        self.setStyleSheet(f"FilterBar {{ border-bottom: 1px solid {BORDER_LOW}; }}")
        self.setStyleSheet(
            f"""
            FilterBar {{
                border-bottom: 1px solid {BORDER_LOW};
            }}
            FilterBar QComboBox {{
                background: #253044;
                color: {t.TEXT_HI};
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 14px;
                padding: 6px 14px;
                min-height: 32px;
            }}
            FilterBar QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            FilterBar QComboBox:focus {{
                border-color: rgba(255,255,255,0.08);
                background: #202B3E;
            }}
            FilterBar QToolButton {{
                background: transparent;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                color: {t.TEXT_MID};
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}
            FilterBar QToolButton:hover {{
                background: rgba(255,255,255,0.06);
                color: {t.TEXT_HI};
            }}
            """
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(8)

        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("All GPUs", "")
        self.gpu_combo.setMinimumWidth(120)
        self.gpu_combo.currentIndexChanged.connect(self._on_gpu)
        lay.addWidget(self.gpu_combo)

        self.status_combo = QComboBox()
        self.status_combo.setMinimumWidth(130)
        for label, value in _STATUS_OPTIONS:
            self.status_combo.addItem(label, value)
        self.status_combo.currentIndexChanged.connect(self._on_status)
        lay.addWidget(self.status_combo)

        self.label_combo = QComboBox()
        self.label_combo.setMinimumWidth(112)
        self.label_combo.addItem("All", "")
        self.label_combo.addItem("No Label", "__none__")
        self.label_combo.currentIndexChanged.connect(self._on_label)
        lay.addWidget(self.label_combo)

        self.sort_combo = QComboBox()
        self.sort_combo.setMinimumWidth(132)
        for text, key in _SORT_OPTIONS:
            self.sort_combo.addItem(text, key)
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        lay.addWidget(self.sort_combo)

        self.reset = IconButton(icons.CLOSE, "Reset filters")
        self.reset.clicked.connect(self._on_reset)
        lay.addWidget(self.reset)
        lay.addStretch(1)

        self._sync_to_widgets()

    def set_gpu_options(self, opts: list[str]) -> None:
        current = self.gpu_combo.currentData()
        self.gpu_combo.blockSignals(True)
        self.gpu_combo.clear()
        self.gpu_combo.addItem("All GPUs", "")
        for opt in opts:
            self.gpu_combo.addItem(opt, opt)
        idx = self.gpu_combo.findData(current)
        self.gpu_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.gpu_combo.blockSignals(False)

    def set_label_options(self, opts: list[str]) -> None:
        current = self.label_combo.currentData()
        self.label_combo.blockSignals(True)
        self.label_combo.clear()
        self.label_combo.addItem("All", "")
        self.label_combo.addItem("No Label", "__none__")
        for opt in opts:
            self.label_combo.addItem(opt, opt)
        idx = self.label_combo.findData(current)
        self.label_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.label_combo.blockSignals(False)

    def gpu_option_texts(self) -> list[str]:
        return [self.gpu_combo.itemText(i) for i in range(self.gpu_combo.count())]

    def label_option_texts(self) -> list[str]:
        return [self.label_combo.itemText(i) for i in range(self.label_combo.count())]

    def set_sort(self, key: str) -> None:
        idx = self.sort_combo.findData(key)
        if idx >= 0:
            self.sort_combo.setCurrentIndex(idx)

    def _on_gpu(self, _idx: int) -> None:
        value = self.gpu_combo.currentData() or ""
        self.state.gpu_types = [value] if value else []
        self.changed.emit(self.state)

    def _on_status(self, _idx: int) -> None:
        value = self.status_combo.currentData() or ""
        self.state.statuses = [value] if value else []
        self.changed.emit(self.state)

    def _on_label(self, _idx: int) -> None:
        value = self.label_combo.currentData() or ""
        self.state.label = value or None
        self.changed.emit(self.state)

    def _on_sort(self, _idx: int) -> None:
        self.state.sort = self.sort_combo.currentData() or "auto"
        self.changed.emit(self.state)

    def _on_reset(self) -> None:
        self.state = FilterState()
        self._sync_to_widgets()
        self.changed.emit(self.state)

    def _sync_to_widgets(self) -> None:
        pairs = (
            (self.gpu_combo, (self.state.gpu_types[:1] or [""])[0]),
            (self.status_combo, (self.state.statuses[:1] or [""])[0]),
            (self.label_combo, self.state.label or ""),
            (self.sort_combo, self.state.sort),
        )
        for combo, value in pairs:
            idx = combo.findData(value)
            combo.blockSignals(True)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
