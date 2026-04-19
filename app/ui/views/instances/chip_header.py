from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.models import Instance, InstanceState
from app.theme import FONT_DISPLAY, OK, TEXT_LOW
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

        led_color = OK if inst.state == InstanceState.RUNNING else TEXT_LOW
        self.gpu_label = QLabel(f"● {inst.num_gpus or 1}× {inst.gpu_name}")
        font = self.gpu_label.font()
        font.setFamily(FONT_DISPLAY)
        font.setPointSize(11)
        font.setBold(True)
        self.gpu_label.setFont(font)
        self.gpu_label.setStyleSheet(f"color: {led_color};")
        lay.addWidget(self.gpu_label)

        self.chips = ChipRow(self)
        lay.addWidget(self.chips, stretch=1)

        if inst.is_verified:
            self._add(Chip("✓ Verified", variant="ok"))
        if inst.public_ip:
            ip = Chip(inst.public_ip, variant="accent", mono=True, clickable=True)
            ip.clicked.connect(self.ip_clicked)
            self._add(ip)
        flag = _FLAGS.get((inst.country or "").upper())
        if flag:
            self._add(Chip(flag))
        self._add(Chip(f"⏱ {_fmt_uptime(inst.duration_seconds)}"))
        self._add(Chip(_fmt_price(inst.dph), mono=True))

    def _add(self, chip: Chip) -> None:
        self._chips.append(chip)
        self.chips.add(chip)

    def chip_texts(self) -> list[str]:
        out: list[str] = []
        for chip in self._chips:
            for label in chip.findChildren(QLabel):
                out.append(label.text())
        return out
