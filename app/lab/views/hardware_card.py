"""Card component for hardware monitoring of a single instance."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
from PySide6.QtCore import Qt
from app import theme as t
from app.ui.components.gauge import GaugeWidget
from app.ui.components.network_widget import NetworkSpeedWidget
from app.lab.state.models import LabInstanceState

class HardwareCard(QFrame):
    def __init__(self, iid: int, gpu_name: str = "GPU", parent=None):
        super().__init__(parent)
        self.iid = iid
        self.setObjectName("hw-card")
        self.setProperty("role", "card")
        self.setMinimumWidth(650)
        self.setMaximumWidth(1300)
        self.setMinimumHeight(450)
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_5)
        
        # Header: Name & Type
        header = QHBoxLayout()
        self.title_lbl = QLabel(f"Instance #{iid}")
        self.title_lbl.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {t.TEXT_HI};")
        header.addWidget(self.title_lbl)
        header.addStretch()
        
        self.gpu_lbl = QLabel(gpu_name)
        self.gpu_lbl.setProperty("role", "muted")
        header.addWidget(self.gpu_lbl)
        lay.addLayout(header)
        lay.addSpacing(t.SPACE_3)
        
        # Gauges Grid (2x2)
        grid = QGridLayout()
        grid.setSpacing(t.SPACE_3)
        
        self.gauge_cpu = GaugeWidget("CPU Load")
        self.gauge_ram = GaugeWidget("RAM Usage")
        self.gauge_disk = GaugeWidget("Disk /work")
        self.gauge_gpu = GaugeWidget("GPU Load")
        self.gauge_vram = GaugeWidget("VRAM Usage")
        self.net_widget = NetworkSpeedWidget()
        
        # Niches styling (wrap gauges in cards)
        # Row 0: CPU, RAM, DISK
        grid.addWidget(self._wrap(self.gauge_cpu), 0, 0)
        grid.addWidget(self._wrap(self.gauge_ram), 0, 1)
        grid.addWidget(self._wrap(self.gauge_disk), 0, 2)
        # Row 1: GPU, VRAM, NET
        grid.addWidget(self._wrap(self.gauge_gpu), 1, 0)
        grid.addWidget(self._wrap(self.gauge_vram), 1, 1)
        grid.addWidget(self._wrap(self.net_widget), 1, 2)
        
        # KEY: Force all columns to have same stretch for perfect symmetry
        for c in range(3):
            grid.setColumnStretch(c, 1)
            
        lay.addLayout(grid)
        
        # Footer: Temp & Uptime
        footer = QHBoxLayout()
        self.temp_lbl = QLabel("Temp: --")
        self.temp_lbl.setProperty("role", "muted")
        footer.addWidget(self.temp_lbl)
        footer.addStretch()
        self.uptime_lbl = QLabel("Uptime: --")
        self.uptime_lbl.setProperty("role", "muted")
        footer.addWidget(self.uptime_lbl)
        lay.addLayout(footer)

    def _wrap(self, widget):
        container = QFrame()
        container.setProperty("role", "card-raised")
        clay = QVBoxLayout(container)
        clay.addWidget(widget)
        return container

    def update_state(self, state: LabInstanceState):
        self.title_lbl.setText(f"Instance #{state.iid}")
        sys = state.system
        
        if sys.gpu_name:
            self.gpu_lbl.setText(sys.gpu_name)
        
        # Calculate subtexts
        ram_used = sys.ram_total_gb * (sys.ram_usage_pct / 100)
        vram_used = (sys.gpu_vram_gb or 0) * (sys.gpu_vram_usage_pct / 100)
        
        self.gauge_cpu.setValue(sys.cpu_usage_pct, f"{sys.cpu_cores} CORES")
        self.gauge_ram.setValue(sys.ram_usage_pct, f"{ram_used:.1f} / {sys.ram_total_gb:.0f} GB")
        self.gauge_disk.setValue(sys.disk_usage_pct, f"{sys.disk_used_gb:.1f} / {sys.disk_total_gb:.0f} GB")
        
        self.gauge_gpu.setValue(sys.gpu_usage_pct, f"{sys.gpu_count} GPU" if sys.gpu_count > 0 else "")
        self.gauge_vram.setValue(sys.gpu_vram_usage_pct, f"{vram_used:.1f} / {sys.gpu_vram_gb or 0:.0f} GB")
        self.net_widget.set_speeds(sys.net_rx_kbps, sys.net_tx_kbps)
        
        self.temp_lbl.setText(f"GPU Temp: {sys.gpu_temp:.0f}\u00B0C")
        
        # Basic uptime display
        h = sys.uptime_seconds // 3600
        m = (sys.uptime_seconds % 3600) // 60
        self.uptime_lbl.setText(f"Uptime: {h}h {m}m")
