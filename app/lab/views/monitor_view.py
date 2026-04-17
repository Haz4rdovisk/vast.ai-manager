"""Monitor view — llama-server status + log viewer. Glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, MetricTile


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

        # Header
        title = QLabel("Server Monitor")
        title.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 24px; font-weight: 700;"
        )
        root.addWidget(title)

        # Status strip
        strip = QHBoxLayout()
        strip.setSpacing(t.SPACE_3)
        self.status_tile = MetricTile("Status", "\u2014", "")
        self.model_tile = MetricTile("Model", "\u2014", "")
        self.config_tile = MetricTile("Config", "\u2014", "")
        strip.addWidget(self.status_tile)
        strip.addWidget(self.model_tile)
        strip.addWidget(self.config_tile)
        root.addLayout(strip)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_2)
        self.stop_btn = QPushButton("\u25A0  Stop Server")
        self.stop_btn.setProperty("variant", "danger")
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.clicked.connect(self.stop_requested.emit)

        self.restart_btn = QPushButton("\u21BB  Restart")
        self.restart_btn.setProperty("variant", "ghost")
        self.restart_btn.setMinimumHeight(38)
        self.restart_btn.clicked.connect(self.restart_requested.emit)

        self.config_btn = QPushButton("\u2699  Reconfigure")
        self.config_btn.setProperty("variant", "ghost")
        self.config_btn.setMinimumHeight(38)
        self.config_btn.clicked.connect(
            lambda: self.navigate_requested.emit("configure")
        )

        self.log_btn = QPushButton("Fetch Log")
        self.log_btn.setProperty("variant", "ghost")
        self.log_btn.setMinimumHeight(38)
        self.log_btn.clicked.connect(self.fetch_log_requested.emit)

        actions.addWidget(self.stop_btn)
        actions.addWidget(self.restart_btn)
        actions.addWidget(self.config_btn)
        actions.addStretch()
        actions.addWidget(self.log_btn)
        root.addLayout(actions)

        # Performance placeholder
        perf_card = GlassCard()
        perf_lay = perf_card.body()
        perf_row = QHBoxLayout()
        perf_row.setSpacing(t.SPACE_3)
        self.req_tile = MetricTile("REQUESTS", "\u2014")
        self.lat_tile = MetricTile("LATENCY", "\u2014")
        self.tps_tile = MetricTile("TOKENS/S", "\u2014")
        perf_row.addWidget(self.req_tile)
        perf_row.addWidget(self.lat_tile)
        perf_row.addWidget(self.tps_tile)
        perf_lay.addLayout(perf_row)
        hint = QLabel("Live performance metrics coming soon")
        hint.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-style: italic;"
            f" font-size: {t.FONT_SIZE_SMALL}px;"
        )
        hint.setAlignment(Qt.AlignCenter)
        perf_lay.addWidget(hint)
        root.addWidget(perf_card)

        # Log output
        log_card = GlassCard()
        log_card.body().addWidget(SectionHeader("LOG", "Remote server output"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(200)
        font = self.log_view.font()
        font.setFamily("JetBrains Mono")
        font.setPointSize(10)
        self.log_view.setFont(font)
        self.log_view.setStyleSheet(
            f"background: {t.BG_VOID}; color: {t.TEXT};"
            f" border: 1px solid {t.BORDER_LOW};"
            f" border-radius: {t.RADIUS_MD}px;"
            f" padding: 10px;"
        )
        self.log_view.setPlainText("Click 'Fetch Log' to see remote output.")
        log_card.body().addWidget(self.log_view)
        root.addWidget(log_card, 1)

        self.store.setup_status_changed.connect(self._render)
        self.store.server_params_changed.connect(self._render_config)

    def set_log(self, text: str):
        self.log_view.setPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _render(self, s):
        if s.llama_server_running:
            self.status_tile.set_value("RUNNING", "process active")
            self.status_tile.set_color(t.LIVE)
            self.model_tile.set_value(
                s.llama_server_model.split("/")[-1]
                if s.llama_server_model else "\u2014",
                s.llama_server_model or "no model"
            )
        else:
            self.status_tile.set_value("STOPPED", "no process")
            self.status_tile.set_color(t.TEXT_MID)
            self.model_tile.set_value("\u2014", "")

    def _render_config(self, p):
        from app.lab.services.model_params import params_summary
        self.config_tile.set_value("Configured", params_summary(p))
