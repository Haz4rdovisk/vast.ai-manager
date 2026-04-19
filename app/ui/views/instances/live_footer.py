from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QStackedLayout

from app.models import Instance
from app.theme import ACCENT, BORDER_LOW, FONT_MONO, TEXT, TEXT_LOW


class _Bar(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.lbl = QLabel(label)
        font = self.lbl.font()
        font.setPointSize(8)
        font.setFamily(FONT_MONO)
        self.lbl.setFont(font)
        self.lbl.setStyleSheet(f"color: {TEXT_LOW};")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {BORDER_LOW}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}"
        )
        lay.addWidget(self.lbl)
        lay.addWidget(self.bar)

    def set_value(self, label: str, pct: float) -> None:
        self.lbl.setText(label)
        self.bar.setValue(int(max(0, min(100, pct))))


class LiveFooter(QFrame):
    """Ultra-spacious metrics footer for premium cluster management."""

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self.main_lay = QVBoxLayout(self)
        # Shifted up to reduce the gap with the separator line
        self.main_lay.setContentsMargins(0, -8, 0, 16) 
        self.main_lay.setSpacing(0)

        self.stack = QStackedLayout()
        self.main_lay.addLayout(self.stack)

        # 1. Loading State
        self.loading_widget = QFrame()
        load_lay = QVBoxLayout(self.loading_widget)
        load_lay.setContentsMargins(0, 0, 0, 0)
        load_lay.setSpacing(2)
        
        load_lbl = QLabel("Loading hardware metrics...")
        lf = load_lbl.font()
        lf.setPointSize(8)
        lf.setFamily(FONT_MONO)
        load_lbl.setFont(lf)
        load_lbl.setStyleSheet(f"color: {TEXT_LOW};")
        
        self.load_bar = QProgressBar()
        self.load_bar.setRange(0, 0)
        self.load_bar.setFixedHeight(2)
        self.load_bar.setTextVisible(False)
        self.load_bar.setStyleSheet(
            f"QProgressBar {{ background: transparent; border: none; max-height: 2px; min-height: 2px; border-radius: 1px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 1px; }}"
        )
        
        load_lay.addWidget(load_lbl)
        load_lay.addWidget(self.load_bar)
        self.stack.addWidget(self.loading_widget)

        # 2. Metrics State
        self.metrics_widget = QFrame()
        met_lay = QVBoxLayout(self.metrics_widget)
        met_lay.setContentsMargins(0, 0, 0, 0)
        met_lay.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(14)
        self.bars = [_Bar("GPU \u2014"), _Bar("vRAM \u2014"), _Bar("CPU \u2014"), _Bar("RAM \u2014")]
        for bar in self.bars:
            row.addWidget(bar, stretch=1)
        met_lay.addLayout(row)
        self.stack.addWidget(self.metrics_widget)

        self._has_data = False
        self.update_instance(inst)

    def update_instance(self, inst: Instance):
        self._gpu_total = inst.gpu_ram_gb or 0
        self._ram_total_mb = (inst.ram_total_gb or 0) * 1024
        self._cpu_cores = inst.cpu_cores or 1

    def apply_metrics(self, metrics: dict) -> None:
        if not self._has_data:
            self._has_data = True
            self.stack.setCurrentWidget(self.metrics_widget)

        gpu = metrics.get("gpu_util") or 0
        temp = metrics.get("gpu_temp")
        self.bars[0].set_value(
            f"GPU {gpu:.0f}%" + (f" {temp:.0f}\u00b0C" if temp is not None else ""),
            gpu,
        )

        vram_used = metrics.get("vram_used_mb") or 0
        vram_total = metrics.get("vram_total_mb") or (self._gpu_total * 1024)
        vram_pct = (vram_used / vram_total * 100) if vram_total else 0
        self.bars[1].set_value(
            f"vRAM {vram_used / 1024:.1f}/{(vram_total or 1) / 1024:.0f}GB",
            vram_pct,
        )

        load = metrics.get("load1") or 0
        load_pct = (load / self._cpu_cores) * 100
        self.bars[2].set_value(
            f"CPU load {load:.2f}" if load else "CPU \u2014",
            load_pct,
        )

        ram_used = metrics.get("ram_used_mb") or 0
        ram_total = metrics.get("ram_total_mb") or self._ram_total_mb
        ram_pct = (ram_used / ram_total * 100) if ram_total else 0
        self.bars[3].set_value(
            f"RAM {ram_used / 1024:.1f}/{(ram_total or 1) / 1024:.0f}GB",
            ram_pct,
        )
