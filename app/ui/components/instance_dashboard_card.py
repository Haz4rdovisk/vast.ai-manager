from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, MetricTile, StatusPill, HealthDot
from app.lab.state.models import LabInstanceState
from app.models import TunnelStatus


class InstanceDashboardCard(GlassCard):
    """A professional, expandable card for a single instance in the Dashboard."""
    select_requested = Signal(int)
    probe_requested = Signal(int)
    setup_all_requested = Signal(int)
    navigate_requested = Signal(int, str)  # iid, view_key

    def __init__(self, iid: int, parent=None):
        super().__init__(raised=True, parent=parent)
        self.iid = iid
        self._expanded = False
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        # 1. Header (Always visible)
        self.header = QWidget()
        self.header_lay = QHBoxLayout(self.header)
        self.header_lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        self.header_lay.setSpacing(t.SPACE_4)
        
        # Left: ID and Health
        self.health_dot = HealthDot("unknown")
        self.header_lay.addWidget(self.health_dot)
        
        self.title_group = QVBoxLayout()
        self.title_group.setSpacing(2)
        self.gpu_lbl = QLabel("Probing GPU...")
        self.gpu_lbl.setProperty("role", "title")
        self.id_lbl = QLabel(f"Instance #{iid}")
        self.id_lbl.setProperty("role", "muted")
        self.title_group.addWidget(self.gpu_lbl)
        self.title_group.addWidget(self.id_lbl)
        self.header_lay.addLayout(self.title_group)
        
        self.header_lay.addStretch()

        # Center: SSH Status Pill
        self.ssh_pill = StatusPill("SSH Disconnected", "unknown")
        self.header_lay.addWidget(self.ssh_pill)

        # Right: Expand button
        self.expand_btn = QPushButton("Details \u25BE")
        self.expand_btn.setProperty("variant", "ghost")
        self.expand_btn.setFixedWidth(100)
        self.expand_btn.clicked.connect(self.toggle_expanded)
        self.header_lay.addWidget(self.expand_btn)

        self._lay.addWidget(self.header)

        # 2. Body (Expandable)
        self.body_container = QWidget()
        self.body_lay = QVBoxLayout(self.body_container)
        self.body_lay.setContentsMargins(t.SPACE_4, 0, t.SPACE_4, t.SPACE_4)
        self.body_lay.setSpacing(t.SPACE_4)
        self.body_container.setVisible(False)

        # Divide body into sections
        # - Metrics Strip
        self.metrics_lay = QHBoxLayout()
        self.llmfit_tile = MetricTile("LLMfit", "\u2014")
        self.llama_tile = MetricTile("llama.cpp", "\u2014")
        self.server_tile = MetricTile("Server", "\u2014")
        self.metrics_lay.addWidget(self.llmfit_tile)
        self.metrics_lay.addWidget(self.llama_tile)
        self.metrics_lay.addWidget(self.server_tile)
        self.body_lay.addLayout(self.metrics_lay)

        # - HW Specs Card
        self.hw_box = QFrame()
        self.hw_box.setStyleSheet(f"background: {t.SURFACE_3}; border-radius: {t.RADIUS_MD}px; padding: 12px;")
        hw_inner = QVBoxLayout(self.hw_box)
        self.hw_lbl = QLabel("Probe instance to see hardware details.")
        self.hw_lbl.setProperty("role", "muted")
        self.hw_lbl.setWordWrap(True)
        hw_inner.addWidget(self.hw_lbl)
        self.body_lay.addWidget(self.hw_box)

        # - Action Bar
        action_bar = QHBoxLayout()
        self.setup_btn = QPushButton("\u26A1 Setup Everything")
        self.setup_btn.clicked.connect(lambda: self.setup_all_requested.emit(self.iid))
        
        self.focus_btn = QPushButton("\u25C9 Focus in Lab")
        self.focus_btn.clicked.connect(lambda: self.select_requested.emit(self.iid))
        
        self.monitor_btn = QPushButton("\u25F4 Monitor")
        self.monitor_btn.setProperty("variant", "ghost")
        self.monitor_btn.clicked.connect(lambda: self.navigate_requested.emit(self.iid, "monitor"))

        action_bar.addWidget(self.setup_btn)
        action_bar.addWidget(self.focus_btn)
        action_bar.addWidget(self.monitor_btn)
        action_bar.addStretch()
        self.body_lay.addLayout(action_bar)

        self._lay.addWidget(self.body_container)

    def toggle_expanded(self):
        self._expanded = not self._expanded
        self.body_container.setVisible(self._expanded)
        self.expand_btn.setText("Hide \u25B4" if self._expanded else "Details \u25BE")
        if self._expanded:
            self.select_requested.emit(self.iid)

    def update_state(self, st: LabInstanceState, ssh_status: str, gpu_name_hint: str = ""):
        # Header updates
        sys = st.system
        gpu = sys.gpu_name or gpu_name_hint or "Unknown GPU"
        self.gpu_lbl.setText(gpu)
        
        # SSH Status
        level = "live" if ssh_status == "connected" else ("warn" if ssh_status == "connecting" else "err")
        self.ssh_pill.set_status(f"SSH {ssh_status.title()}", level)
        self.health_dot.set_level("live" if st.setup.probed and ssh_status == "connected" else "unknown")

        # Metrics
        s = st.setup
        self.llmfit_tile.set_value(
            "READY" if s.llmfit_serving else ("INSTALLED" if s.llmfit_installed else "MISSING"),
            "model advisor"
        )
        self.llama_tile.set_value(
            "READY" if s.llamacpp_installed else "MISSING",
            "inference engine"
        )
        self.server_tile.set_value(
            "RUNNING" if s.llama_server_running else "STOPPED",
            s.llama_server_model[:20] + "..." if len(s.llama_server_model) > 20 else (s.llama_server_model or "no model")
        )

        # HW Specs
        parts = []
        if sys.cpu_name:
            parts.append(f"CPU: {sys.cpu_name} ({sys.cpu_cores} cores)")
        if sys.ram_total_gb:
            parts.append(f"RAM: {sys.ram_total_gb:.0f}GB total")
        if sys.gpu_name:
            vram = f"{sys.gpu_vram_gb:.0f}GB" if sys.gpu_vram_gb else "?"
            parts.append(f"GPU: {sys.gpu_name} ({vram} VRAM) x{sys.gpu_count}")
        
        self.hw_lbl.setText("  \u2022  ".join(parts) if parts else "Pending probe for hardware details...")
        
        # Busy states
        is_busy = bool(st.busy_keys)
        self.setup_btn.setEnabled(not is_busy)
        if is_busy:
            self.gpu_lbl.setText(f"{gpu} (Working...)")
