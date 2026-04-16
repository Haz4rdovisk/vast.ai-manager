from __future__ import annotations
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Signal, Qt
from app import theme
from app.models import Instance, InstanceState, TunnelStatus
from app.ui.metric_bar import MetricBar


STATE_LABELS = {
    InstanceState.STOPPED: ("○ Desativada", theme.TEXT_SECONDARY),
    InstanceState.STARTING: ("◌ Ativando...", theme.WARNING),
    InstanceState.RUNNING: ("● Ativa", theme.SUCCESS),
    InstanceState.STOPPING: ("◌ Desativando...", theme.WARNING),
    InstanceState.UNKNOWN: ("? Desconhecido", theme.TEXT_SECONDARY),
}

TUNNEL_LABELS = {
    TunnelStatus.DISCONNECTED: ("Desconectado", theme.INFO),
    TunnelStatus.CONNECTING: ("Conectando...", theme.WARNING),
    TunnelStatus.CONNECTED: ("Conectado", theme.SUCCESS),
    TunnelStatus.FAILED: ("Falha de conexão", theme.DANGER),
}


def _format_duration(seconds: int | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


class InstanceCard(QFrame):
    activate_requested = Signal(int)
    deactivate_requested = Signal(int)
    reconnect_requested = Signal(int)
    disconnect_requested = Signal(int)
    open_terminal_requested = Signal(int)
    models_requested = Signal(int)
    copy_endpoint_requested = Signal(int)

    def __init__(self, instance: Instance, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.instance = instance
        self.tunnel_status = TunnelStatus.DISCONNECTED
        self.local_port = 11434
        # Most recent live metrics from the in-container nvidia-smi/proc poller.
        # Overrides the slow Vast API values whenever present.
        self._live: dict = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        # Header row
        header = QHBoxLayout()
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("h2")
        self.gpu_lbl = QLabel()
        self.gpu_lbl.setObjectName("secondary")
        self.gpu_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.status_lbl)
        header.addStretch()
        header.addWidget(self.gpu_lbl)
        lay.addLayout(header)

        self.subtitle_lbl = QLabel()
        self.subtitle_lbl.setObjectName("secondary")
        lay.addWidget(self.subtitle_lbl)

        # Hardware / location row — small grey text, wraps if long.
        self.details_lbl = QLabel()
        self.details_lbl.setObjectName("secondary")
        self.details_lbl.setWordWrap(True)
        self.details_lbl.setStyleSheet("font-size: 9pt;")
        lay.addWidget(self.details_lbl)

        # Metrics container
        self.metrics_container = QFrame()
        self.metrics_container.setStyleSheet("QFrame { background: transparent; border: none; }")
        mlay = QVBoxLayout(self.metrics_container)
        mlay.setContentsMargins(0, 6, 0, 6)
        mlay.setSpacing(6)
        self.gpu_bar = MetricBar("GPU")
        self.vram_bar = MetricBar("vRAM")
        self.cpu_bar = MetricBar("CPU")
        self.ram_bar = MetricBar("RAM")
        self.disk_bar = MetricBar("Disco")
        self.net_lbl = QLabel("Rede   ↓ — / ↑ —")
        self.net_lbl.setObjectName("secondary")
        mlay.addWidget(self.gpu_bar)
        mlay.addWidget(self.vram_bar)
        mlay.addWidget(self.cpu_bar)
        mlay.addWidget(self.ram_bar)
        mlay.addWidget(self.disk_bar)
        mlay.addWidget(self.net_lbl)
        lay.addWidget(self.metrics_container)

        # Endpoint row
        self.endpoint_wrap = QFrame()
        self.endpoint_wrap.setStyleSheet("QFrame { background: transparent; border: none; }")
        endpoint_layout = QHBoxLayout(self.endpoint_wrap)
        endpoint_layout.setContentsMargins(0, 4, 0, 4)
        self.endpoint_lbl = QLabel("")
        self.endpoint_lbl.setObjectName("mono")
        self.endpoint_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.copy_btn = QPushButton("Copiar")
        self.copy_btn.setObjectName("secondary")
        self.copy_btn.setFixedWidth(80)
        self.copy_btn.clicked.connect(lambda: self.copy_endpoint_requested.emit(self.instance.id))
        endpoint_layout.addWidget(self.endpoint_lbl)
        endpoint_layout.addStretch()
        endpoint_layout.addWidget(self.copy_btn)
        lay.addWidget(self.endpoint_wrap)

        # Loaded-model badge — visible whenever the model watcher reports a
        # llama-server with at least one model loaded behind the tunnel.
        self.model_badge = QLabel()
        self.model_badge.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.model_badge.setStyleSheet(
            f"QLabel {{ background: {theme.CARD_BORDER}; color: {theme.TEXT};"
            f" border-radius: 10px; padding: 4px 10px;"
            f" font-family: Consolas, 'Courier New', monospace; font-size: 9pt; }}"
        )
        self.model_badge.setVisible(False)
        self._loaded_model: str | None = None
        lay.addWidget(self.model_badge)

        # Action buttons
        actions = QHBoxLayout()
        self.primary_btn = QPushButton()
        self.primary_btn.clicked.connect(self._on_primary_click)
        self.terminal_btn = QPushButton("Terminal")
        self.terminal_btn.setObjectName("secondary")
        self.terminal_btn.clicked.connect(lambda: self.open_terminal_requested.emit(self.instance.id))
        self.models_btn = QPushButton("Deploy Modelos")
        self.models_btn.setObjectName("secondary")
        self.models_btn.clicked.connect(lambda: self.models_requested.emit(self.instance.id))
        self.disconnect_btn = QPushButton("Desconectar")
        self.disconnect_btn.setObjectName("secondary")
        self.disconnect_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.instance.id))
        self.deactivate_btn = QPushButton("Desativar")
        self.deactivate_btn.setObjectName("danger")
        self.deactivate_btn.clicked.connect(lambda: self.deactivate_requested.emit(self.instance.id))
        actions.addWidget(self.primary_btn)
        actions.addWidget(self.models_btn)
        actions.addWidget(self.terminal_btn)
        actions.addWidget(self.disconnect_btn)
        actions.addStretch()
        actions.addWidget(self.deactivate_btn)
        lay.addLayout(actions)

        self.update_from(instance, self.tunnel_status, self.local_port)

    def _on_primary_click(self):
        if self.instance.state == InstanceState.STOPPED:
            self.activate_requested.emit(self.instance.id)
        elif self.tunnel_status in (TunnelStatus.FAILED, TunnelStatus.DISCONNECTED) and self.instance.state == InstanceState.RUNNING:
            self.reconnect_requested.emit(self.instance.id)

    def update_from(self, inst: Instance, tunnel_status: TunnelStatus, local_port: int):
        self.instance = inst
        self.tunnel_status = tunnel_status
        self.local_port = local_port

        # Header: explicitly distinguish between instance lifecycle and local tunnel
        label, color = STATE_LABELS.get(inst.state, STATE_LABELS[InstanceState.UNKNOWN])

        if inst.state == InstanceState.RUNNING:
            t_label, t_color = TUNNEL_LABELS[tunnel_status]
            # Use span style to dynamically build the header
            self.status_lbl.setText(
                f"<span style='color: {color}'>{label}</span>"
                f" <span style='color: {theme.TEXT_SECONDARY}'>&nbsp;&nbsp;·&nbsp;&nbsp;Túnel:</span>"
                f" <span style='color: {t_color}'>{t_label}</span>"
            )
            # Remove direct stylesheet color to avoid overriding HTML spans
            self.status_lbl.setStyleSheet("font-weight: 600;")
        else:
            self.status_lbl.setText(label)
            self.status_lbl.setStyleSheet(f"color: {color}; font-weight: 600;")

        gpu_part = f"{inst.num_gpus}× {inst.gpu_name}" if inst.num_gpus > 1 else inst.gpu_name
        self.gpu_lbl.setText(f"{gpu_part} · {inst.gpu_ram_gb:.0f} GB VRAM")

        parts = []
        if inst.image:
            parts.append(inst.image)
        parts.append(f"${inst.dph:.2f}/h")
        if inst.state == InstanceState.RUNNING and inst.duration_seconds:
            parts.append(f"ativa há {_format_duration(inst.duration_seconds)}")
        self.subtitle_lbl.setText(" · ".join(parts))

        self.details_lbl.setText(self._format_details(inst))

        # Metrics visibility — only show live telemetry while RUNNING AND CONNECTED.
        # Reset bars on transition out so a future RUNNING doesn't flash old values.
        is_running = inst.state == InstanceState.RUNNING
        is_connected_for_metrics = is_running and tunnel_status == TunnelStatus.CONNECTED
        
        self.metrics_container.setVisible(is_connected_for_metrics)
        if not is_connected_for_metrics:
            for bar in (self.gpu_bar, self.vram_bar, self.cpu_bar,
                        self.ram_bar, self.disk_bar):
                bar.set_value(None)
            self.net_lbl.setText("Rede   ↓ — / ↑ —")
            self._live = {}
        if is_connected_for_metrics:
            gpu_text = None
            if inst.gpu_util is not None:
                temp = f"  {inst.gpu_temp:.0f}°C" if inst.gpu_temp is not None else ""
                gpu_text = f"{inst.gpu_util:.0f}%{temp}"
            self.gpu_bar.set_value(inst.gpu_util, gpu_text)
            
            if inst.vram_usage_gb is not None and inst.gpu_ram_gb:
                vram_pct = (inst.vram_usage_gb / inst.gpu_ram_gb) * 100.0
                self.vram_bar.set_value(vram_pct, f"{inst.vram_usage_gb:.1f} / {inst.gpu_ram_gb:.1f} GB")
            else:
                self.vram_bar.set_value(None)

            cpu_text = f"{inst.cpu_util:.0f}%" if inst.cpu_util is not None else None
            self.cpu_bar.set_value(inst.cpu_util, cpu_text)
            
            if inst.ram_total_gb and inst.ram_used_gb is not None:
                pct = (inst.ram_used_gb / inst.ram_total_gb) * 100
                self.ram_bar.set_value(pct, f"{pct:.0f}% ({inst.ram_used_gb:.0f} / {inst.ram_total_gb:.0f} GB)")
            else:
                self.ram_bar.set_value(None)
                
            if inst.disk_space_gb and inst.disk_usage_gb is not None:
                disk_pct = (inst.disk_usage_gb / inst.disk_space_gb) * 100.0
                self.disk_bar.set_value(disk_pct, f"{inst.disk_usage_gb:.0f} / {inst.disk_space_gb:.0f} GB")
            else:
                self.disk_bar.set_value(None)
                
            down = f"{inst.inet_down_mbps:.1f}" if inst.inet_down_mbps is not None else "—"
            up = f"{inst.inet_up_mbps:.1f}" if inst.inet_up_mbps is not None else "—"
            self.net_lbl.setText(f"Rede   ↓ {down} Mbps  /  ↑ {up} Mbps")

        # Endpoint row
        show_endpoint = is_running and tunnel_status == TunnelStatus.CONNECTED
        self.endpoint_wrap.setVisible(show_endpoint)
        if show_endpoint:
            self.endpoint_lbl.setText(f"🔗  http://127.0.0.1:{local_port}")

        # Hide model badge if the tunnel went away — the cached id is stale
        # the moment we lose the link to llama-server.
        if not show_endpoint:
            self.model_badge.setVisible(False)
        elif self._loaded_model:
            self.model_badge.setVisible(True)

        # Apply any live overlay AFTER Vast values, so the card always shows
        # the freshest numbers we have.
        if is_running and self._live:
            self._apply_live_overlay()

        self._update_buttons()

    def set_live_metrics(self, d: dict):
        """Push real-time telemetry from the in-container poller. Overrides
        the slow Vast API values for whichever fields are present."""
        self._live = d or {}
        if self.instance.state == InstanceState.RUNNING:
            self._apply_live_overlay()

    def clear_live_metrics(self):
        self._live = {}

    def set_loaded_model(self, model_id: str | None):
        """Show or hide the model pill. Pass None/'' to hide."""
        mid = (model_id or "").strip()
        self._loaded_model = mid or None
        if not mid:
            self.model_badge.setVisible(False)
            self.model_badge.setText("")
            return
        # Trim huge HF-style ids for display but keep full text selectable
        # via tooltip / copy.
        display = mid if len(mid) <= 60 else "…" + mid[-58:]
        self.model_badge.setText(f"🤖  {display}")
        self.model_badge.setToolTip(mid)
        # Only show if the endpoint row is visible (tunnel up + RUNNING).
        if self.endpoint_wrap.isVisible():
            self.model_badge.setVisible(True)

    @staticmethod
    def _format_details(inst: Instance) -> str:
        """Build the small grey hardware/location line under the subtitle.
        Each segment only appears when Vast actually returned the field."""
        bits: list[str] = []
        if inst.geolocation:
            bits.append(f"📍 {inst.geolocation}")
        elif inst.country:
            bits.append(f"📍 {inst.country}")
        if inst.hostname:
            bits.append(f"🖥 {inst.hostname}")
        elif inst.host_id:
            bits.append(f"🖥 host #{inst.host_id}")
        if inst.datacenter:
            bits.append(f"🏢 {inst.datacenter}")
        elif inst.hosting_type:
            bits.append(inst.hosting_type)
        if inst.cpu_name:
            cores = f" ({inst.cpu_cores}c)" if inst.cpu_cores else ""
            bits.append(f"🧠 {inst.cpu_name}{cores}")
        if inst.cuda_max_good:
            bits.append(f"CUDA ≤ {inst.cuda_max_good:g}")
        if inst.pcie_gen:
            pcie = f"PCIe Gen {inst.pcie_gen:g}"
            if inst.pcie_bw_gbps:
                pcie += f" · {inst.pcie_bw_gbps:.1f} GB/s"
            bits.append(pcie)
        if inst.disk_bw_mbps:
            bits.append(f"Disco {inst.disk_bw_mbps:.0f} MB/s")
        if inst.dlperf:
            bits.append(f"DLPerf {inst.dlperf:.1f}")
        if inst.reliability is not None:
            # Vast returns 0..1; render as percent
            r = inst.reliability * 100 if inst.reliability <= 1.0 else inst.reliability
            bits.append(f"⚡ {r:.1f}%")
        return "  ·  ".join(bits)

    def _apply_live_overlay(self):
        d = self._live
        if "gpu_util" in d:
            temp_str = f"  {d['gpu_temp']:.0f}°C" if "gpu_temp" in d else ""
            self.gpu_bar.set_value(d["gpu_util"], f"{d['gpu_util']:.0f}%{temp_str}")
        if "vram_used_mb" in d and "vram_total_mb" in d and d["vram_total_mb"] > 0:
            used_gb = d["vram_used_mb"] / 1024.0
            total_gb = d["vram_total_mb"] / 1024.0
            pct = used_gb / total_gb * 100.0
            self.vram_bar.set_value(pct, f"{used_gb:.1f} / {total_gb:.1f} GB")
        if "ram_used_mb" in d and "ram_total_mb" in d and d["ram_total_mb"] > 0:
            used_gb = d["ram_used_mb"] / 1024.0
            total_gb = d["ram_total_mb"] / 1024.0
            pct = used_gb / total_gb * 100.0
            self.ram_bar.set_value(pct, f"{pct:.0f}% ({used_gb:.0f} / {total_gb:.0f} GB)")
        if "load1" in d and self.instance.cpu_cores:
            cpu_pct = min(100.0, d["load1"] / max(1, self.instance.cpu_cores) * 100.0)
            self.cpu_bar.set_value(cpu_pct, f"{cpu_pct:.0f}%")
        if "disk_used_gb" in d and "disk_total_gb" in d and d["disk_total_gb"] > 0:
            pct = d["disk_used_gb"] / d["disk_total_gb"] * 100.0
            self.disk_bar.set_value(
                pct, f"{d['disk_used_gb']:.0f} / {d['disk_total_gb']:.0f} GB",
            )

    def _update_buttons(self):
        state = self.instance.state
        tunnel = self.tunnel_status

        if state == InstanceState.STOPPED:
            self.primary_btn.setText("Ativar")
            self.primary_btn.setVisible(True)
            self.primary_btn.setEnabled(True)
            self.terminal_btn.setVisible(False)
            self.models_btn.setVisible(False)
            self.disconnect_btn.setVisible(False)
            self.deactivate_btn.setVisible(False)
        elif state == InstanceState.STARTING:
            self.primary_btn.setText("Ativando...")
            self.primary_btn.setVisible(True)
            self.primary_btn.setEnabled(False)
            self.terminal_btn.setVisible(False)
            self.models_btn.setVisible(False)
            self.disconnect_btn.setVisible(False)
            self.deactivate_btn.setVisible(True)
            self.deactivate_btn.setEnabled(True)
        elif state == InstanceState.STOPPING:
            self.primary_btn.setText("Desativando...")
            self.primary_btn.setVisible(True)
            self.primary_btn.setEnabled(False)
            self.terminal_btn.setVisible(False)
            self.models_btn.setVisible(False)
            self.disconnect_btn.setVisible(False)
            self.deactivate_btn.setVisible(False)
        elif state == InstanceState.RUNNING:
            self.terminal_btn.setVisible(True)
            self.deactivate_btn.setVisible(True)
            self.deactivate_btn.setEnabled(True)
            if tunnel == TunnelStatus.CONNECTED:
                self.models_btn.setVisible(True)
                self.primary_btn.setVisible(False)
                self.disconnect_btn.setVisible(True)
            elif tunnel == TunnelStatus.CONNECTING:
                self.models_btn.setVisible(False)
                self.primary_btn.setText("Conectando...")
                self.primary_btn.setVisible(True)
                self.primary_btn.setEnabled(False)
                self.disconnect_btn.setVisible(False)
            elif tunnel == TunnelStatus.FAILED:
                self.models_btn.setVisible(False)
                self.primary_btn.setText("Tentar novamente")
                self.primary_btn.setVisible(True)
                self.primary_btn.setEnabled(True)
                self.disconnect_btn.setVisible(False)
            else:
                self.models_btn.setVisible(False)
                self.primary_btn.setText("Conectar")
                self.primary_btn.setVisible(True)
                self.primary_btn.setEnabled(True)
                self.disconnect_btn.setVisible(False)
        else:
            self.primary_btn.setVisible(False)
            self.terminal_btn.setVisible(False)
            self.models_btn.setVisible(False)
            self.disconnect_btn.setVisible(False)
            self.deactivate_btn.setVisible(False)
