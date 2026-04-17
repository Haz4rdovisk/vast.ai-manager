"""Dashboard \u2014 instance selector, setup status, quick actions."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, MetricTile, StatusPill


class DashboardView(QWidget):
    probe_requested = Signal()
    setup_requested = Signal(str)     # "llmfit" | "llamacpp" | "all"
    navigate_requested = Signal(str)  # nav key

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        # Instance selector header
        head = QHBoxLayout()
        head.addWidget(SectionHeader("REMOTE INSTANCE", "AI Lab Dashboard"))
        head.addStretch()
        self.refresh_btn = QPushButton("\u21BB  Refresh")
        self.refresh_btn.clicked.connect(self.probe_requested.emit)
        head.addWidget(self.refresh_btn)
        root.addLayout(head)

        # Instance info card
        self.info_card = GlassCard(raised=True)
        self.instance_lbl = QLabel("No instance selected")
        self.instance_lbl.setProperty("role", "display")
        self.instance_sub = QLabel("Select an instance from Cloud view or click a model card.")
        self.instance_sub.setProperty("role", "muted")
        self.instance_sub.setWordWrap(True)
        self.info_card.body().addWidget(self.instance_lbl)
        self.info_card.body().addWidget(self.instance_sub)
        root.addWidget(self.info_card)

        # Setup status strip
        status_row = QHBoxLayout()
        status_row.setSpacing(t.SPACE_4)
        self.llmfit_tile = MetricTile("LLMfit", "\u2014", "model advisor")
        self.llama_tile = MetricTile("llama.cpp", "\u2014", "inference engine")
        self.models_tile = MetricTile("Models", "\u2014", "GGUF on instance")
        self.server_tile = MetricTile("Server", "\u2014", "llama-server")
        status_row.addWidget(self.llmfit_tile)
        status_row.addWidget(self.llama_tile)
        status_row.addWidget(self.models_tile)
        status_row.addWidget(self.server_tile)
        root.addLayout(status_row)

        # Setup actions card
        self.setup_card = GlassCard()
        self.setup_card.body().addWidget(SectionHeader("SETUP", "Instance Setup"))
        self.setup_status_lbl = QLabel("Probe the instance to check what's installed.")
        self.setup_status_lbl.setWordWrap(True)
        self.setup_card.body().addWidget(self.setup_status_lbl)
        setup_btns = QHBoxLayout()
        self.install_all_btn = QPushButton("\u26A1 Setup Everything")
        self.install_all_btn.clicked.connect(lambda: self.setup_requested.emit("all"))
        self.install_llmfit_btn = QPushButton("Install LLMfit")
        self.install_llmfit_btn.setProperty("variant", "ghost")
        self.install_llmfit_btn.clicked.connect(lambda: self.setup_requested.emit("llmfit"))
        self.install_llama_btn = QPushButton("Install llama.cpp")
        self.install_llama_btn.setProperty("variant", "ghost")
        self.install_llama_btn.clicked.connect(lambda: self.setup_requested.emit("llamacpp"))
        setup_btns.addWidget(self.install_all_btn)
        setup_btns.addWidget(self.install_llmfit_btn)
        setup_btns.addWidget(self.install_llama_btn)
        setup_btns.addStretch()
        self.setup_card.body().addLayout(setup_btns)
        root.addWidget(self.setup_card)

        # Hardware info card (from LLMfit)
        self.hw_card = GlassCard()
        self.hw_card.body().addWidget(SectionHeader("HARDWARE", "Remote Instance Specs"))
        self.hw_lbl = QLabel("Probe instance to see hardware details.")
        self.hw_lbl.setProperty("role", "muted")
        self.hw_lbl.setWordWrap(True)
        self.hw_card.body().addWidget(self.hw_lbl)
        root.addWidget(self.hw_card)

        # Quick actions
        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_3)
        disc_btn = QPushButton("\u2726 Discover Models")
        disc_btn.clicked.connect(lambda: self.navigate_requested.emit("discover"))
        models_btn = QPushButton("\u25A4 View Models")
        models_btn.clicked.connect(lambda: self.navigate_requested.emit("models"))
        mon_btn = QPushButton("\u25F4 Monitor Server")
        mon_btn.clicked.connect(lambda: self.navigate_requested.emit("monitor"))
        actions.addWidget(disc_btn)
        actions.addWidget(models_btn)
        actions.addWidget(mon_btn)
        actions.addStretch()
        root.addLayout(actions)

        root.addStretch()

        # Subscribe to store
        self.store.setup_status_changed.connect(self._render_status)
        self.store.remote_system_changed.connect(self._render_hw)
        self.store.instance_changed.connect(self._render_instance)

    def set_instance_info(self, iid: int, gpu_name: str, ssh_host: str):
        self.instance_lbl.setText(f"Instance #{iid}")
        self.instance_sub.setText(f"{gpu_name}  \u00b7  {ssh_host}")

    def _render_instance(self, iid):
        if not iid:
            self.instance_lbl.setText("No instance selected")
            self.instance_sub.setText("Select an instance from Cloud view.")

    def _render_status(self, s):
        self.llmfit_tile.set_value(
            "READY" if s.llmfit_serving else ("INSTALLED" if s.llmfit_installed else "MISSING"),
            "serving" if s.llmfit_serving else ("not serving" if s.llmfit_installed else "not installed"),
        )
        self.llama_tile.set_value(
            "READY" if s.llamacpp_installed else "MISSING",
            s.llamacpp_path or "not found",
        )
        self.models_tile.set_value(
            str(s.model_count), "GGUF files on instance"
        )
        self.server_tile.set_value(
            "RUNNING" if s.llama_server_running else "STOPPED",
            s.llama_server_model or "no model loaded",
        )

        # Update setup hints
        missing = []
        if not s.llmfit_installed:
            missing.append("LLMfit")
        if not s.llamacpp_installed:
            missing.append("llama.cpp")
        if missing:
            self.setup_status_lbl.setText(
                f"Missing: {', '.join(missing)}. Click Setup to install automatically.")
            self.setup_status_lbl.setStyleSheet(f"color: {t.WARN};")
        else:
            self.setup_status_lbl.setText("All tools installed. \u2714")
            self.setup_status_lbl.setStyleSheet(f"color: {t.OK};")

    def _render_hw(self, sys):
        parts = []
        if sys.gpu_name:
            vram = f"{sys.gpu_vram_gb:.0f} GB" if sys.gpu_vram_gb else "?"
            parts.append(f"\u2022 GPU: {sys.gpu_name} ({vram} VRAM)")
            if sys.gpu_count > 1:
                parts.append(f"  \u00d7 {sys.gpu_count} GPUs")
        if sys.cpu_name:
            parts.append(f"\u2022 CPU: {sys.cpu_name} ({sys.cpu_cores} cores)")
        if sys.ram_total_gb:
            parts.append(f"\u2022 RAM: {sys.ram_total_gb:.0f} GB total, {sys.ram_available_gb:.0f} GB free")
        if sys.backend:
            parts.append(f"\u2022 Backend: {sys.backend}")
        self.hw_lbl.setText("\n".join(parts) if parts else "No hardware info available.")
