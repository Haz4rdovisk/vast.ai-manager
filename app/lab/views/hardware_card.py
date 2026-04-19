"""Card component for hardware monitoring — glassmorphism polish."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt
from app import theme as t
from app.ui.components.gauge import GaugeWidget
from app.ui.components.network_widget import NetworkSpeedWidget
from app.ui.components.thermometer import ThermometerWidget
from app.lab.state.models import LabInstanceState


from app.ui.components.primitives import GlassCard


class HardwareCard(GlassCard):
    def __init__(self, iid: int, gpu_name: str = "GPU", parent=None):
        super().__init__(parent)
        self.iid = iid
        self._metric_cols: int | None = None
        self.setMinimumWidth(360)
        self.setMinimumHeight(340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = self.body()
        lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)

        # Header
        header = QHBoxLayout()
        self.title_lbl = QLabel(f"Instance #{iid}")
        self.title_lbl.setStyleSheet(
            f"font-size: 15pt; font-weight: 700; color: {t.TEXT_HI};"
        )
        header.addWidget(self.title_lbl)
        header.addStretch()

        self.gpu_lbl = QLabel(gpu_name)
        self.gpu_lbl.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px;"
        )
        header.addWidget(self.gpu_lbl)
        lay.addLayout(header)
        lay.addSpacing(t.SPACE_2)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(t.SPACE_4)

        # Gauges grid, reflowed by card width.
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setHorizontalSpacing(t.SPACE_4)
        self.metrics_grid.setVerticalSpacing(t.SPACE_3)

        self.gauge_cpu = GaugeWidget("CPU Load")
        self.gauge_ram = GaugeWidget("RAM Usage")
        self.gauge_disk = GaugeWidget("Disk /work")
        self.gauge_gpu = GaugeWidget("GPU Load")
        self.gauge_vram = GaugeWidget("VRAM Usage")
        self.net_widget = NetworkSpeedWidget()

        self.metric_widgets = [
            self._wrap(self.gauge_cpu),
            self._wrap(self.gauge_ram),
            self._wrap(self.gauge_disk),
            self._wrap(self.gauge_gpu),
            self._wrap(self.gauge_vram),
            self._wrap(self.net_widget),
        ]
        self._arrange_metrics()

        content.addLayout(self.metrics_grid, 1)

        self.thermo = ThermometerWidget()
        content.addWidget(self.thermo, 0, Qt.AlignRight | Qt.AlignVCenter)
        lay.addLayout(content, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        self.status_lbl = QLabel("Live telemetry")
        self.status_lbl.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px; font-weight: 650;"
        )
        footer.addWidget(self.status_lbl)
        footer.addStretch()
        self.uptime_lbl = QLabel("Uptime: --")
        self.uptime_lbl.setProperty("role", "muted")
        footer.addWidget(self.uptime_lbl)
        lay.addLayout(footer)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_metrics()

    def _metric_column_count(self) -> int:
        content_w = max(0, self.width() - (t.SPACE_4 * 2) - 96)
        if content_w >= 600:
            return 3
        if content_w >= 280:
            return 2
        return 1

    def _arrange_metrics(self) -> None:
        cols = self._metric_column_count()
        if cols == self._metric_cols and self.metrics_grid.count():
            return
        self._metric_cols = cols

        while self.metrics_grid.count():
            self.metrics_grid.takeAt(0)

        for index, widget in enumerate(self.metric_widgets):
            row = index // cols
            col = index % cols
            self.metrics_grid.addWidget(widget, row, col)
            widget.show()

        for col in range(3):
            self.metrics_grid.setColumnStretch(col, 0)
        for col in range(cols):
            self.metrics_grid.setColumnStretch(col, 1)

    def _wrap(self, widget):
        container = QFrame()
        container.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        return container

    def update_state(self, state: LabInstanceState):
        self.title_lbl.setText(f"Instance #{state.iid}")
        sys = state.system

        if sys.gpu_name:
            self.gpu_lbl.setText(sys.gpu_name)

        ram_used = sys.ram_total_gb * (sys.ram_usage_pct / 100)
        vram_used = (sys.gpu_vram_gb or 0) * (sys.gpu_vram_usage_pct / 100)

        self.gauge_cpu.setValue(sys.cpu_usage_pct, f"{sys.cpu_cores} CORES")
        self.gauge_ram.setValue(
            sys.ram_usage_pct,
            f"{ram_used:.1f} / {sys.ram_total_gb:.0f} GB"
        )
        self.gauge_disk.setValue(
            sys.disk_usage_pct,
            f"{sys.disk_used_gb:.1f} / {sys.disk_total_gb:.0f} GB"
        )
        self.gauge_gpu.setValue(
            sys.gpu_usage_pct,
            f"{sys.gpu_count} GPU" if sys.gpu_count > 0 else ""
        )
        self.gauge_vram.setValue(
            sys.gpu_vram_usage_pct,
            f"{vram_used:.1f} / {sys.gpu_vram_gb or 0:.0f} GB"
        )
        self.net_widget.set_speeds(sys.net_rx_kbps, sys.net_tx_kbps)

        temp_c = t.temp_color(sys.gpu_temp)
        self.thermo.set_temperature(sys.gpu_temp)
        self.status_lbl.setText(
            "GPU thermal nominal" if sys.gpu_temp < 70 else "GPU thermal watch"
        )
        self.status_lbl.setStyleSheet(
            f"color: {temp_c}; font-size: {t.FONT_SIZE_SMALL}px; font-weight: 700;"
        )

        h = sys.uptime_seconds // 3600
        m = (sys.uptime_seconds % 3600) // 60
        self.uptime_lbl.setText(f"Uptime: {h}h {m}m")
