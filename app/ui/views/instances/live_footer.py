from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

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
    """Four live metric bars plus a compact status string."""

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self._gpu_total = inst.gpu_ram_gb or 0
        self._ram_total_mb = (inst.ram_total_gb or 0) * 1024
        self.setStyleSheet(
            f"LiveFooter {{ border-top: 1px solid {BORDER_LOW}; padding-top: 10px; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 10, 0, 0)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(14)
        self.bars = [_Bar("GPU —"), _Bar("vRAM —"), _Bar("CPU —"), _Bar("RAM —")]
        for bar in self.bars:
            row.addWidget(bar, stretch=1)
        outer.addLayout(row)

        self.status = QLabel("—")
        font = self.status.font()
        font.setPointSize(8)
        font.setFamily(FONT_MONO)
        self.status.setFont(font)
        self.status.setStyleSheet(f"color: {TEXT};")
        outer.addWidget(self.status)

    def apply_metrics(self, metrics: dict) -> None:
        gpu = metrics.get("gpu_util") or 0
        temp = metrics.get("gpu_temp")
        self.bars[0].set_value(
            f"GPU {gpu:.0f}%" + (f" {temp:.0f}°C" if temp is not None else ""),
            gpu,
        )

        vram_used = metrics.get("vram_used_mb") or 0
        vram_total = metrics.get("vram_total_mb") or (self._gpu_total * 1024)
        vram_pct = (vram_used / vram_total * 100) if vram_total else 0
        self.bars[1].set_value(
            f"vRAM {vram_used / 1024:.1f}/{(vram_total or 1) / 1024:.0f}GB",
            vram_pct,
        )

        load = metrics.get("load1")
        self.bars[2].set_value(
            f"CPU load {load:.2f}" if load is not None else "CPU —",
            min(100, (load or 0) * 25),
        )

        ram_used = metrics.get("ram_used_mb") or 0
        ram_total = metrics.get("ram_total_mb") or self._ram_total_mb
        ram_pct = (ram_used / ram_total * 100) if ram_total else 0
        self.bars[3].set_value(
            f"RAM {ram_used / 1024:.1f}/{(ram_total or 1) / 1024:.0f}GB",
            ram_pct,
        )

        self.status.setText(
            f"GPU: {gpu:.0f}% {temp:.0f}°C, RAM: {ram_used / 1024:.1f}GB"
            if temp is not None
            else f"GPU: {gpu:.0f}%"
        )

    def status_text(self) -> str:
        return self.status.text()
