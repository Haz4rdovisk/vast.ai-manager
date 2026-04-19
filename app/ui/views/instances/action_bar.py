from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton

from app.models import Instance, InstanceState, TunnelStatus
from app.theme import ACCENT, ACCENT_HI, BORDER_LOW, ERR, FONT_DISPLAY, TEXT
from app.ui.components import icons
from app.ui.components.primitives import IconButton


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFixedSize(1, 20)
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
    """Primary CTA plus icon button row."""

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

    def __init__(self, inst: Instance, tunnel: TunnelStatus, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(6)

        self.primary = self._build_primary(inst, tunnel)
        lay.addWidget(self.primary)
        lay.addWidget(_separator())

        if inst.state == InstanceState.STARTING:
            self.btn_reboot = IconButton(icons.POWER, STOP_TOOLTIP)
            self.btn_reboot.clicked.connect(self.deactivate_requested)
        else:
            self.btn_reboot = IconButton(icons.REBOOT, "Reboot")
            self.btn_reboot.clicked.connect(self.reboot_requested)
        self.btn_snapshot = IconButton(icons.CLOUD, "Snapshot / save")
        self.btn_destroy = IconButton(icons.RECYCLE, "Destroy", danger=True)
        for btn in (self.btn_reboot, self.btn_snapshot, self.btn_destroy):
            lay.addWidget(btn)

        lay.addWidget(_separator())

        self.btn_log = IconButton(icons.LOG, "View logs")
        self.btn_label = IconButton(icons.TAG, "Edit label")
        self.btn_flag = IconButton(icons.FLAG, "Flag / bookmark")
        for btn in (self.btn_log, self.btn_label, self.btn_flag):
            lay.addWidget(btn)

        lay.addWidget(_separator())

        self.btn_key = IconButton(icons.KEY, "Copy SSH command")
        self.btn_lab = IconButton(icons.LAB, "Open Lab")
        lay.addWidget(self.btn_key)
        lay.addWidget(self.btn_lab)
        lay.addStretch(1)

        self.btn_snapshot.clicked.connect(self.snapshot_requested)
        self.btn_destroy.clicked.connect(self.destroy_requested)
        self.btn_log.clicked.connect(self.log_requested)
        self.btn_label.clicked.connect(self.label_requested)
        self.btn_flag.clicked.connect(self.flag_requested)
        self.btn_key.clicked.connect(self.key_requested)
        self.btn_lab.clicked.connect(self.lab_requested)

    def _build_primary(self, inst: Instance, tunnel: TunnelStatus) -> QPushButton:
        tooltip = ""
        disabled_color = BORDER_LOW
        keep_enabled = False
        if inst.state == InstanceState.STARTING and is_scheduling_instance(inst):
            label, sig, color = "scheduling...", None, ACCENT
            disabled_color = ACCENT
            keep_enabled = True
            tooltip = _scheduling_tooltip(inst)
        elif inst.state == InstanceState.STOPPED:
            label, sig, color = "Activate", self.activate_requested, ACCENT
        elif inst.state == InstanceState.STARTING:
            label, sig, color = "Starting...", None, TEXT
        elif inst.state == InstanceState.RUNNING and tunnel != TunnelStatus.CONNECTED:
            label, sig, color = "Connect", self.connect_requested, ACCENT
        elif inst.state == InstanceState.RUNNING and tunnel == TunnelStatus.CONNECTED:
            label, sig, color = "Deactivate", self.deactivate_requested, ERR
        else:
            label, sig, color = inst.state.value, None, TEXT

        btn = QPushButton(label)
        btn.setFixedHeight(28)
        font = btn.font()
        font.setFamily(FONT_DISPLAY)
        font.setPointSize(9)
        font.setBold(True)
        btn.setFont(font)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setStyleSheet(
            f"QPushButton {{ background: {color}; color: white; border: none;"
            f" border-radius: 8px; padding: 4px 14px; }}"
            f"QPushButton:hover {{ background: {ACCENT_HI}; }}"
            f"QPushButton:disabled {{ background: {disabled_color}; color: white; }}"
        )
        if sig is not None:
            btn.clicked.connect(lambda: sig.emit())
        elif not keep_enabled:
            btn.setEnabled(False)
        return btn
