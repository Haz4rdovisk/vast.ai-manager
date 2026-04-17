"""Dashboard — multi-instance control center."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import SectionHeader, GlassCard
from app.ui.components.instance_dashboard_card import InstanceDashboardCard
from app.models import Instance, TunnelStatus


class DashboardView(QWidget):
    probe_requested = Signal()
    setup_requested = Signal(str, int)  # action, iid
    navigate_requested = Signal(str)    # view key
    instance_action_requested = Signal(int, str) # iid, action

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.cards: dict[int, InstanceDashboardCard] = {}
        self._last_instances: list[Instance] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        # Header
        head = QHBoxLayout()
        head.addWidget(SectionHeader("CONTROL CENTER", "AI Lab Dashboard"))
        head.addStretch()
        root.addLayout(head)

        # Scroll area for cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.list_lay = QVBoxLayout(self.scroll_content)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(t.SPACE_4)
        self.list_lay.addStretch()
        self.scroll.setWidget(self.scroll_content)
        root.addWidget(self.scroll, 1)

        # Placeholder for empty state
        self.empty_card = GlassCard()
        self.empty_card.body().addWidget(SectionHeader("Awaiting Active Connections", "Dashboard is inactive"))
        msg = QLabel("Ative uma instância na aba 'Instances' para começar.\n"
                     "O Lab Dashboard se ativará automaticamente assim que a conexão SSH for estabelecida.")
        msg.setProperty("role", "muted")
        msg.setWordWrap(True)
        self.empty_card.body().addWidget(msg)
        self.list_lay.insertWidget(0, self.empty_card)

        # Global subscribe
        self.store.instance_state_updated.connect(self._on_state_updated)

    def sync_instances(self, instances: list[Instance], user_info):
        """Sync the list of cards with active instances."""
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
                card.select_requested.connect(lambda iid: self.instance_action_requested.emit(iid, "select"))
                card.probe_requested.connect(lambda iid: self.instance_action_requested.emit(iid, "probe"))
                card.setup_all_requested.connect(lambda iid: self.instance_action_requested.emit(iid, "setup_all"))
                card.navigate_requested.connect(lambda iid, key: self._navigate_to_instance(iid, key))
                
                self.list_lay.insertWidget(self.list_lay.count() - 1, card)
                self.cards[inst.id] = card
                
                # Immediate initial render
                self._update_card(inst.id)
        
        self.empty_card.setVisible(not self.cards)

    def _on_state_updated(self, iid: int, state):
        if iid in self.cards:
            self._update_card(iid)

    def _update_card(self, iid: int):
        card = self.cards.get(iid)
        if not card: return
        
        # Find raw instance for SSH status hint
        inst = next((i for i in self._last_instances if i.id == iid), None)
        # We need to know the tunnel status. Dashboard view doesn't have it directly.
        # But AppShell/Controller do. 
        # For simplicity, we'll assume if it's in sync_instances with host/port, it's alive-ish.
        # Better: AppShell should handle this. Or we check store? 
        # Let's just pass empty for now or use the state.
        
        # Actually, let's assume if sync_instances called it, it's 'connected' for now
        # until the next refresh cycle.
        st = self.store.get_state(iid)
        card.update_state(st, "connected", gpu_name_hint=inst.gpu_name if inst else "")

    def _navigate_to_instance(self, iid: int, view_key: str):
        self.instance_action_requested.emit(iid, "select")
        self.navigate_requested.emit(view_key)
