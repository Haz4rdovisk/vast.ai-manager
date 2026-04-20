from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel

from app.models import Instance, InstanceState, TunnelStatus
from app.theme import ACCENT, ACCENT_HI, BORDER_LOW, ERR, FONT_DISPLAY, TEXT, OK, TEXT_MID
from app.ui.components import icons
from app.ui.components.primitives import IconButton, Chip


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFixedSize(1, 16)
    sep.setStyleSheet(f"background: {BORDER_LOW};")
    return sep


SCHEDULING_TOOLTIP = (
    "Attempting to schedule your instance. Your GPU is currently in use, and\n"
    "your instance will not be able to start until it is free again - which\n"
    "could take anywhere from hours to weeks. You can copy your data directory\n"
    "from this instance to a new running instance using the copy buttons on\n"
    "the control panel. See docs for more info."
)

STOP_TOOLTIP = "Stop your instance. Storage charges still apply. See FAQ for details."


def _status_text(inst: Instance, *keys: str) -> str:
    for key in keys:
        value = inst.raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return ""


def is_scheduling_instance(inst: Instance) -> bool:
    if inst.raw.get("_is_scheduling") is True:
        return True
    actual = _status_text(
        inst,
        "_normalized_actual_status",
        "actual_status",
        "cur_state",
        "current_state",
        "container_state",
    )
    intended = _status_text(
        inst,
        "_normalized_intended_status",
        "intended_status",
        "next_state",
        "desired_status",
        "target_status",
        "target_state",
    )
    message = str(inst.status_message or "").lower()
    if "schedul" in message or "gpu is currently in use" in message:
        return True
    if actual in {"pending", "queued", "scheduling"}:
        return True
    return intended == "running" and actual in {"", "stopped", "exited", "offline", "none"}


def _scheduling_tooltip(inst: Instance) -> str:
    message = str(inst.status_message or "").strip()
    low = message.lower()
    if message and ("schedul" in low or "gpu is currently in use" in low):
        return message
    return SCHEDULING_TOOLTIP


class ActionBar(QFrame):
    """Refined action row: Power toggle, Real-time status, and Connection controls."""

    activate_requested = Signal()
    deactivate_requested = Signal()
    connect_requested = Signal()
    disconnect_requested = Signal()
    reboot_requested = Signal()
    snapshot_requested = Signal()
    destroy_requested = Signal()
    log_requested = Signal()
    label_requested = Signal()
    flag_requested = Signal()
    key_requested = Signal()
    lab_requested = Signal()
    fix_ssh_requested = Signal()

    def __init__(self, inst: Instance, tunnel: TunnelStatus, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)

        # 1. Power lifecycle button (Subtle Icon)
        self.btn_power = IconButton(icons.POWER, "Toggle power")
        lay.addWidget(self.btn_power)
        
        lay.addWidget(_separator())

        # 2. Standard Icons
        self.btn_reboot = IconButton(icons.REBOOT, "Reboot")
        self.btn_snapshot = IconButton(icons.CLOUD, "Snapshot")
        self.btn_destroy = IconButton(icons.RECYCLE, "Destroy", danger=True)
        self.btn_log = IconButton(icons.LOG, "Logs")
        self.btn_label = IconButton(icons.TAG, "Label")
        self.btn_key = IconButton(icons.KEY, "SSH Key")
        self.btn_lab = IconButton(icons.LAB, "AI Lab")
        
        for btn in (self.btn_reboot, self.btn_snapshot, self.btn_destroy, 
                    self.btn_log, self.btn_label, self.btn_key, self.btn_lab):
            lay.addWidget(btn)

        lay.addStretch(1)

        # 3. Connection Button (Sleek, at the right)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setFixedHeight(26)
        c_font = self.btn_connect.font()
        c_font.setFamily(FONT_DISPLAY)
        c_font.setPointSize(9)
        c_font.setBold(True)
        self.btn_connect.setFont(c_font)
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setProperty("size", "sm")
        # Override padding to prevent clipping at 26px height
        self.btn_connect.setStyleSheet("padding: 2px 14px;")
        self.primary = self.btn_connect
        lay.addWidget(self.btn_connect)

        # Connections
        self.btn_reboot.clicked.connect(self.reboot_requested)
        self.btn_snapshot.clicked.connect(self.snapshot_requested)
        self.btn_destroy.clicked.connect(self.destroy_requested)
        self.btn_log.clicked.connect(self.log_requested)
        self.btn_label.clicked.connect(self.label_requested)
        self.btn_key.clicked.connect(self.key_requested)
        self.btn_lab.clicked.connect(self.lab_requested)
        
        self.update_state(inst, tunnel)

    def update_state(self, inst: Instance, tunnel: TunnelStatus) -> None:
        scheduling = is_scheduling_instance(inst)

        # 1. Status & Colors
        variant = "default"
        label = inst.state.value.upper()
        p_color = TEXT_MID
        p_sig = None
        p_tip = "Busy"
        
        if inst.state == InstanceState.RUNNING:
            p_color, p_sig, p_tip = ERR, self.deactivate_requested, "Stop Instance"
        elif inst.state == InstanceState.SCHEDULING or scheduling:
            p_color, p_sig, p_tip = "#FFA000", self.deactivate_requested, "Cancel Search"
        elif inst.state == InstanceState.STOPPED:
            p_color, p_sig, p_tip = OK, self.activate_requested, "Start Instance"
        elif inst.state == InstanceState.STARTING:
            p_color, p_sig, p_tip = ACCENT_HI, None, "Starting..."
        elif inst.state == InstanceState.STOPPING:
            p_color, p_sig, p_tip = ERR, None, "Stopping..."

        # Update Power Button
        self.btn_power._base_color = p_color
        self.btn_power.setToolTip(p_tip)
        self.btn_power._refresh_icon()
        try: self.btn_power.clicked.disconnect()
        except: pass
        if p_sig:
            self.btn_power.clicked.connect(lambda: p_sig.emit())
            self.btn_power.setEnabled(True)
        else:
            self.btn_power.setEnabled(False)

        # 2. Connection Logic
        c_label = "Connect"
        c_sig = None
        c_color_qss = "" 
        c_enabled = (inst.state == InstanceState.RUNNING)
        
        if tunnel == TunnelStatus.CONNECTING:
            c_label = "Connecting..."
        elif tunnel == TunnelStatus.CONNECTED:
            c_label, c_sig = "Disconnect", self.disconnect_requested
            c_color_qss = f"background: {ERR};"
        elif tunnel == TunnelStatus.FAILED:
            c_label, c_sig = "Retry", self.connect_requested
        else:
            c_sig = self.connect_requested

        self.btn_connect.setText(c_label)
        self.btn_connect.setEnabled(c_enabled)
        self.btn_connect.setToolTip(_scheduling_tooltip(inst) if scheduling else "")
        self.btn_connect.setStyleSheet(f"padding: 2px 14px; {c_color_qss}") 
        
        try: self.btn_connect.clicked.disconnect()
        except: pass
        if c_sig:
            self.btn_connect.clicked.connect(lambda: c_sig.emit())

        # 3. Shared Icons
        try: self.btn_reboot.clicked.disconnect()
        except: pass
        if scheduling:
            self.btn_reboot.setEnabled(True)
            self.btn_reboot.setToolTip(STOP_TOOLTIP)
            self.btn_reboot.clicked.connect(lambda: self.deactivate_requested.emit())
        else:
            self.btn_reboot.setEnabled(inst.state == InstanceState.RUNNING)
            self.btn_reboot.setToolTip("Reboot")
            self.btn_reboot.clicked.connect(self.reboot_requested)
        self.btn_snapshot.setEnabled(inst.state != InstanceState.STOPPING)
        self.btn_destroy.setEnabled(inst.state == InstanceState.STOPPED or inst.state == InstanceState.SCHEDULING or scheduling)
