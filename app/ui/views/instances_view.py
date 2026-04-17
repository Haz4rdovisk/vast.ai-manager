"""The Instances view — landing page. Billing strip on top, one InstanceCard
per Vast.ai instance, and a console drawer at the bottom. Consumes signals
from AppController directly."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox,
)
from app import theme as t
from app.controller import AppController
from app.models import Instance, InstanceState, TunnelStatus, UserInfo
from app.ui.components.primitives import SectionHeader, GlassCard
from app.ui.views.billing_strip import BillingStrip
from app.ui.views.console_drawer import ConsoleDrawer
from app.ui.views.instance_card import InstanceCard


class InstancesView(QWidget):
    open_lab_requested = Signal(int)  # iid — propagates to shell to switch tabs
    open_settings_requested = Signal()

    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.cards: dict[int, InstanceCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        # Header row: title + counts + refresh controls
        head = QHBoxLayout()
        head.addWidget(SectionHeader("CLOUD", "Minhas Instâncias"))
        head.addStretch()
        self.active_lbl = QLabel("0 ativas"); self.active_lbl.setProperty("role", "muted")
        head.addWidget(self.active_lbl)

        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["↺ 5s", "↺ 10s", "↺ 30s", "↺ 60s", "↺ off"])
        idx_map = {5: 0, 10: 1, 30: 2, 60: 3, 0: 4}
        self.interval_combo.setCurrentIndex(
            idx_map.get(controller.config.refresh_interval_seconds, 2))
        self.interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        head.addWidget(self.interval_combo)

        self.refresh_btn = QPushButton("Atualizar")
        self.refresh_btn.setProperty("variant", "ghost")
        self.refresh_btn.clicked.connect(controller.request_refresh)
        head.addWidget(self.refresh_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setProperty("variant", "ghost")
        self.settings_btn.setFixedWidth(42)
        self.settings_btn.clicked.connect(self.open_settings_requested)
        head.addWidget(self.settings_btn)
        root.addLayout(head)

        # Billing strip
        self.billing = BillingStrip(controller.config)
        root.addWidget(self.billing)

        # Instance list scroll area
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0); self.list_layout.setSpacing(t.SPACE_3)
        self.empty_card = GlassCard()
        self.empty_card.body().addWidget(SectionHeader("COMEÇAR", "Configure sua API key"))
        hint = QLabel("Cole sua Vast.ai API key em Configurações para começar a ver suas instâncias.")
        hint.setWordWrap(True); hint.setProperty("role", "muted")
        self.empty_card.body().addWidget(hint)
        go_btn = QPushButton("Abrir Configurações")
        go_btn.clicked.connect(self.open_settings_requested)
        self.empty_card.body().addWidget(go_btn)
        self.list_layout.addWidget(self.empty_card)

        self.empty_lbl = QLabel("Nenhuma instância encontrada na sua conta Vast.ai.")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setProperty("role", "muted")
        self.empty_lbl.setStyleSheet(
            f"padding: 80px 0; font-size: 12pt; color: {t.TEXT_MID};"
        )
        self.list_layout.addWidget(self.empty_lbl)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        # Console drawer
        self.console = ConsoleDrawer()
        root.addWidget(self.console)

        # Controller wiring
        controller.instances_refreshed.connect(self.handle_refresh)
        controller.tunnel_status_changed.connect(self._on_tunnel_status)
        controller.live_metrics.connect(self._on_live_metrics)
        controller.model_changed.connect(self._on_model_changed)
        controller.log_line.connect(self.console.log)

    # ---- Refresh ----
    def handle_refresh(self, instances: list[Instance], user):
        self._rebuild_cards(instances)
        self.billing.update_values(user, instances, self.controller.today_spend())
        active = sum(1 for i in instances if i.state == InstanceState.RUNNING)
        self.active_lbl.setText(f"{active} ativa" if active == 1 else f"{active} ativas")

    def _rebuild_cards(self, instances: list[Instance]):
        current = {i.id for i in instances}
        for iid in list(self.cards.keys()):
            if iid not in current:
                card = self.cards.pop(iid)
                self.list_layout.removeWidget(card); card.setParent(None); card.deleteLater()

        has_key = bool(self.controller.config.api_key)
        self.empty_card.setVisible(not instances and not has_key)
        self.empty_lbl.setVisible(not instances and has_key)
        for inst in instances:
            tun = self.controller.tunnel_states.get(inst.id, TunnelStatus.DISCONNECTED)
            if inst.id in self.cards:
                self.cards[inst.id].update_from(inst, tun, self.controller.config.default_tunnel_port)
            else:
                c = InstanceCard(inst)
                c.activate_requested.connect(self.controller.activate)
                c.deactivate_requested.connect(self._confirm_deactivate)
                c.reconnect_requested.connect(self.controller.connect_tunnel)
                c.disconnect_requested.connect(self.controller.disconnect_tunnel)
                c.open_terminal_requested.connect(self._on_open_terminal)
                c.open_lab_requested.connect(self.open_lab_requested)
                c.copy_endpoint_requested.connect(self._on_copy_endpoint)
                c.update_from(inst, tun, self.controller.config.default_tunnel_port)
                insert_at = max(0, self.list_layout.count() - 1)
                self.list_layout.insertWidget(insert_at, c)
                self.cards[inst.id] = c

    # ---- Per-card event relays ----
    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        inst = next((i for i in self.controller.last_instances if i.id == iid), None)
        card = self.cards.get(iid)
        if card and inst:
            card.update_from(inst, TunnelStatus(status),
                             self.controller.config.default_tunnel_port)

    def _on_live_metrics(self, iid: int, d: dict):
        card = self.cards.get(iid)
        if card is not None:
            card.set_live_metrics(d)

    def _on_model_changed(self, iid: int, model_id: str):
        card = self.cards.get(iid)
        if card is not None:
            card.set_loaded_model(model_id or None)

    # ---- Commands ----
    def _confirm_deactivate(self, iid: int):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Desativar instância",
            "Tem certeza? A máquina será parada e a conexão encerrada.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.controller.deactivate(iid)

    def _on_open_terminal(self, iid: int):
        inst = next((i for i in self.controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            self.console.log(f"Terminal indisponível para #{iid}")
            return
        try:
            self.controller.ssh.open_terminal(
                inst.ssh_host, inst.ssh_port,
                self.controller.config.terminal_preference,
            )
            self.console.log(f"Terminal aberto para {inst.ssh_host}:{inst.ssh_port}")
        except Exception as e:
            self.console.log(f"Falha ao abrir terminal: {e}")

    def _on_copy_endpoint(self, iid: int):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(
            f"http://127.0.0.1:{self.controller.config.default_tunnel_port}")
        self.console.log("Endereço copiado.")

    def _on_interval_changed(self, idx: int):
        mapping = {0: 5, 1: 10, 2: 30, 3: 60, 4: 0}
        self.controller.config.refresh_interval_seconds = mapping[idx]
        self.controller.config_store.save(self.controller.config)
        self.controller.apply_config(self.controller.config)
