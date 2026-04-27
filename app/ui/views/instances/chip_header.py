from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.models import Instance, InstanceState
from app.theme import FONT_DISPLAY, OK, TEXT_LOW, ERR
from app.ui.components.primitives import Chip, ChipRow


_FLAGS = {
    "US": "🇺🇸", "DE": "🇩🇪", "BR": "🇧🇷", "FR": "🇫🇷", "GB": "🇬🇧",
    "CA": "🇨🇦", "JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳", "IN": "🇮🇳",
    "NL": "🇳🇱", "SE": "🇸🇪", "FI": "🇫🇮", "PL": "🇵🇱", "RU": "🇷🇺",
    "AU": "🇦🇺", "MX": "🇲🇽", "AR": "🇦🇷", "ES": "🇪🇸", "IT": "🇮🇹",
}


def _fmt_uptime(secs: int | None) -> str:
    if not secs or secs <= 0:
        return "—"
    days, rem = divmod(int(secs), 86400)
    if days:
        return f"{days}d"
    hours, rem = divmod(rem, 3600)
    if hours:
        return f"{hours}h"
    minutes, _ = divmod(rem, 60)
    return f"{minutes}m"


def _fmt_price(dph: float | None) -> str:
    if dph is None:
        return "—"
    if dph < 0.001:
        return "<$0.001/hr"
    return f"${dph:.3f}/hr"


class ChipHeader(QFrame):
    """Top row of an InstanceCard: LED, GPU label, and chip strip."""

    ip_clicked = Signal()

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self._chips: list[Chip] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.gpu_label = QLabel()
        font = self.gpu_label.font()
        font.setFamily(FONT_DISPLAY)
        font.setPointSize(11)
        font.setBold(True)
        self.gpu_label.setFont(font)
        lay.addWidget(self.gpu_label)

        self.chips_row = ChipRow(self)
        lay.addWidget(self.chips_row)
        
        lay.addStretch(1) # Visual separation: Move status to the far right
        
        self.status_chip = Chip("OFFLINE")
        lay.addWidget(self.status_chip)
        
        self.update_instance(inst)

    def update_instance(self, inst: Instance):
        led_color = OK if inst.state == InstanceState.RUNNING else TEXT_LOW
        self.gpu_label.setText(f"\u25cf {inst.num_gpus or 1}\u00d7 {inst.gpu_name}")
        self.gpu_label.setStyleSheet(f"color: {led_color};")
        
        self.chips_row.clear()
        self._chips = []
        
        if inst.is_verified:
            self._add(Chip("\u2713 Verified", variant="ok"))
        if inst.public_ip:
            ip = Chip(inst.public_ip, variant="accent", mono=True, clickable=True)
            ip.clicked.connect(self.ip_clicked)
            self._add(ip)
        flag = _FLAGS.get((inst.country or "").upper())
        if flag:
            self._add(Chip(flag))
        self._add(Chip(f"\u23f1 {_fmt_uptime(inst.duration_seconds)}"))
        self._add(Chip(_fmt_price(inst.dph), mono=True))

        # Update the dedicated Status Chip on the far right
        status_variant = "default"
        status_label = inst.state.value.upper()
        if inst.state == InstanceState.RUNNING:
            status_variant, status_label = "ok", "RUNNING"
        elif inst.state == InstanceState.SCHEDULING:
            status_variant, status_label = "accent", "SCHEDULING"
        elif inst.state == InstanceState.STOPPED:
            status_variant, status_label = "default", "OFFLINE"
        elif inst.state == InstanceState.STARTING:
            status_variant, status_label = "accent", "STARTING"
        elif inst.state == InstanceState.STOPPING:
            status_variant, status_label = "danger", "STOPPING"
        elif inst.state == InstanceState.OUTBID:
            status_variant, status_label = "danger", "OUTBID"

        self.status_chip.label.setText(status_label)
        from app.ui.components.primitives import _CHIP_VARIANTS
        bg, border, fg = _CHIP_VARIANTS.get(status_variant, _CHIP_VARIANTS["default"])
        self.status_chip.label.setStyleSheet(f"color: {fg}; background: transparent;")
        self.status_chip.setStyleSheet(
            f"QFrame#chip {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: 999px; }}"
        )

    def _add(self, chip: Chip) -> None:
        self._chips.append(chip)
        self.chips_row.add(chip)

    def chip_texts(self) -> list[str]:
        out: list[str] = []
        for chip in self._chips:
            for label in chip.findChildren(QLabel):
                out.append(label.text())
        return out
