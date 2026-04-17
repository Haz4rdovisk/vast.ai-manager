"""Monitor view \u2014 llama-server status, log viewer, stop/restart."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit,
)
from PySide6.QtCore import Signal
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, MetricTile, StatusPill


class MonitorView(QWidget):
    stop_requested = Signal()
    restart_requested = Signal()
    fetch_log_requested = Signal()
    navigate_requested = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        root.addWidget(SectionHeader("SERVER", "Monitor llama-server"))

        # Status strip
        strip = QHBoxLayout()
        strip.setSpacing(t.SPACE_4)
        self.status_tile = MetricTile("Status", "\u2014", "")
        self.model_tile = MetricTile("Model", "\u2014", "")
        self.config_tile = MetricTile("Config", "\u2014", "")
        strip.addWidget(self.status_tile)
        strip.addWidget(self.model_tile)
        strip.addWidget(self.config_tile)
        root.addLayout(strip)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_3)
        self.stop_btn = QPushButton("\u25A0  Stop Server")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.restart_btn = QPushButton("\u21BB  Restart")
        self.restart_btn.clicked.connect(self.restart_requested.emit)
        self.config_btn = QPushButton("\u2699  Reconfigure")
        self.config_btn.clicked.connect(lambda: self.navigate_requested.emit("configure"))
        self.log_btn = QPushButton("Fetch Log")
        self.log_btn.setProperty("variant", "ghost")
        self.log_btn.clicked.connect(self.fetch_log_requested.emit)
        actions.addWidget(self.stop_btn)
        actions.addWidget(self.restart_btn)
        actions.addWidget(self.config_btn)
        actions.addStretch()
        actions.addWidget(self.log_btn)
        root.addLayout(actions)

        # Log output
        log_card = GlassCard()
        log_card.body().addWidget(SectionHeader("LOG", "Remote server log"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(300)
        font = self.log_view.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        self.log_view.setFont(font)
        self.log_view.setPlainText("Click 'Fetch Log' to see remote output.")
        log_card.body().addWidget(self.log_view)
        root.addWidget(log_card, 1)

        self.store.setup_status_changed.connect(self._render)
        self.store.server_params_changed.connect(self._render_config)

    def set_log(self, text: str):
        self.log_view.setPlainText(text)
        # Auto scroll to bottom
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _render(self, s):
        if s.llama_server_running:
            self.status_tile.set_value("RUNNING", "process active")
            self.model_tile.set_value(
                s.llama_server_model.split("/")[-1] if s.llama_server_model else "\u2014",
                s.llama_server_model or "no model"
            )
        else:
            self.status_tile.set_value("STOPPED", "no process")
            self.model_tile.set_value("\u2014", "")

    def _render_config(self, p):
        from app.lab.services.model_params import params_summary
        self.config_tile.set_value("Configured", params_summary(p))
