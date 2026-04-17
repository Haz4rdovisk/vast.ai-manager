"""Dashboard — multi-instance AI Lab control center. Glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import SectionHeader, GlassCard, MetricTile, StatusPill
from app.ui.components.instance_dashboard_card import InstanceDashboardCard
from app.models import Instance, TunnelStatus


class DashboardView(QWidget):
    probe_requested = Signal()
    setup_requested = Signal(str, int)       # action, iid
    navigate_requested = Signal(str)         # view key
    instance_action_requested = Signal(int, str)  # iid, action

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.cards: dict[int, InstanceDashboardCard] = {}
        self.tunnel_statuses: dict[int, str] = {}
        self._last_instances: list[Instance] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        # ── Header ─────────────────────────────────────────────────────
        head = QHBoxLayout()
        head.setSpacing(t.SPACE_3)

        title_group = QVBoxLayout()
        title_group.setSpacing(4)
        title = QLabel("AI Lab")
        title.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: {t.FONT_SIZE_DISPLAY}px;"
            f" font-weight: 700;"
        )
        subtitle = QLabel("Control center for your remote AI instances")
        subtitle.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px;"
        )
        title_group.addWidget(title)
        title_group.addWidget(subtitle)
        head.addLayout(title_group)
        head.addStretch()

        self.connected_pill = StatusPill("0 connected", "muted")
        head.addWidget(self.connected_pill)
        root.addLayout(head)

        # ── Overview Row ───────────────────────────────────────────────
        overview = QHBoxLayout()
        overview.setSpacing(t.SPACE_3)
        self.tile_instances  = MetricTile("INSTANCES", "0")
        self.tile_components = MetricTile("COMPONENTS", "\u2014")
        self.tile_models     = MetricTile("MODELS", "0")
        overview.addWidget(self.tile_instances)
        overview.addWidget(self.tile_components)
        overview.addWidget(self.tile_models)
        root.addLayout(overview)

        # ── Cards scroll area ──────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.list_lay = QVBoxLayout(self.scroll_content)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(t.SPACE_4)
        self.list_lay.addStretch()
        self.scroll.setWidget(self.scroll_content)
        root.addWidget(self.scroll, 1)

        # ── Empty state ────────────────────────────────────────────────
        self.empty_card = GlassCard()
        ec = self.empty_card.body()
        icon = QLabel("\u25C9")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size: 40pt; color: {t.ACCENT_SOFT};")
        ec.addWidget(icon)
        etitle = QLabel("Awaiting Connections")
        etitle.setAlignment(Qt.AlignCenter)
        etitle.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 18px; font-weight: 600;"
        )
        ec.addWidget(etitle)
        emsg = QLabel(
            "Activate an instance from the Instances tab.\n"
            "The dashboard will light up when SSH connects."
        )
        emsg.setAlignment(Qt.AlignCenter)
        emsg.setWordWrap(True)
        emsg.setProperty("role", "muted")
        emsg.setMaximumWidth(500)
        ec.addWidget(emsg, alignment=Qt.AlignCenter)

        go_btn = QPushButton("Go to Instances \u2192")
        go_btn.setProperty("variant", "ghost")
        go_btn.setFixedWidth(180)
        go_btn.clicked.connect(lambda: self.navigate_requested.emit("instances"))
        btn_wrap = QHBoxLayout()
        btn_wrap.addStretch()
        btn_wrap.addWidget(go_btn)
        btn_wrap.addStretch()
        ec.addLayout(btn_wrap)
        self.list_lay.insertWidget(0, self.empty_card)

        # Store subscribe
        self.store.instance_state_updated.connect(self._on_state_updated)

    # ── Sync from controller ───────────────────────────────────────────
    def sync_instances(self, instances: list[Instance], user_info):
        self._last_instances = instances
        active_ids = {i.id for i in instances if i.ssh_host and i.ssh_port}

        # Remove dead cards
        for iid in list(self.cards.keys()):
            if iid not in active_ids:
                card = self.cards.pop(iid)
                self.list_lay.removeWidget(card)
                card.deleteLater()

        # Add new cards
        for inst in instances:
            if inst.id in active_ids and inst.id not in self.cards:
                card = InstanceDashboardCard(inst.id)
                card.select_requested.connect(
                    lambda iid: self.instance_action_requested.emit(iid, "select")
                )
                card.probe_requested.connect(
                    lambda iid: self.instance_action_requested.emit(iid, "probe")
                )
                card.setup_all_requested.connect(
                    lambda iid: self.instance_action_requested.emit(iid, "setup_all")
                )
                card.navigate_requested.connect(
                    lambda iid, key: self._navigate_to_instance(iid, key)
                )
                self.list_lay.insertWidget(self.list_lay.count() - 1, card)
                self.cards[inst.id] = card

        # Update ALL cards
        for iid in list(self.cards.keys()):
            self._update_card(iid)

        self.empty_card.setVisible(not self.cards)
        self._update_overview()

    def _on_state_updated(self, iid: int, state):
        if iid in self.cards:
            self._update_card(iid)
            self._update_overview()

    def _update_card(self, iid: int):
        card = self.cards.get(iid)
        if not card:
            return
        inst = next((i for i in self._last_instances if i.id == iid), None)
        st = self.store.get_state(iid)

        from app.models import InstanceState
        if not inst or inst.state != InstanceState.RUNNING:
            status = "disconnected"
        else:
            status = self.tunnel_statuses.get(iid, "disconnected")

        card.update_state(st, status, fallback_gpu=inst.gpu_name if inst else "")

    def _update_overview(self):
        n = len(self.cards)
        self.tile_instances.set_value(str(n))

        # Count components & models
        ready = 0
        total = 0
        model_count = 0
        connected = 0
        for iid in self.cards:
            st = self.store.get_state(iid)
            if st.setup.llmfit_installed:
                ready += 1
            total += 1
            if st.setup.llamacpp_installed:
                ready += 1
            total += 1
            model_count += st.setup.model_count
            status = self.tunnel_statuses.get(iid, "disconnected")
            if status == "connected":
                connected += 1

        self.tile_components.set_value(
            f"{ready}/{total}" if total > 0 else "\u2014",
            "ready" if ready == total and total > 0 else ""
        )
        self.tile_models.set_value(str(model_count))

        level = "live" if connected > 0 else "muted"
        self.connected_pill.set_status(
            f"{connected} connected" if connected != 1 else "1 connected",
            level
        )

    def update_tunnel_status(self, iid: int, status: str):
        self.tunnel_statuses[iid] = status
        if iid in self.cards:
            self._update_card(iid)
            self._update_overview()

    def _navigate_to_instance(self, iid: int, view_key: str):
        self.instance_action_requested.emit(iid, "select")
        self.navigate_requested.emit(view_key)
