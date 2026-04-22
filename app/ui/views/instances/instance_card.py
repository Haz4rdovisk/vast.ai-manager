from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QVBoxLayout

from app.models import Instance, InstanceState, TunnelStatus
from app.theme import BORDER_LOW
from app.ui.components.primitives import GlassCard
from app.ui.views.instances.action_bar import ActionBar
from app.ui.views.instances.chip_header import ChipHeader
from app.ui.views.instances.live_footer import LiveFooter
from app.ui.views.instances.specs_grid import SpecsGrid


def _hr() -> QFrame:
    """A bold horizontal rule with massive 48px vertical breathing room."""
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {BORDER_LOW}; margin: 48px 0px;")
    return line


class InstanceCard(QFrame):
    """Ultra-airy always-open card for professional cluster management."""

    activate_requested = Signal(int)
    deactivate_requested = Signal(int)
    connect_requested = Signal(int)
    disconnect_requested = Signal(int)
    reboot_requested = Signal(int)
    snapshot_requested = Signal(int)
    destroy_requested = Signal(int)
    log_requested = Signal(int)
    label_requested = Signal(int)
    flag_requested = Signal(int)
    key_requested = Signal(int)
    lab_requested = Signal(int)
    selection_toggled = Signal(int, bool)
    ip_copy_requested = Signal(int)
    fix_ssh_requested = Signal(int)

    def __init__(
        self,
        inst: Instance,
        *,
        port: int,
        tunnel: TunnelStatus = TunnelStatus.DISCONNECTED,
        selected: bool = False,
        select_mode: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.inst = inst
        self._tunnel = tunnel
        self._port = port
        self._select_mode = select_mode
        self._selected = selected

        self._card = GlassCard(parent=self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        self._inner = self._card.body()
        # Tightened outer padding (Red areas in screenshot)
        self._inner.setContentsMargins(20, 10, 20, 10) 
        self._inner.setSpacing(0)
        self._build()

    def _build(self) -> None:
        # 1. Header Row
        top = QHBoxLayout()
        top.setSpacing(10)
        top.setContentsMargins(0, 0, 0, 8) # Extra space below header
        self.header = ChipHeader(self.inst, self._card)
        self.header.ip_clicked.connect(lambda: self.ip_copy_requested.emit(self.inst.id))
        top.addWidget(self.header, stretch=1)

        self.select_check = QCheckBox()
        self.select_check.setChecked(self._selected)
        self.select_check.setVisible(self._select_mode)
        self.select_check.toggled.connect(
            lambda value: self.selection_toggled.emit(self.inst.id, bool(value))
        )
        top.addWidget(self.select_check)
        self._inner.addLayout(top)

        # Separator 1: Between Header and Specs
        self._inner.addWidget(_hr())

        # 2. Specs Section
        self.specs = SpecsGrid(self.inst, self._card)
        self._inner.addWidget(self.specs)

        self.live: LiveFooter | None = None
        # Only show live metrics footer if the tunnel is explicitly CONNECTED
        if self._tunnel == TunnelStatus.CONNECTED:
            # Separator 2: Between Specs and Metrics
            self._inner.addWidget(_hr())
            self.live = LiveFooter(self.inst, self._card)
            self._inner.addWidget(self.live)

        # 3. Final Separator for Action Bar
        self._inner.addWidget(_hr())
        
        self.actions = ActionBar(self.inst, self._tunnel, self._card)
        self._wire_actions()
        self._inner.addWidget(self.actions)

    def _wire_actions(self) -> None:
        actions = self.actions
        actions.activate_requested.connect(lambda: self.activate_requested.emit(self.inst.id))
        actions.deactivate_requested.connect(lambda: self.deactivate_requested.emit(self.inst.id))
        actions.connect_requested.connect(lambda: self.connect_requested.emit(self.inst.id))
        actions.disconnect_requested.connect(lambda: self.disconnect_requested.emit(self.inst.id))
        actions.reboot_requested.connect(lambda: self.reboot_requested.emit(self.inst.id))
        actions.snapshot_requested.connect(lambda: self.snapshot_requested.emit(self.inst.id))
        actions.destroy_requested.connect(lambda: self.destroy_requested.emit(self.inst.id))
        actions.log_requested.connect(lambda: self.log_requested.emit(self.inst.id))
        actions.label_requested.connect(lambda: self.label_requested.emit(self.inst.id))
        actions.flag_requested.connect(lambda: self.flag_requested.emit(self.inst.id))
        actions.key_requested.connect(lambda: self.key_requested.emit(self.inst.id))
        actions.lab_requested.connect(lambda: self.lab_requested.emit(self.inst.id))
        actions.fix_ssh_requested.connect(lambda: self.fix_ssh_requested.emit(self.inst.id))

    def update_instance(self, inst: Instance, tunnel: TunnelStatus) -> None:
        # Rebuild required if power state OR tunnel connection state changes
        pstate_changed = (inst.state == InstanceState.RUNNING) != (self.inst.state == InstanceState.RUNNING)
        tunnel_changed = (tunnel == TunnelStatus.CONNECTED) != (self._tunnel == TunnelStatus.CONNECTED)
        
        self.inst = inst
        self.inst = inst
        self._tunnel = tunnel

        if pstate_changed or tunnel_changed:
            self._clear_inner()
            self._build()
            return

        # Otherwise, update in-place
        self.header.update_instance(inst)
        self.specs.update_instance(inst)
        if self.live: self.live.update_instance(inst)
        self.actions.update_state(inst, tunnel)

    def _clear_inner(self) -> None:
        while self._inner.count():
            item = self._inner.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            layout = item.layout()
            if layout is not None:
                while layout.count():
                    child = layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()

    def apply_metrics(self, metrics: dict) -> None:
        if self.live is not None:
            self.live.apply_metrics(metrics)

    def set_select_mode(self, on: bool) -> None:
        self._select_mode = on
        self.select_check.setVisible(on)

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self.select_check.setChecked(on)
