"""Instance Dashboard Card — expandable card for the AI Lab dashboard.
Glassmorphism redesign with animated expand/collapse."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from app import theme as t
from app.ui.components.primitives import GlassCard, MetricTile, StatusPill, HealthDot
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

        # ── 1. Header (Always visible) ─────────────────────────────────
        self.header = QWidget()
        self.header_lay = QHBoxLayout(self.header)
        self.header_lay.setContentsMargins(
            t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4
        )
        self.header_lay.setSpacing(t.SPACE_4)

        # Health dot
        self.health_dot = HealthDot("unknown")
        self.header_lay.addWidget(self.health_dot)

        # Title group
        self.title_group = QVBoxLayout()
        self.title_group.setSpacing(2)
        self.gpu_lbl = QLabel("Probing GPU...")
        self.gpu_lbl.setProperty("role", "title")
        self.id_lbl = QLabel(f"Instance #{iid}")
        self.id_lbl.setProperty("role", "muted")
        self.id_lbl.setStyleSheet(f"font-size: {t.FONT_SIZE_SMALL}px;")
        self.title_group.addWidget(self.gpu_lbl)
        self.title_group.addWidget(self.id_lbl)
        self.header_lay.addLayout(self.title_group)

        self.header_lay.addStretch()

        # SSH pill
        self.ssh_pill = StatusPill("SSH Offline", "unknown")
        self.header_lay.addWidget(self.ssh_pill)

        # Expand button
        self.expand_btn = QPushButton("Details \u25BE")
        self.expand_btn.setProperty("variant", "ghost")
        self.expand_btn.setFixedWidth(100)
        self.expand_btn.clicked.connect(self.toggle_expanded)
        self.header_lay.addWidget(self.expand_btn)

        self._lay.addWidget(self.header)

        # ── 2. Body (Expandable) ───────────────────────────────────────
        self.body_container = QWidget()
        self.body_lay = QVBoxLayout(self.body_container)
        self.body_lay.setContentsMargins(
            t.SPACE_4, 0, t.SPACE_4, t.SPACE_4
        )
        self.body_lay.setSpacing(t.SPACE_4)
        self.body_container.setMaximumHeight(0)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BORDER_LOW};")
        self.body_lay.addWidget(sep)

        # Metrics Strip
        self.metrics_lay = QHBoxLayout()
        self.metrics_lay.setSpacing(t.SPACE_3)
        self.llmfit_tile = MetricTile("LLMfit", "\u2014")
        self.llama_tile = MetricTile("llama.cpp", "\u2014")
        self.server_tile = MetricTile("Files", "\u2014")
        self.metrics_lay.addWidget(self.llmfit_tile)
        self.metrics_lay.addWidget(self.llama_tile)
        self.metrics_lay.addWidget(self.server_tile)
        self.body_lay.addLayout(self.metrics_lay)

        # HW Specs
        self.hw_box = QFrame()
        self.hw_box.setStyleSheet(
            f"background: {t.SURFACE_3}; border-radius: {t.RADIUS_MD}px;"
            f" padding: 14px;"
        )
        hw_inner = QVBoxLayout(self.hw_box)
        hw_inner.setContentsMargins(0, 0, 0, 0)
        self.hw_lbl = QLabel("Probe instance to see hardware details.")
        self.hw_lbl.setProperty("role", "muted")
        self.hw_lbl.setWordWrap(True)
        hw_inner.addWidget(self.hw_lbl)
        self.body_lay.addWidget(self.hw_box)

        # Action Bar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(t.SPACE_2)
        self.setup_btn = QPushButton("\u26A1 Setup Everything")
        self.setup_btn.clicked.connect(
            lambda: self.setup_all_requested.emit(self.iid)
        )

        self.discover_btn = QPushButton("\u2726 Discover Models")
        self.discover_btn.setProperty("variant", "ghost")
        self.discover_btn.clicked.connect(
            lambda: self.navigate_requested.emit(self.iid, "discover")
        )

        self.models_btn = QPushButton("\u2630 Installed Models")
        self.models_btn.setProperty("variant", "ghost")
        self.models_btn.clicked.connect(
            lambda: self.navigate_requested.emit(self.iid, "models")
        )

        self.studio_btn = QPushButton("\u25D4 Studio")
        self.studio_btn.setProperty("variant", "ghost")
        self.studio_btn.clicked.connect(
            lambda: self.navigate_requested.emit(self.iid, "studio")
        )

        action_bar.addWidget(self.setup_btn)
        action_bar.addWidget(self.discover_btn)
        action_bar.addWidget(self.models_btn)
        action_bar.addWidget(self.studio_btn)
        action_bar.addStretch()
        self.body_lay.addLayout(action_bar)

        self._lay.addWidget(self.body_container)

    # ── Expand / Collapse with animation ───────────────────────────────
    def toggle_expanded(self):
        self._expanded = not self._expanded
        self.expand_btn.setText(
            "Hide \u25B4" if self._expanded else "Details \u25BE"
        )

        if self._expanded:
            self.select_requested.emit(self.iid)
            # Measure natural height
            self.body_container.setMaximumHeight(16777215)
            self.body_container.adjustSize()
            target_h = self.body_container.sizeHint().height()
            self.body_container.setMaximumHeight(0)
        else:
            target_h = 0

        anim = QPropertyAnimation(self.body_container, b"maximumHeight")
        anim.setDuration(t.ANIM_SLOW)
        anim.setStartValue(self.body_container.maximumHeight())
        anim.setEndValue(target_h)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if not self._expanded:
            anim.finished.connect(
                lambda: self.body_container.setMaximumHeight(0)
            )
        anim.start()
        self._expand_anim = anim  # prevent GC

    # ── State update ───────────────────────────────────────────────────
    def update_state(self, st: LabInstanceState, ssh_status: str,
                     fallback_gpu: str = ""):
        sys = st.system
        gpu = fallback_gpu or sys.gpu_name or "Remote Instance"
        self.gpu_lbl.setText(gpu)

        # SSH Status
        is_connecting = ssh_status == "connecting"
        is_connected = ssh_status == "connected"
        is_failed = ssh_status == "failed"

        pill_text = f"SSH {ssh_status.title()}"
        if ssh_status == "disconnected":
            pill_text = "SSH Offline"

        pill_level = (
            "live" if is_connected
            else ("info" if is_connecting else "err")
        )
        self.ssh_pill.set_status(pill_text, pill_level)

        if is_connected:
            dot_level = "live" if st.setup.probed else "info"
        elif is_connecting:
            dot_level = "info"
        else:
            dot_level = "err" if is_failed else "warn"
        self.health_dot.set_level(dot_level)

        # State logic
        is_probing = "probe" in st.busy_keys
        is_setting_up = "setup" in st.busy_keys
        is_updating = "update_check" in st.busy_keys
        is_syncing = (not st.setup.probed or is_probing) and is_connected
        is_busy = is_probing or is_setting_up or is_updating

        # Metrics
        s = st.setup
        if is_syncing:
            self.llmfit_tile.set_value("SYNCING...")
            self.llama_tile.set_value("SYNCING...")
            self.server_tile.set_value("SYNCING...")
        else:
            val_llmfit = (
                "READY" if s.llmfit_serving
                else ("INSTALLED" if s.llmfit_installed else "MISSING")
            )
            val_llama = "READY" if s.llamacpp_installed else "MISSING"
            val_files = str(s.model_count)

            self.llmfit_tile.set_value(val_llmfit, "model advisor")
            if s.llmfit_serving:
                self.llmfit_tile.set_color(t.LIVE)
            elif s.llmfit_installed:
                self.llmfit_tile.set_color(t.INFO)
            else:
                self.llmfit_tile.set_color(t.WARN)

            self.llama_tile.set_value(val_llama, "inference engine")
            self.llama_tile.set_color(
                t.LIVE if s.llamacpp_installed else t.WARN
            )

            self.server_tile.set_value(val_files, "GGUF files found")

        # HW Specs
        parts = []
        if sys.cpu_name:
            parts.append(f"CPU: {sys.cpu_name} ({sys.cpu_cores} cores)")
        if sys.ram_total_gb:
            parts.append(f"RAM: {sys.ram_total_gb:.0f}GB")
        if sys.gpu_vram_gb:
            parts.append(f"VRAM: {sys.gpu_vram_gb:.0f}GB")

        if not parts:
            if ssh_status == "connected":
                self.hw_lbl.setText("Probing remote hardware details...")
            else:
                self.hw_lbl.setText("Connect SSH to see hardware specs.")
        else:
            self.hw_lbl.setText("  \u2022  ".join(parts))

        # Connection guard
        self.expand_btn.setEnabled(is_connected)
        if not is_connected and self._expanded:
            self.toggle_expanded()

        # Button states
        is_installed = st.setup.llmfit_installed and st.setup.llamacpp_installed

        if is_updating:
            self.setup_btn.setText("\u21BB CHECKING...")
            self.setup_btn.setEnabled(False)
        elif is_syncing:
            self.setup_btn.setText("\u21BB SYNCING...")
            self.setup_btn.setEnabled(False)
        elif is_setting_up:
            self.setup_btn.setText("\u26A1 SETTING UP...")
            self.setup_btn.setEnabled(False)
        elif is_installed:
            self.setup_btn.setText("\u21BB Check Updates")
            self.setup_btn.setProperty("variant", "ghost")
            self.setup_btn.style().unpolish(self.setup_btn)
            self.setup_btn.style().polish(self.setup_btn)
            self.setup_btn.setEnabled(not is_busy)
        else:
            self.setup_btn.setText("\u26A1 Setup Everything")
            self.setup_btn.setEnabled(not is_busy)

        can_use = is_installed and not is_busy and not is_syncing
        self.discover_btn.setEnabled(can_use)
        self.models_btn.setEnabled(can_use)
        self.studio_btn.setEnabled(can_use)

        if is_updating:
            self.gpu_lbl.setText(f"{gpu} (Checking updates...)")
        elif is_syncing:
            self.gpu_lbl.setText(f"{gpu} (Syncing...)")
        elif is_setting_up:
            self.gpu_lbl.setText(f"{gpu} (Updating...)")
