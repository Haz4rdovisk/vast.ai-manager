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

        self.btn_reboot = IconButton(icons.REBOOT, "Reboot")
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

        self.btn_reboot.clicked.connect(self.reboot_requested)
        self.btn_snapshot.clicked.connect(self.snapshot_requested)
        self.btn_destroy.clicked.connect(self.destroy_requested)
        self.btn_log.clicked.connect(self.log_requested)
        self.btn_label.clicked.connect(self.label_requested)
        self.btn_flag.clicked.connect(self.flag_requested)
        self.btn_key.clicked.connect(self.key_requested)
        self.btn_lab.clicked.connect(self.lab_requested)

    def _build_primary(self, inst: Instance, tunnel: TunnelStatus) -> QPushButton:
        if inst.state == InstanceState.STOPPED:
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
        btn.setStyleSheet(
            f"QPushButton {{ background: {color}; color: white; border: none;"
            f" border-radius: 8px; padding: 4px 14px; }}"
            f"QPushButton:hover {{ background: {ACCENT_HI}; }}"
            f"QPushButton:disabled {{ background: {BORDER_LOW}; color: {TEXT}; }}"
        )
        if sig is not None:
            btn.clicked.connect(lambda: sig.emit())
        else:
            btn.setEnabled(False)
        return btn
