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
        self.server_tile = MetricTile("Files", "\u2014")
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
        
        self.discover_btn = QPushButton("\u2726 Discover Models")
        self.discover_btn.clicked.connect(lambda: self.navigate_requested.emit(self.iid, "discover"))

        self.models_btn = QPushButton("\u2630 Installed Models")
        self.models_btn.clicked.connect(lambda: self.navigate_requested.emit(self.iid, "models"))
        
        self.monitor_btn = QPushButton("\u25F4 Monitor")
        self.monitor_btn.setProperty("variant", "ghost")
        self.monitor_btn.clicked.connect(lambda: self.navigate_requested.emit(self.iid, "monitor"))

        action_bar.addWidget(self.setup_btn)
        action_bar.addWidget(self.discover_btn)
        action_bar.addWidget(self.models_btn)
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

    def update_state(self, st: LabInstanceState, ssh_status: str, fallback_gpu: str = ""):
        # Header updates
        sys = st.system
        # Keep global naming consistent: Prioritize Vast.ai name for title, hardware details below.
        gpu = fallback_gpu or sys.gpu_name or "Remote Instance"
        self.gpu_lbl.setText(gpu)
        
        # SSH Status
        # Connection Status & Health Dot
        is_connecting = ssh_status == "connecting"
        is_connected = ssh_status == "connected"
        is_failed = ssh_status == "failed"
        
        pill_text = f"SSH {ssh_status.title()}"
        if ssh_status == "disconnected":
            pill_text = "SSH Offline"
        
        pill_level = "live" if is_connected else ("info" if is_connecting else "err")
        self.ssh_pill.set_status(pill_text, pill_level)

        if is_connected:
            dot_level = "live" if st.setup.probed else "info"
        elif is_connecting:
            dot_level = "info" # Blue for waiting
        else:
            # Stopped or failed
            dot_level = "err" if is_failed else "warn"
        self.health_dot.set_level(dot_level)

        # --- State Logic ---
        is_probing = "probe" in st.busy_keys
        is_setting_up = "setup" in st.busy_keys
        is_updating = "update_check" in st.busy_keys
        # Unified "Syncing" state: Haven't probed yet, or currently probing.
        is_syncing = (not st.setup.probed or is_probing) and is_connected
        is_busy = is_probing or is_setting_up or is_updating
        
        # Metrics Mapping
        s = st.setup
        if is_syncing:
            val_llmfit = "SYNCING..."
            val_llama = "SYNCING..."
            val_files = "SYNCING..."
            level_llmfit = "info"
            level_llama = "info"
        else:
            val_llmfit = "READY" if s.llmfit_serving else ("INSTALLED" if s.llmfit_installed else "MISSING")
            val_llama = "READY" if s.llamacpp_installed else "MISSING"
            val_files = str(s.model_count)
            level_llmfit = "live" if s.llmfit_serving else ("info" if s.llmfit_installed else "warn")
            level_llama = "live" if s.llamacpp_installed else "warn"

        self.llmfit_tile.set_value(val_llmfit, "model advisor")
        # Reuse tile level if I had a set_level, but MetricTile is simple. 
        # For now I'll just change the text.
        self.llama_tile.set_value(val_llama, "inference engine")
        self.server_tile.set_value(val_files, "GGUF files found")

        # HW Specs
        parts = []
        if sys.cpu_name:
            parts.append(f"CPU: {sys.cpu_name} ({sys.cpu_cores} cores)")
        if sys.ram_total_gb:
            parts.append(f"RAM: {sys.ram_total_gb:.0f}GB")
        
        # If we have VRAM info, show it
        if sys.gpu_vram_gb:
            parts.append(f"VRAM: {sys.gpu_vram_gb:.0f}GB")
        
        if not parts:
            if ssh_status == "connected":
                self.hw_lbl.setText("Probing remote hardware details...")
            else:
                self.hw_lbl.setText("Connect SSH to see full hardware specs.")
        else:
            self.hw_lbl.setText("  \u2022  ".join(parts))
        
        # Connection Guard: Only allow expansion if connected
        is_connected = ssh_status == "connected"
        self.expand_btn.setEnabled(is_connected)
        if not is_connected and self._expanded:
            self.toggle_expanded() # Close if connection drops
        
        # Busy & Ready states
        is_installed = st.setup.llmfit_installed and st.setup.llamacpp_installed
        
        # Setup Button Logic
        if is_updating:
            self.setup_btn.setText("\u21BB CHECKING UPDATES...")
            self.setup_btn.setEnabled(False)
        elif is_syncing:
            self.setup_btn.setText("\u21BB SYNCING...")
            self.setup_btn.setEnabled(False)
        elif is_setting_up:
            self.setup_btn.setText("\u26A1 SETTING UP...")
            self.setup_btn.setEnabled(False)
        elif is_installed:
            self.setup_btn.setText("\u21BB Check for updates")
            self.setup_btn.setEnabled(not is_busy)
        else:
            self.setup_btn.setText("\u26A1 Setup Everything")
            self.setup_btn.setEnabled(not is_busy)

        # Features Guard: Strictly need installation confirmed and not syncing
        can_use_features = is_installed and not is_busy and not is_syncing
        self.discover_btn.setEnabled(can_use_features)
        self.models_btn.setEnabled(can_use_features)
        self.monitor_btn.setEnabled(can_use_features)

        if is_updating:
            self.gpu_lbl.setText(f"{gpu} (Checking updates...)")
        elif is_syncing:
            self.gpu_lbl.setText(f"{gpu} (Syncing...)")
        elif is_setting_up:
            self.gpu_lbl.setText(f"{gpu} (Updating...)")
