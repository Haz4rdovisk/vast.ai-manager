"""Instance card — dashboard-style dark surface built from the new design
system. Preserves every signal/state from the Cloud version so AppController
wiring is unchanged."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QSizePolicy, QWidget,
)
from app import theme as t
from app.models import Instance, InstanceState, TunnelStatus
from app.ui.components.primitives import GlassCard, SectionHeader, StatusPill


STATE_LABELS = {
    InstanceState.STOPPED:  ("○ Desativada",    "muted"),
    InstanceState.STARTING: ("◌ Ativando…",     "warn"),
    InstanceState.RUNNING:  ("● Ativa",         "ok"),
    InstanceState.STOPPING: ("◌ Desativando…",  "warn"),
    InstanceState.UNKNOWN:  ("? Desconhecido",  "muted"),
}

TUNNEL_LABELS = {
    TunnelStatus.DISCONNECTED: ("Desconectado", "info"),
    TunnelStatus.CONNECTING:   ("Conectando…",  "warn"),
    TunnelStatus.CONNECTED:    ("Conectado",    "live"),
    TunnelStatus.FAILED:       ("Falha",        "err"),
}


def _fmt_duration(seconds: int | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    h, r = divmod(seconds, 3600)
    m, _ = divmod(r, 60)
    return f"{h}h {m}m" if h else f"{m}m"


class _Bar(QWidget):
    """Inline labeled progress bar. Replaces the old MetricBar."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(10)
        self.k = QLabel(label); self.k.setFixedWidth(56)
        self.k.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 9pt;")
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.v = QLabel("—")
        self.v.setAlignment(Qt.AlignRight | Qt.AlignVCenter); self.v.setMinimumWidth(140)
        self.v.setStyleSheet(f"color: {t.TEXT}; font-family: {t.FONT_MONO}; font-size: 9pt;")
        h.addWidget(self.k); h.addWidget(self.bar, 1); h.addWidget(self.v)
        self._color(t.TEXT_MID)

    def set_value(self, percent: float | None, text: str | None = None):
        if percent is None:
            self.bar.setValue(0); self.v.setText("—"); self._color(t.TEXT_MID); return
        p = max(0.0, min(100.0, percent))
        self.bar.setValue(int(p))
        self.v.setText(text if text is not None else f"{p:.0f}%")
        self._color(t.metric_color(p))

    def _color(self, color: str):
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {t.SURFACE_3}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )


class InstanceCard(GlassCard):
    activate_requested      = Signal(int)
    deactivate_requested    = Signal(int)
    reconnect_requested     = Signal(int)
    disconnect_requested    = Signal(int)
    open_terminal_requested = Signal(int)
    open_lab_requested      = Signal(int)  # renamed from models_requested
    copy_endpoint_requested = Signal(int)

    def __init__(self, instance: Instance, parent=None):
        super().__init__(parent=parent)
        self.instance = instance
        self.tunnel_status = TunnelStatus.DISCONNECTED
        self.local_port = 11434
        self._live: dict = {}
        self._loaded_model: str | None = None

        # ---- Header: state pill + gpu line ----
        head = QHBoxLayout()
        self.state_pill = StatusPill("—", "muted")
        head.addWidget(self.state_pill)
        head.addStretch()
        self.gpu_lbl = QLabel("")
        self.gpu_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 10pt;")
        head.addWidget(self.gpu_lbl)
        self._lay.addLayout(head)

        # ---- Title row: instance label + hourly cost ----
        title_row = QHBoxLayout()
        self.title_lbl = QLabel("")
        self.title_lbl.setProperty("role", "title")
        self.cost_lbl = QLabel("")
        self.cost_lbl.setStyleSheet(
            f"color: {t.ACCENT}; font-size: 11pt; font-weight: 700; font-family: {t.FONT_MONO};"
        )
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        title_row.addWidget(self.cost_lbl)
        self._lay.addLayout(title_row)

        # ---- Subtitle: image + uptime ----
        self.subtitle_lbl = QLabel("")
        self.subtitle_lbl.setProperty("role", "muted")
        self.subtitle_lbl.setWordWrap(True)
        self._lay.addWidget(self.subtitle_lbl)

        # ---- Hardware detail line ----
        self.details_lbl = QLabel("")
        self.details_lbl.setProperty("role", "muted")
        self.details_lbl.setWordWrap(True)
        self.details_lbl.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 9pt;")
        self._lay.addWidget(self.details_lbl)

        # ---- Metrics container (visible only when CONNECTED) ----
        self.metrics_container = QFrame()
        self.metrics_container.setStyleSheet("QFrame { background: transparent; border: none; }")
        m = QVBoxLayout(self.metrics_container)
        m.setContentsMargins(0, t.SPACE_2, 0, t.SPACE_2); m.setSpacing(t.SPACE_2)
        self.gpu_bar  = _Bar("GPU")
        self.vram_bar = _Bar("vRAM")
        self.cpu_bar  = _Bar("CPU")
        self.ram_bar  = _Bar("RAM")
        self.disk_bar = _Bar("Disco")
        self.net_lbl  = QLabel("Rede   ↓ — / ↑ —")
        self.net_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 9pt;")
        for b in (self.gpu_bar, self.vram_bar, self.cpu_bar, self.ram_bar, self.disk_bar):
            m.addWidget(b)
        m.addWidget(self.net_lbl)
        self._lay.addWidget(self.metrics_container)

        # ---- Endpoint row ----
        self.endpoint_wrap = QFrame()
        self.endpoint_wrap.setStyleSheet("QFrame { background: transparent; border: none; }")
        er = QHBoxLayout(self.endpoint_wrap); er.setContentsMargins(0, 0, 0, 0)
        self.endpoint_lbl = QLabel("")
        self.endpoint_lbl.setProperty("role", "mono")
        self.endpoint_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.copy_btn = QPushButton("Copiar")
        self.copy_btn.setProperty("variant", "ghost")
        self.copy_btn.setFixedWidth(88)
        self.copy_btn.clicked.connect(lambda: self.copy_endpoint_requested.emit(self.instance.id))
        er.addWidget(self.endpoint_lbl); er.addStretch(); er.addWidget(self.copy_btn)
        self._lay.addWidget(self.endpoint_wrap)

        # ---- Model badge ----
        self.model_badge = QLabel("")
        self.model_badge.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.model_badge.setStyleSheet(
            f"QLabel {{ background: {t.SURFACE_2}; color: {t.TEXT};"
            f" border: 1px solid {t.BORDER_MED};"
            f" border-radius: 999px; padding: 4px 12px;"
            f" font-family: {t.FONT_MONO}; font-size: 9pt; }}"
        )
        self.model_badge.setVisible(False)
        self._lay.addWidget(self.model_badge)

        # ---- Actions row ----
        actions = QHBoxLayout()
        self.primary_btn      = QPushButton(""); self.primary_btn.clicked.connect(self._on_primary)
        self.lab_btn          = QPushButton("Abrir no Lab"); self.lab_btn.setProperty("variant", "ghost")
        self.lab_btn.clicked.connect(lambda: self.open_lab_requested.emit(self.instance.id))
        self.terminal_btn     = QPushButton("Terminal"); self.terminal_btn.setProperty("variant", "ghost")
        self.terminal_btn.clicked.connect(lambda: self.open_terminal_requested.emit(self.instance.id))
        self.disconnect_btn   = QPushButton("Desconectar"); self.disconnect_btn.setProperty("variant", "ghost")
        self.disconnect_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.instance.id))
        self.deactivate_btn   = QPushButton("Desativar"); self.deactivate_btn.setProperty("variant", "danger")
        self.deactivate_btn.clicked.connect(lambda: self.deactivate_requested.emit(self.instance.id))
        for b in (self.primary_btn, self.lab_btn, self.terminal_btn, self.disconnect_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(self.deactivate_btn)
        self._lay.addLayout(actions)

        self.update_from(instance, self.tunnel_status, self.local_port)

    # ---- Public API used by the Instances view ----
    def update_from(self, inst: Instance, tunnel_status: TunnelStatus, local_port: int):
        """Identical contract to the old card — see [instance_card.py:166-263]
        for the full state machine. Reimplemented against the new widgets."""
        self.instance = inst
        self.tunnel_status = tunnel_status
        self.local_port = local_port

        label, level = STATE_LABELS.get(inst.state, STATE_LABELS[InstanceState.UNKNOWN])
        if inst.state == InstanceState.RUNNING:
            t_label, t_level = TUNNEL_LABELS[tunnel_status]
            self.state_pill.set_status(f"{label}  ·  {t_label}", t_level)
        else:
            self.state_pill.set_status(label, level)

        gpu_part = f"{inst.num_gpus}× {inst.gpu_name}" if inst.num_gpus > 1 else (inst.gpu_name or "GPU")
        self.gpu_lbl.setText(f"{gpu_part} · {inst.gpu_ram_gb:.0f} GB VRAM")

        self.title_lbl.setText(inst.label or f"Instance #{inst.id}")
        self.cost_lbl.setText(f"${inst.dph:.2f}/h")

        sub = []
        if inst.image: sub.append(inst.image)
        if inst.state == InstanceState.RUNNING and inst.duration_seconds:
            sub.append(f"ativa há {_fmt_duration(inst.duration_seconds)}")
        self.subtitle_lbl.setText(" · ".join(sub))

        self.details_lbl.setText(self._format_details(inst))

        is_running = inst.state == InstanceState.RUNNING
        is_connected = is_running and tunnel_status == TunnelStatus.CONNECTED
        self.metrics_container.setVisible(is_connected)
        if not is_connected:
            for b in (self.gpu_bar, self.vram_bar, self.cpu_bar, self.ram_bar, self.disk_bar):
                b.set_value(None)
            self.net_lbl.setText("Rede   ↓ — / ↑ —")
            self._live = {}
        else:
            self._render_metrics_from_instance(inst)

        self.endpoint_wrap.setVisible(is_connected)
        if is_connected:
            self.endpoint_lbl.setText(f"🔗  http://127.0.0.1:{local_port}")

        self.model_badge.setVisible(bool(self._loaded_model) and is_connected)
        if is_running and self._live:
            self._apply_live_overlay()

        self._update_buttons()

    def set_live_metrics(self, d: dict):
        self._live = d or {}
        if self.instance.state == InstanceState.RUNNING:
            self._apply_live_overlay()

    def clear_live_metrics(self):
        self._live = {}

    def set_loaded_model(self, model_id: str | None):
        mid = (model_id or "").strip()
        self._loaded_model = mid or None
        if not mid:
            self.model_badge.setVisible(False); self.model_badge.setText(""); return
        disp = mid if len(mid) <= 60 else "…" + mid[-58:]
        self.model_badge.setText(f"🤖  {disp}")
        self.model_badge.setToolTip(mid)
        if self.endpoint_wrap.isVisible():
            self.model_badge.setVisible(True)

    # ---- internals ----
    def _on_primary(self):
        s = self.instance.state
        if s == InstanceState.STOPPED:
            self.activate_requested.emit(self.instance.id); return
        if s == InstanceState.RUNNING and self.tunnel_status in (
                TunnelStatus.FAILED, TunnelStatus.DISCONNECTED):
            self.reconnect_requested.emit(self.instance.id)

    def _render_metrics_from_instance(self, inst: Instance):
        # Identical logic to [instance_card.py:213-243]
        if inst.gpu_util is not None:
            temp = f"  {inst.gpu_temp:.0f}°C" if inst.gpu_temp is not None else ""
            self.gpu_bar.set_value(inst.gpu_util, f"{inst.gpu_util:.0f}%{temp}")
        if inst.vram_usage_gb is not None and inst.gpu_ram_gb:
            pct = (inst.vram_usage_gb / inst.gpu_ram_gb) * 100.0
            self.vram_bar.set_value(pct, f"{inst.vram_usage_gb:.1f} / {inst.gpu_ram_gb:.1f} GB")
        if inst.cpu_util is not None:
            self.cpu_bar.set_value(inst.cpu_util, f"{inst.cpu_util:.0f}%")
        if inst.ram_total_gb and inst.ram_used_gb is not None:
            pct = (inst.ram_used_gb / inst.ram_total_gb) * 100.0
            self.ram_bar.set_value(pct, f"{pct:.0f}% ({inst.ram_used_gb:.0f} / {inst.ram_total_gb:.0f} GB)")
        if inst.disk_space_gb and inst.disk_usage_gb is not None:
            pct = (inst.disk_usage_gb / inst.disk_space_gb) * 100.0
            self.disk_bar.set_value(pct, f"{inst.disk_usage_gb:.0f} / {inst.disk_space_gb:.0f} GB")
        down = f"{inst.inet_down_mbps:.1f}" if inst.inet_down_mbps is not None else "—"
        up   = f"{inst.inet_up_mbps:.1f}"   if inst.inet_up_mbps is not None else "—"
        self.net_lbl.setText(f"Rede   ↓ {down} Mbps  /  ↑ {up} Mbps")

    def _apply_live_overlay(self):
        # Identical to [instance_card.py:329-351]
        d = self._live
        if "gpu_util" in d:
            t_ = f"  {d['gpu_temp']:.0f}°C" if "gpu_temp" in d else ""
            self.gpu_bar.set_value(d["gpu_util"], f"{d['gpu_util']:.0f}%{t_}")
        if "vram_used_mb" in d and d.get("vram_total_mb", 0) > 0:
            used = d["vram_used_mb"] / 1024.0
            total = d["vram_total_mb"] / 1024.0
            self.vram_bar.set_value(used / total * 100.0, f"{used:.1f} / {total:.1f} GB")
        if "ram_used_mb" in d and d.get("ram_total_mb", 0) > 0:
            used = d["ram_used_mb"] / 1024.0
            total = d["ram_total_mb"] / 1024.0
            self.ram_bar.set_value(used / total * 100.0, f"{used/total*100:.0f}% ({used:.0f} / {total:.0f} GB)")
        if "load1" in d and self.instance.cpu_cores:
            cpu_pct = min(100.0, d["load1"] / max(1, self.instance.cpu_cores) * 100.0)
            self.cpu_bar.set_value(cpu_pct, f"{cpu_pct:.0f}%")
        if "disk_used_gb" in d and d.get("disk_total_gb", 0) > 0:
            pct = d["disk_used_gb"] / d["disk_total_gb"] * 100.0
            self.disk_bar.set_value(pct, f"{d['disk_used_gb']:.0f} / {d['disk_total_gb']:.0f} GB")

    def _update_buttons(self):
        s = self.instance.state
        tun = self.tunnel_status
        # Defaults
        self.primary_btn.setVisible(True); self.primary_btn.setEnabled(True)
        self.lab_btn.setVisible(False); self.terminal_btn.setVisible(False)
        self.disconnect_btn.setVisible(False); self.deactivate_btn.setVisible(False)

        if s == InstanceState.STOPPED:
            self.primary_btn.setText("Ativar")
        elif s == InstanceState.STARTING:
            self.primary_btn.setText("Ativando…"); self.primary_btn.setEnabled(False)
            self.deactivate_btn.setVisible(True)
        elif s == InstanceState.STOPPING:
            self.primary_btn.setText("Desativando…"); self.primary_btn.setEnabled(False)
        elif s == InstanceState.RUNNING:
            self.terminal_btn.setVisible(True); self.deactivate_btn.setVisible(True)
            if tun == TunnelStatus.CONNECTED:
                self.primary_btn.setVisible(False)
                self.lab_btn.setVisible(True)
                self.disconnect_btn.setVisible(True)
            elif tun == TunnelStatus.CONNECTING:
                self.primary_btn.setText("Conectando…"); self.primary_btn.setEnabled(False)
            elif tun == TunnelStatus.FAILED:
                self.primary_btn.setText("Tentar novamente")
            else:
                self.primary_btn.setText("Conectar")
        else:
            self.primary_btn.setVisible(False)

    @staticmethod
    def _format_details(inst: Instance) -> str:
        # Identical to [instance_card.py:293-327]
        bits = []
        if inst.geolocation: bits.append(f"📍 {inst.geolocation}")
        elif inst.country:   bits.append(f"📍 {inst.country}")
        if inst.hostname:    bits.append(f"🖥 {inst.hostname}")
        elif inst.host_id:   bits.append(f"🖥 host #{inst.host_id}")
        if inst.datacenter:  bits.append(f"🏢 {inst.datacenter}")
        if inst.cpu_name:
            cores = f" ({inst.cpu_cores}c)" if inst.cpu_cores else ""
            bits.append(f"🧠 {inst.cpu_name}{cores}")
        if inst.cuda_max_good:   bits.append(f"CUDA ≤ {inst.cuda_max_good:g}")
        if inst.pcie_gen:
            pcie = f"PCIe Gen {inst.pcie_gen:g}"
            if inst.pcie_bw_gbps: pcie += f" · {inst.pcie_bw_gbps:.1f} GB/s"
            bits.append(pcie)
        if inst.disk_bw_mbps: bits.append(f"Disco {inst.disk_bw_mbps:.0f} MB/s")
        if inst.dlperf:       bits.append(f"DLPerf {inst.dlperf:.1f}")
        if inst.reliability is not None:
            r = inst.reliability * 100 if inst.reliability <= 1.0 else inst.reliability
            bits.append(f"⚡ {r:.1f}%")
        return "  ·  ".join(bits)
