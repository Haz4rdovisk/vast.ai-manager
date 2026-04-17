"""Instances view — landing page with billing strip, instance cards,
and collapsible console. Glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox, QFrame,
)
from app import theme as t
from app.controller import AppController
from app.models import Instance, InstanceState, TunnelStatus, UserInfo
from app.ui.components.primitives import StatusPill, GlassCard
from app.ui.views.billing_strip import BillingStrip
from app.ui.views.console_drawer import ConsoleDrawer
from app.ui.views.instance_card import InstanceCard



class InstancesView(QWidget):
    open_lab_requested = Signal(int)
    open_settings_requested = Signal()
    open_analytics_requested = Signal()

    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.cards: dict[int, InstanceCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        # ── Header ─────────────────────────────────────────────────────
        head = QHBoxLayout()
        head.setSpacing(t.SPACE_3)

        title = QLabel("My Instances")
        title.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 24px; font-weight: 700;"
        )
        head.addWidget(title)

        self.active_pill = StatusPill("0 active", "muted")
        head.addWidget(self.active_pill)
        head.addStretch()

        self.interval_combo = QComboBox()
        self.interval_combo.addItems(
            ["\u21BA 5s", "\u21BA 10s", "\u21BA 30s", "\u21BA 60s", "\u21BA off"]
        )
        idx_map = {5: 0, 10: 1, 30: 2, 60: 3, 0: 4}
        self.interval_combo.setCurrentIndex(
            idx_map.get(controller.config.refresh_interval_seconds, 2)
        )
        self.interval_combo.currentIndexChanged.connect(
            self._on_interval_changed
        )
        head.addWidget(self.interval_combo)

        self.refresh_btn = QPushButton("\u21BB  Refresh")
        self.refresh_btn.setProperty("variant", "ghost")
        self.refresh_btn.clicked.connect(controller.request_refresh)
        head.addWidget(self.refresh_btn)

        self.settings_btn = QPushButton("\u2699")
        self.settings_btn.setProperty("variant", "ghost")
        self.settings_btn.setFixedWidth(42)
        self.settings_btn.clicked.connect(self.open_settings_requested)
        head.addWidget(self.settings_btn)
        root.addLayout(head)

        # ── Billing strip ──────────────────────────────────────────────
        self.billing = BillingStrip(controller.config)
        self.billing.analytics_requested.connect(self.open_analytics_requested)
        root.addWidget(self.billing)

        # ── Instance list scroll ───────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(t.SPACE_3)

        # Empty: no key
        self.empty_card = GlassCard()
        ec_lay = self.empty_card.body()
        icon = QLabel("\u2726")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"font-size: 48pt; color: {t.ACCENT_SOFT};"
        )
        ec_lay.addWidget(icon)
        welcome = QLabel("Welcome to Vast.ai Manager")
        welcome.setAlignment(Qt.AlignCenter)
        welcome.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 18px; font-weight: 600;"
        )
        ec_lay.addWidget(welcome)
        hint = QLabel(
            "Configure your API key to see your cloud GPU instances."
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        ec_lay.addWidget(hint)
        go_btn = QPushButton("Open Settings")
        go_btn.setFixedWidth(160)
        go_btn.clicked.connect(self.open_settings_requested)
        btn_wrap = QHBoxLayout()
        btn_wrap.addStretch()
        btn_wrap.addWidget(go_btn)
        btn_wrap.addStretch()
        ec_lay.addLayout(btn_wrap)
        self.list_layout.addWidget(self.empty_card)

        # Empty: has key but no instances
        self.empty_lbl = QLabel(
            "No instances found in your Vast.ai account."
        )
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setProperty("role", "muted")
        self.empty_lbl.setStyleSheet(
            f"padding: 80px 0; font-size: 13pt; color: {t.TEXT_MID};"
        )
        self.list_layout.addWidget(self.empty_lbl)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        # ── Console drawer (collapsible) ───────────────────────────────
        self._console_expanded = False
        self.console_wrap = QFrame()
        self.console_wrap.setStyleSheet("border: none; background: transparent;")
        cw_lay = QVBoxLayout(self.console_wrap)
        cw_lay.setContentsMargins(0, 0, 0, 0)
        cw_lay.setSpacing(0)

        self.toggle_console_btn = QPushButton("Console \u25BE")
        self.toggle_console_btn.setProperty("variant", "ghost")
        self.toggle_console_btn.setFixedHeight(28)
        self.toggle_console_btn.setStyleSheet(
            f"font-size: 10px; color: {t.TEXT_LOW}; padding: 2px 12px;"
            f" border: none; text-align: right;"
        )
        self.toggle_console_btn.clicked.connect(self._toggle_console)
        cw_lay.addWidget(self.toggle_console_btn)

        self.console = ConsoleDrawer()
        self.console.setMaximumHeight(0)
        cw_lay.addWidget(self.console)
        root.addWidget(self.console_wrap)

        # ── Controller wiring ──────────────────────────────────────────
        controller.instances_refreshed.connect(self.handle_refresh)
        controller.tunnel_status_changed.connect(self._on_tunnel_status)
        controller.live_metrics.connect(self._on_live_metrics)
        controller.model_changed.connect(self._on_model_changed)
        controller.log_line.connect(self.console.log)

    # ── Console toggle ─────────────────────────────────────────────────
    def _toggle_console(self):
        self._console_expanded = not self._console_expanded
        target = 200 if self._console_expanded else 0
        self.toggle_console_btn.setText(
            "Console \u25B4" if self._console_expanded else "Console \u25BE"
        )
        anim = QPropertyAnimation(self.console, b"maximumHeight")
        anim.setDuration(t.ANIM_NORMAL)
        anim.setStartValue(self.console.maximumHeight())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        # prevent garbage collection
        self._console_anim = anim

    # ── Refresh ────────────────────────────────────────────────────────
    def handle_refresh(self, instances: list[Instance], user):
        self._rebuild_cards(instances)
        self.billing.update_values(
            user, instances, self.controller.today_spend()
        )
        active = sum(1 for i in instances if i.state == InstanceState.RUNNING)
        level = "live" if active > 0 else "muted"
        self.active_pill.set_status(
            f"{active} active" if active != 1 else "1 active", level
        )

    def _rebuild_cards(self, instances: list[Instance]):
        current = {i.id for i in instances}
        for iid in list(self.cards.keys()):
            if iid not in current:
                card = self.cards.pop(iid)
                self.list_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()

        has_key = bool(self.controller.config.api_key)
        self.empty_card.setVisible(not instances and not has_key)
        self.empty_lbl.setVisible(not instances and has_key)

        for inst in instances:
            tun = self.controller.tunnel_states.get(
                inst.id, TunnelStatus.DISCONNECTED
            )
            if inst.id in self.cards:
                self.cards[inst.id].update_from(
                    inst, tun, self.controller.config.default_tunnel_port
                )
            else:
                c = InstanceCard(inst)
                c.activate_requested.connect(self.controller.activate)
                c.deactivate_requested.connect(self._confirm_deactivate)
                c.reconnect_requested.connect(self.controller.connect_tunnel)
                c.disconnect_requested.connect(
                    self.controller.disconnect_tunnel
                )
                c.open_terminal_requested.connect(self._on_open_terminal)
                c.open_lab_requested.connect(self.open_lab_requested)
                c.copy_endpoint_requested.connect(self._on_copy_endpoint)
                c.update_from(
                    inst, tun, self.controller.config.default_tunnel_port
                )
                insert_at = max(0, self.list_layout.count() - 1)
                self.list_layout.insertWidget(insert_at, c)
                self.cards[inst.id] = c

    # ── Per-card event relays ──────────────────────────────────────────
    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        inst = next(
            (i for i in self.controller.last_instances if i.id == iid), None
        )
        card = self.cards.get(iid)
        if card and inst:
            card.update_from(
                inst, TunnelStatus(status),
                self.controller.config.default_tunnel_port,
            )

    def _on_live_metrics(self, iid: int, d: dict):
        card = self.cards.get(iid)
        if card is not None:
            card.set_live_metrics(d)

    def _on_model_changed(self, iid: int, model_id: str):
        card = self.cards.get(iid)
        if card is not None:
            card.set_loaded_model(model_id or None)

    # ── Commands ───────────────────────────────────────────────────────
    def _confirm_deactivate(self, iid: int):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Deactivate instance",
            "Are you sure? The machine will be stopped and the connection closed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.controller.deactivate(iid)

    def _on_open_terminal(self, iid: int):
        inst = next(
            (i for i in self.controller.last_instances if i.id == iid), None
        )
        if not inst or not inst.ssh_host or not inst.ssh_port:
            self.console.log(f"Terminal unavailable for #{iid}")
            return
        try:
            self.controller.ssh.open_terminal(
                inst.ssh_host, inst.ssh_port,
                self.controller.config.terminal_preference,
            )
            self.console.log(
                f"Terminal opened for {inst.ssh_host}:{inst.ssh_port}"
            )
        except Exception as e:
            self.console.log(f"Failed to open terminal: {e}")

    def _on_copy_endpoint(self, iid: int):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(
            f"http://127.0.0.1:{self.controller.config.default_tunnel_port}"
        )
        self.console.log("Endpoint copied.")

    def _on_interval_changed(self, idx: int):
        mapping = {0: 5, 1: 10, 2: 30, 3: 60, 4: 0}
        self.controller.config.refresh_interval_seconds = mapping[idx]
        self.controller.config_store.save(self.controller.config)
        self.controller.apply_config(self.controller.config)
