"""Machine view — hardware spec tiles + capacity notes."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QHBoxLayout
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, MetricTile, SectionHeader, StatusPill, KeyValueRow,
)
from app.lab.services.capacity import estimate_capacity
from app.lab.state.models import HardwareSpec
from app.lab.state.store import LabStore


class MachineView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        root.addWidget(SectionHeader("SYSTEM", "Machine"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(t.SPACE_4)
        grid.setVerticalSpacing(t.SPACE_4)
        self.cpu_tile = MetricTile("CPU", "\u2014")
        self.ram_tile = MetricTile("Memory", "\u2014")
        self.gpu_tile = MetricTile("GPU", "\u2014")
        self.vram_tile = MetricTile("VRAM", "\u2014")
        self.disk_tile = MetricTile("Disk Free", "\u2014")
        self.backend_tile = MetricTile("Backend", "\u2014")
        for i, tile in enumerate([self.cpu_tile, self.ram_tile, self.gpu_tile,
                                  self.vram_tile, self.disk_tile, self.backend_tile]):
            grid.addWidget(tile, i // 3, i % 3)
        root.addLayout(grid)

        self.cap_card = GlassCard()
        header_row = QHBoxLayout()
        self.cap_header = QLabel("Capacity")
        self.cap_header.setProperty("role", "title")
        self.cap_pill = StatusPill("\u2014", "info")
        header_row.addWidget(self.cap_header)
        header_row.addStretch()
        header_row.addWidget(self.cap_pill)
        self.cap_card.body().addLayout(header_row)
        self.cap_headline = QLabel("Detecting\u2026")
        self.cap_headline.setWordWrap(True)
        self.cap_card.body().addWidget(self.cap_headline)
        self.cap_notes = QVBoxLayout()
        self.cap_notes.setSpacing(4)
        self.cap_card.body().addLayout(self.cap_notes)
        root.addWidget(self.cap_card)

        self.det_card = GlassCard()
        det_header = QLabel("HARDWARE DETAILS")
        det_header.setProperty("role", "section")
        self.det_card.body().addWidget(det_header)
        self.row_os = KeyValueRow("OS", "\u2014", mono=False)
        self.row_cpu_cores = KeyValueRow("CPU cores", "\u2014")
        self.row_gpu_list = KeyValueRow("GPU(s)", "\u2014")
        self.row_driver = KeyValueRow("NVIDIA driver", "\u2014")
        for r in [self.row_os, self.row_cpu_cores, self.row_gpu_list, self.row_driver]:
            self.det_card.body().addWidget(r)
        root.addWidget(self.det_card)

        root.addStretch()

        self.store.hardware_changed.connect(self.render)
        self.render(self.store.hardware)

    def render(self, hw: HardwareSpec):
        self.cpu_tile.set_value(hw.cpu_name or "\u2014",
                                f"{hw.cpu_cores_physical}c / {hw.cpu_cores_logical}t")
        self.ram_tile.set_value(f"{hw.ram_total_gb:.0f} GB",
                                f"{hw.ram_available_gb:.0f} GB available")
        if hw.gpus:
            names = ", ".join(g.name.replace("NVIDIA GeForce ", "") for g in hw.gpus)
            self.gpu_tile.set_value(names, f"{len(hw.gpus)}x detected")
            total_vram = sum(g.vram_total_gb for g in hw.gpus)
            cuda_label = "CUDA-capable" if any(g.cuda_capable for g in hw.gpus) else "no CUDA"
            self.vram_tile.set_value(f"{total_vram:.0f} GB", cuda_label)
        else:
            self.gpu_tile.set_value("None detected", "CPU-only mode")
            self.vram_tile.set_value("\u2014", "\u2014")
        self.disk_tile.set_value(f"{hw.disk_free_gb:.0f} GB",
                                 f"of {hw.disk_total_gb:.0f} GB")
        self.backend_tile.set_value(hw.best_backend.upper(),
                                    "recommended for this box")

        cap = estimate_capacity(hw)
        tier_to_level = {"excellent": "ok", "strong": "ok", "good": "info",
                         "limited": "warn", "weak": "err"}
        self.cap_pill.set_status(cap.tier.upper(), tier_to_level.get(cap.tier, "info"))
        self.cap_headline.setText(cap.headline)
        while self.cap_notes.count():
            w = self.cap_notes.takeAt(0).widget()
            if w:
                w.deleteLater()
        for n in cap.notes:
            row = QLabel(f"\u2022  {n}")
            row.setProperty("role", "muted")
            self.cap_notes.addWidget(row)

        self.row_os.set_value(f"{hw.os_name} {hw.os_version}")
        self.row_cpu_cores.set_value(
            f"{hw.cpu_cores_physical} physical / {hw.cpu_cores_logical} logical")
        self.row_gpu_list.set_value(
            ", ".join(g.name for g in hw.gpus) if hw.gpus else "none")
        drivers = {g.driver for g in hw.gpus if g.driver}
        self.row_driver.set_value(", ".join(sorted(drivers)) if drivers else "\u2014")
