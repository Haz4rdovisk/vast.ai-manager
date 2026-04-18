"""Instance card — premium glassmorphism design with visual zones.
Preserves every signal/state so AppController wiring is unchanged."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QSizePolicy, QWidget,
)
from app import theme as t
from app.models import Instance, InstanceState, TunnelStatus
from app.ui.components.primitives import GlassCard, StatusPill, Badge, Divider


STATE_LABELS = {
    InstanceState.STOPPED:  ("\u25CB Stopped",       "muted"),
    InstanceState.STARTING: ("\u25CC Starting\u2026", "warn"),
    InstanceState.RUNNING:  ("\u25CF Active",         "ok"),
    InstanceState.STOPPING: ("\u25CC Stopping\u2026", "warn"),
    InstanceState.UNKNOWN:  ("? Unknown",             "muted"),
}

TUNNEL_LABELS = {
    TunnelStatus.DISCONNECTED: ("Disconnected", "info"),
    TunnelStatus.CONNECTING:   ("Connecting\u2026",  "warn"),
    TunnelStatus.CONNECTED:    ("Connected",    "live"),
    TunnelStatus.FAILED:       ("Failed",       "err"),
}


def _fmt_duration(seconds: int | None) -> str:
    if not seconds or seconds < 0:
        return "\u2014"
    h, r = divmod(seconds, 3600)
    m, _ = divmod(r, 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ── Metric bar ──────────────────────────────────────────────────────────────
class _Bar(QWidget):
    """Inline labeled progress bar with 8px height."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self.k = QLabel(label)
        self.k.setFixedWidth(56)
        self.k.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 10px;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.v = QLabel("\u2014")
        self.v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.v.setMinimumWidth(140)
        self.v.setStyleSheet(
            f"color: {t.TEXT}; font-family: {t.FONT_MONO};"
            f" font-size: {t.FONT_SIZE_MONO}px;"
        )
        h.addWidget(self.k)
        h.addWidget(self.bar, 1)
        h.addWidget(self.v)
        self._color(t.TEXT_MID)

    def set_value(self, percent: float | None, text: str | None = None):
        if percent is None:
            self.bar.setValue(0)
            self.v.setText("\u2014")
            self._color(t.TEXT_MID)
            return
        p = max(0.0, min(100.0, percent))
        self.bar.setValue(int(p))
        self.v.setText(text if text is not None else f"{p:.0f}%")
        self._color(t.metric_color(p))

    def _color(self, color: str):
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {t.SURFACE_3}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
class InstanceCard(GlassCard):
    activate_requested      = Signal(int)
    deactivate_requested    = Signal(int)
    reconnect_requested     = Signal(int)
    disconnect_requested    = Signal(int)
    open_terminal_requested = Signal(int)
    open_lab_requested      = Signal(int)
    copy_endpoint_requested = Signal(int)

    def __init__(self, instance: Instance, parent=None):
        super().__init__(parent=parent)
        self.instance = instance
        self.tunnel_status = TunnelStatus.DISCONNECTED
        self.local_port = 11434
        self._live: dict = {}
        self._loaded_model: str | None = None

        # ── ZONE A: Header ─────────────────────────────────────────────
        zone_a = QHBoxLayout()
        zone_a.setSpacing(t.SPACE_3)
        self.state_pill = StatusPill("\u2014", "muted")
        zone_a.addWidget(self.state_pill)
        zone_a.addStretch()

        self.gpu_lbl = Badge("", mono=True)
        zone_a.addWidget(self.gpu_lbl)

        self.cost_lbl = QLabel("")
        self.cost_lbl.setStyleSheet(
            f"color: {t.ACCENT}; font-size: 12pt; font-weight: 700;"
            f" font-family: {t.FONT_MONO};"
        )
        zone_a.addWidget(self.cost_lbl)
        self._lay.addLayout(zone_a)

        # ── ZONE B: Identity ───────────────────────────────────────────
        self.title_lbl = QLabel("")
        self.title_lbl.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 15pt; font-weight: 700;"
        )
        self._lay.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel("")
        self.subtitle_lbl.setProperty("role", "muted")
        self.subtitle_lbl.setWordWrap(True)
        self._lay.addWidget(self.subtitle_lbl)

        self.details_lbl = QLabel("")
        self.details_lbl.setWordWrap(True)
        self.details_lbl.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: {t.FONT_SIZE_LABEL}px;"
        )
        self._lay.addWidget(self.details_lbl)

        self._lay.addWidget(Divider())

        # ── ZONE C: Live Data (visible only when CONNECTED) ────────────
        self.metrics_container = QWidget()
        mc = QVBoxLayout(self.metrics_container)
        mc.setContentsMargins(0, t.SPACE_2, 0, t.SPACE_2)
        mc.setSpacing(t.SPACE_2)

        self.gpu_bar  = _Bar("GPU")
        self.vram_bar = _Bar("vRAM")
        self.cpu_bar  = _Bar("CPU")
        self.ram_bar  = _Bar("RAM")
        self.disk_bar = _Bar("Disk")
        self.net_lbl  = QLabel("Net   \u2193 \u2014 / \u2191 \u2014")
        self.net_lbl.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: 10px;"
            f" font-family: {t.FONT_MONO};"
        )
        for b in (self.gpu_bar, self.vram_bar, self.cpu_bar,
                  self.ram_bar, self.disk_bar):
            mc.addWidget(b)
        mc.addWidget(self.net_lbl)
        self._lay.addWidget(self.metrics_container)

        # Endpoint row
        self.endpoint_wrap = QWidget()
        er = QHBoxLayout(self.endpoint_wrap)
        er.setContentsMargins(0, 0, 0, 0)
        self.endpoint_lbl = QLabel("")
        self.endpoint_lbl.setProperty("role", "mono")
        self.endpoint_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setProperty("variant", "ghost")
        self.copy_btn.setFixedWidth(80)
        self.copy_btn.clicked.connect(
            lambda: self.copy_endpoint_requested.emit(self.instance.id)
        )
        er.addWidget(self.endpoint_lbl)
        er.addStretch()
        er.addWidget(self.copy_btn)
        self._lay.addWidget(self.endpoint_wrap)

        # Model badge
        self.model_badge = Badge("", mono=True)
        self.model_badge.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.model_badge.setVisible(False)
        self._lay.addWidget(self.model_badge)

        self._lay.addWidget(Divider())

        # ── Actions row ────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_2)
        self.primary_btn = QPushButton("")
        self.primary_btn.setMinimumHeight(38)
        self.primary_btn.clicked.connect(self._on_primary)

        self.lab_btn = QPushButton("Open Lab")
        self.lab_btn.setProperty("variant", "ghost")
        self.lab_btn.setMinimumHeight(38)
        self.lab_btn.clicked.connect(
            lambda: self.open_lab_requested.emit(self.instance.id)
        )

        self.terminal_btn = QPushButton("Terminal")
        self.terminal_btn.setProperty("variant", "ghost")
        self.terminal_btn.setMinimumHeight(38)
        self.terminal_btn.clicked.connect(
            lambda: self.open_terminal_requested.emit(self.instance.id)
        )

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setProperty("variant", "ghost")
        self.disconnect_btn.setMinimumHeight(38)
        self.disconnect_btn.clicked.connect(
            lambda: self.disconnect_requested.emit(self.instance.id)
        )

        self.deactivate_btn = QPushButton("Deactivate")
        self.deactivate_btn.setProperty("variant", "danger")
        self.deactivate_btn.setMinimumHeight(38)
        self.deactivate_btn.clicked.connect(
            lambda: self.deactivate_requested.emit(self.instance.id)
        )

        for b in (self.primary_btn, self.lab_btn, self.terminal_btn,
                  self.disconnect_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(self.deactivate_btn)
        self._lay.addLayout(actions)

        self.update_from(instance, self.tunnel_status, self.local_port)

    # ── Public API used by the Instances view ──────────────────────────
    def update_from(self, inst: Instance, tunnel_status: TunnelStatus,
                    local_port: int):
        self.instance = inst
        self.tunnel_status = tunnel_status
        self.local_port = local_port

        label, level = STATE_LABELS.get(
            inst.state, STATE_LABELS[InstanceState.UNKNOWN]
        )
        if inst.state == InstanceState.RUNNING:
            t_label, t_level = TUNNEL_LABELS[tunnel_status]
            self.state_pill.set_status(f"{label}  \u00b7  {t_label}", t_level)
        else:
            self.state_pill.set_status(label, level)

        gpu_part = (
            f"{inst.num_gpus}\u00d7 {inst.gpu_name}"
            if inst.num_gpus > 1 else (inst.gpu_name or "GPU")
        )
        self.gpu_lbl.setText(f"{gpu_part} \u00b7 {inst.gpu_ram_gb:.0f} GB")

        label_str = getattr(inst, "label", None)
        self.title_lbl.setText(label_str or f"Instance #{inst.id}")
        self.cost_lbl.setText(f"${inst.dph:.2f}/h")

        sub = []
        if inst.image:
            sub.append(inst.image)
        if inst.state == InstanceState.RUNNING and inst.duration_seconds:
            sub.append(f"active for {_fmt_duration(inst.duration_seconds)}")
        self.subtitle_lbl.setText(" \u00b7 ".join(sub))
        self.details_lbl.setText(self._format_details(inst))

        is_running = inst.state == InstanceState.RUNNING
        is_connected = is_running and tunnel_status == TunnelStatus.CONNECTED
        self.metrics_container.setVisible(is_connected)
        if not is_connected:
            for b in (self.gpu_bar, self.vram_bar, self.cpu_bar,
                      self.ram_bar, self.disk_bar):
                b.set_value(None)
            self.net_lbl.setText("Net   \u2193 \u2014 / \u2191 \u2014")
            self._live = {}
        else:
            self._render_metrics_from_instance(inst)

        self.endpoint_wrap.setVisible(is_connected)
        if is_connected:
            self.endpoint_lbl.setText(
                f"\U0001F517  http://127.0.0.1:{local_port}"
            )

        self.model_badge.setVisible(
            bool(self._loaded_model) and is_connected
        )
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
            self.model_badge.setVisible(False)
            self.model_badge.setText("")
            return
        disp = mid if len(mid) <= 60 else "\u2026" + mid[-58:]
        self.model_badge.setText(f"\U0001F916  {disp}")
        self.model_badge.setToolTip(mid)
        if self.endpoint_wrap.isVisible():
            self.model_badge.setVisible(True)

    # ── internals ──────────────────────────────────────────────────────
    def _on_primary(self):
        s = self.instance.state
        if s == InstanceState.STOPPED:
            self.activate_requested.emit(self.instance.id)
            return
        if s == InstanceState.RUNNING and self.tunnel_status in (
                TunnelStatus.FAILED, TunnelStatus.DISCONNECTED):
            self.reconnect_requested.emit(self.instance.id)

    def _render_metrics_from_instance(self, inst: Instance):
        if inst.gpu_util is not None:
            temp = f"  {inst.gpu_temp:.0f}\u00b0C" if inst.gpu_temp is not None else ""
            self.gpu_bar.set_value(inst.gpu_util, f"{inst.gpu_util:.0f}%{temp}")
        if inst.vram_usage_gb is not None and inst.gpu_ram_gb:
            pct = (inst.vram_usage_gb / inst.gpu_ram_gb) * 100.0
            self.vram_bar.set_value(
                pct, f"{inst.vram_usage_gb:.1f} / {inst.gpu_ram_gb:.1f} GB"
            )
        if inst.cpu_util is not None:
            self.cpu_bar.set_value(inst.cpu_util, f"{inst.cpu_util:.0f}%")
        if inst.ram_total_gb and inst.ram_used_gb is not None:
            pct = (inst.ram_used_gb / inst.ram_total_gb) * 100.0
            self.ram_bar.set_value(
                pct,
                f"{pct:.0f}% ({inst.ram_used_gb:.0f} / {inst.ram_total_gb:.0f} GB)"
            )
        if inst.disk_space_gb and inst.disk_usage_gb is not None:
            pct = (inst.disk_usage_gb / inst.disk_space_gb) * 100.0
            self.disk_bar.set_value(
                pct,
                f"{inst.disk_usage_gb:.0f} / {inst.disk_space_gb:.0f} GB"
            )
        down = f"{inst.inet_down_mbps:.1f}" if inst.inet_down_mbps is not None else "\u2014"
        up = f"{inst.inet_up_mbps:.1f}" if inst.inet_up_mbps is not None else "\u2014"
        self.net_lbl.setText(f"Net   \u2193 {down} Mbps  /  \u2191 {up} Mbps")

    def _apply_live_overlay(self):
        d = self._live
        if "gpu_util" in d:
            t_ = f"  {d['gpu_temp']:.0f}\u00b0C" if "gpu_temp" in d else ""
            self.gpu_bar.set_value(d["gpu_util"], f"{d['gpu_util']:.0f}%{t_}")
        if "vram_used_mb" in d and d.get("vram_total_mb", 0) > 0:
            used = d["vram_used_mb"] / 1024.0
            total = d["vram_total_mb"] / 1024.0
            self.vram_bar.set_value(
                used / total * 100.0, f"{used:.1f} / {total:.1f} GB"
            )
        if "ram_used_mb" in d and d.get("ram_total_mb", 0) > 0:
            used = d["ram_used_mb"] / 1024.0
            total = d["ram_total_mb"] / 1024.0
            self.ram_bar.set_value(
                used / total * 100.0,
                f"{used/total*100:.0f}% ({used:.0f} / {total:.0f} GB)"
            )
        if "load1" in d and self.instance.cpu_cores:
            cpu_pct = min(
                100.0, d["load1"] / max(1, self.instance.cpu_cores) * 100.0
            )
            self.cpu_bar.set_value(cpu_pct, f"{cpu_pct:.0f}%")
        if "disk_used_gb" in d and d.get("disk_total_gb", 0) > 0:
            pct = d["disk_used_gb"] / d["disk_total_gb"] * 100.0
            self.disk_bar.set_value(
                pct,
                f"{d['disk_used_gb']:.0f} / {d['disk_total_gb']:.0f} GB"
            )

    def _update_buttons(self):
        s = self.instance.state
        tun = self.tunnel_status
        self.primary_btn.setVisible(True)
        self.primary_btn.setEnabled(True)
        self.lab_btn.setVisible(False)
        self.terminal_btn.setVisible(False)
        self.disconnect_btn.setVisible(False)
        self.deactivate_btn.setVisible(False)

        if s == InstanceState.STOPPED:
            self.primary_btn.setText("\u25B6  Activate")
        elif s == InstanceState.STARTING:
            self.primary_btn.setText("Starting\u2026")
            self.primary_btn.setEnabled(False)
            self.deactivate_btn.setVisible(True)
        elif s == InstanceState.STOPPING:
            self.primary_btn.setText("Stopping\u2026")
            self.primary_btn.setEnabled(False)
        elif s == InstanceState.RUNNING:
            self.terminal_btn.setVisible(True)
            self.deactivate_btn.setVisible(True)
            if tun == TunnelStatus.CONNECTED:
                self.primary_btn.setVisible(False)
                self.lab_btn.setVisible(True)
                self.disconnect_btn.setVisible(True)
            elif tun == TunnelStatus.CONNECTING:
                self.primary_btn.setText("Connecting\u2026")
                self.primary_btn.setEnabled(False)
            elif tun == TunnelStatus.FAILED:
                self.primary_btn.setText("\u21BB  Retry")
            else:
                self.primary_btn.setText("\u2192  Connect")
        else:
            self.primary_btn.setVisible(False)

    @staticmethod
    def _format_details(inst: Instance) -> str:
        bits = []
        if inst.geolocation:
            bits.append(f"\U0001F4CD {inst.geolocation}")
        elif inst.country:
            bits.append(f"\U0001F4CD {inst.country}")
        if inst.hostname:
            bits.append(f"\U0001F5A5 {inst.hostname}")
        elif inst.host_id:
            bits.append(f"\U0001F5A5 host #{inst.host_id}")
        if inst.datacenter:
            bits.append(f"\U0001F3E2 {inst.datacenter}")
        if inst.cpu_name:
            cores = f" ({inst.cpu_cores}c)" if inst.cpu_cores else ""
            bits.append(f"\U0001F9E0 {inst.cpu_name}{cores}")
        if inst.cuda_max_good:
            bits.append(f"CUDA \u2264 {inst.cuda_max_good:g}")
        if inst.pcie_gen:
            pcie = f"PCIe Gen {inst.pcie_gen:g}"
            if inst.pcie_bw_gbps:
                pcie += f" \u00b7 {inst.pcie_bw_gbps:.1f} GB/s"
            bits.append(pcie)
        if inst.disk_bw_mbps:
            bits.append(f"Disk {inst.disk_bw_mbps:.0f} MB/s")
        if inst.dlperf:
            bits.append(f"DLPerf {inst.dlperf:.1f}")
        if inst.reliability is not None:
            r = (inst.reliability * 100
                 if inst.reliability <= 1.0 else inst.reliability)
            bits.append(f"\u26A1 {r:.1f}%")
        return "  \u00b7  ".join(bits)
