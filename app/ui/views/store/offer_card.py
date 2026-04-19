"""Rich marketplace offer card."""
from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.models_rental import Offer
from app.ui.components.primitives import Badge, GlassCard, StatusPill


def _text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _raw_float(offer: Offer, *names: str) -> float | None:
    for name in names:
        value = offer.raw.get(name)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _fmt_num(value: float | int | None, suffix: str = "", decimals: int = 1) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number == 0:
        text = "0"
    elif abs(number) >= 100:
        text = f"{number:,.0f}"
    elif number.is_integer():
        text = f"{number:.0f}"
    else:
        text = f"{number:,.{decimals}f}"
    return f"{text} {suffix}".strip()


def _fmt_price(value: float | None, unit: str = "hr") -> str:
    if value is None:
        return "-"
    digits = 3 if value < 1 else 2
    return f"${value:.{digits}f}/{unit}"


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _fmt_bool(value: bool, true_text: str, false_text: str) -> str:
    return true_text if value else false_text


def _price_parts(offer: Offer) -> tuple[float, float, float, float | None, float | None]:
    total_hour = max(float(offer.dph_total or 0), 0.0)
    storage_gb = (
        _raw_float(offer, "allocated_storage", "allocated_storage_gb", "disk_gb")
        or offer.disk_space_gb
        or 0.0
    )
    storage_month = max(float(offer.storage_cost or 0.0) * storage_gb, 0.0)
    storage_hour = storage_month / (30.0 * 24.0) if storage_month else 0.0
    gpu_hour = max(total_hour - storage_hour, 0.0)
    inet_up = _raw_float(offer, "inet_up_cost")
    inet_down = _raw_float(offer, "inet_down_cost")
    return gpu_hour, storage_hour, total_hour, inet_up, inet_down


def _price_tooltip(offer: Offer) -> str:
    gpu_hour, storage_hour, total_hour, inet_up, inet_down = _price_parts(offer)

    def row(label: str, hour: float, bold: bool = False) -> str:
        tag = "b" if bold else "span"
        color = "#3BD488" if bold else "#F1F4FA"
        return (
            "<tr>"
            f"<td style='color:{color};'><{tag}>{escape(label)}</{tag}></td>"
            f"<td align='right' style='color:{color};'><{tag}>{_fmt_price(hour)}</{tag}></td>"
            f"<td align='right' style='color:{color};'><{tag}>{_fmt_price(hour * 24, 'day')}</{tag}></td>"
            f"<td align='right' style='color:{color};'><{tag}>{_fmt_price(hour * 24 * 30, 'mo')}</{tag}></td>"
            "</tr>"
        )

    def tb(value: float | None) -> str:
        if value is None:
            return "-"
        return f"${value * 1000:.3f}/TB"

    return f"""
    <div style="font-size:14px; color:#F1F4FA; min-width:420px;">
      <div style="font-size:20px; font-weight:700; margin-bottom:10px;">Price Breakdown</div>
      <table cellspacing="0" cellpadding="5" width="100%">
        {row("On-Demand GPU", gpu_hour)}
        {row("Storage", storage_hour)}
        {row("Total Cost", total_hour, True)}
        <tr>
          <td><b>Internet (usage-based)</b></td>
          <td></td>
          <td align="right">Up {tb(inet_up)}</td>
          <td align="right">Down {tb(inet_down)}</td>
        </tr>
      </table>
      <div style="margin-top:10px; color:#C7CEDC; font-weight:600;">
        Total base cost excludes internet charges, applied only when used.
      </div>
    </div>
    """


class _InfoBlock(QWidget):
    def __init__(self, label: str, value: str, hint: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        label_lbl = QLabel(label)
        label_lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: 12px; font-weight: 800;"
        )
        value_lbl = QLabel(value)
        value_lbl.setWordWrap(True)
        value_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        value_lbl.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 16px; font-weight: 700;"
        )
        hint_lbl = QLabel(hint)
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: 13px; font-weight: 600;"
        )

        lay.addWidget(label_lbl)
        lay.addWidget(value_lbl)
        if hint:
            lay.addWidget(hint_lbl)
        lay.addStretch()


class OfferCard(GlassCard):
    rent_clicked = Signal(object)
    details_clicked = Signal(object)

    def __init__(self, offer: Offer, parent=None):
        super().__init__(raised=True, parent=parent)
        self.offer = offer
        self.setMinimumHeight(190)
        self.body().setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        self.body().setSpacing(t.SPACE_3)

        self._build_header()
        self._build_grid()

    def _build_header(self) -> None:
        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(t.SPACE_3)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(t.SPACE_5)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(5)

        identity = QLabel(
            f"m:{self.offer.machine_id}    host:{_text(self.offer.host_id)}"
            f"    {_text(self.offer.country or self.offer.geolocation, 'Unknown region')}"
        )
        identity.setStyleSheet(
            f"color: {t.TEXT}; font-size: 13px; font-weight: 800;"
        )
        title_wrap.addWidget(identity)

        self.title_lbl = QLabel(f"{self.offer.num_gpus}x {_text(self.offer.gpu_name, 'Unknown GPU')}")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 26px; font-weight: 850;"
        )
        title_wrap.addWidget(self.title_lbl)
        top.addLayout(title_wrap, 1)

        price_box = QVBoxLayout()
        price_box.setContentsMargins(0, 0, 0, 0)
        price_box.setSpacing(5)
        price_box.setAlignment(Qt.AlignRight | Qt.AlignTop)

        self.price_lbl = QLabel(_fmt_price(self.offer.effective_price()))
        self.price_lbl.setAlignment(Qt.AlignRight)
        self.price_lbl.setToolTip(_price_tooltip(self.offer))
        self.price_lbl.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 28px; font-weight: 900;"
        )
        price_hint = QLabel("plus bandwidth")
        price_hint.setAlignment(Qt.AlignRight)
        price_hint.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 750;"
        )
        hover_hint = QLabel("hover for breakdown")
        hover_hint.setAlignment(Qt.AlignRight)
        hover_hint.setStyleSheet(
            f"color: {t.ACCENT_SOFT}; font-size: 12px; font-weight: 800;"
        )

        price_box.addWidget(self.price_lbl)
        price_box.addWidget(price_hint)
        price_box.addWidget(hover_hint)
        top.addLayout(price_box)
        header.addLayout(top)

        badges = QHBoxLayout()
        badges.setContentsMargins(0, 0, 0, 0)
        badges.setSpacing(t.SPACE_4)
        badges.addWidget(StatusPill("verified" if self.offer.verified else "unverified", "ok" if self.offer.verified else "warn"))
        badges.addWidget(StatusPill("rentable" if self.offer.rentable else "unavailable", "ok" if self.offer.rentable else "err"))
        if self.offer.rented:
            badges.addWidget(StatusPill("rented", "warn"))
        if self.offer.external:
            badges.addWidget(Badge("external"))
        if self.offer.hosting_type:
            badges.addWidget(Badge(self.offer.hosting_type))
        if self.offer.static_ip:
            badges.addWidget(Badge("static IP"))
        badges.addStretch()
        header.addLayout(badges)

        self.body().addLayout(header)

    def _build_grid(self) -> None:
        total_flops = _raw_float(self.offer, "total_flops", "flops", "total_flops_tflops")
        pcie_bw = _raw_float(self.offer, "pcie_bw", "pcie_bandwidth")
        pci_gen = _raw_float(self.offer, "pci_gen")
        gpu_mem_bw = _raw_float(self.offer, "gpu_mem_bw", "gpu_mem_bandwidth")
        compute = self.offer.compute_cap / 100 if self.offer.compute_cap else None

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(t.SPACE_4)
        grid.setVerticalSpacing(t.SPACE_3)

        gpu_hint_parts = []
        if self.offer.cuda_max_good:
            gpu_hint_parts.append(f"CUDA {_fmt_num(self.offer.cuda_max_good, decimals=1)}")
        if compute:
            gpu_hint_parts.append(f"CC {_fmt_num(compute, decimals=1)}")
        if self.offer.gpu_arch:
            gpu_hint_parts.append(_text(self.offer.gpu_arch))

        vram_hint_parts = [f"{_fmt_num(self.offer.gpu_ram_gb, 'GB')} per GPU"]
        if gpu_mem_bw:
            vram_hint_parts.append(f"{_fmt_num(gpu_mem_bw, 'GB/s')}")

        bus_hint_parts = []
        if pcie_bw:
            bus_hint_parts.append(f"{_fmt_num(pcie_bw, 'GB/s')}")
        if pci_gen:
            bus_hint_parts.append(f"PCIe {_fmt_num(pci_gen, decimals=1)}")

        duration = _fmt_num(self.offer.duration_days, "days", 1)
        if duration == "0 days":
            duration = "-"

        blocks = [
            _InfoBlock("GPU compute", _fmt_num(total_flops, "TFLOPS"), "  ".join(gpu_hint_parts)),
            _InfoBlock("VRAM", _fmt_num(self.offer.gpu_total_ram_gb, "GB"), "  ".join(vram_hint_parts)),
            _InfoBlock("PCIe / bus", "  ".join(bus_hint_parts) or "-", f"{_fmt_num(self.offer.flops_per_dphtotal, 'FLOPS/$')}"),
            _InfoBlock(
                "CPU",
                _text(self.offer.cpu_name, "Unknown CPU"),
                f"{_fmt_num(self.offer.cpu_cores, 'cores')}  {_fmt_num(self.offer.cpu_ram_gb, 'GB RAM')}",
            ),
            _InfoBlock(
                "Disk",
                _fmt_num(self.offer.disk_space_gb, "GB"),
                f"{_fmt_num(self.offer.disk_bw_mbps, 'MB/s')}",
            ),
            _InfoBlock(
                "Network",
                f"{_fmt_num(self.offer.inet_down_mbps, 'Mbps')} down",
                f"{_fmt_num(self.offer.inet_up_mbps, 'Mbps')} up  {_fmt_num(self.offer.direct_port_count, 'ports')}",
            ),
            _InfoBlock(
                "Performance",
                _fmt_num(self.offer.dlperf, "DLPerf"),
                f"{_fmt_num(self.offer.dlperf_per_dphtotal, 'DLPerf/$')}",
            ),
            _InfoBlock(
                "Reliability",
                _fmt_percent(self.offer.reliability),
                f"Max duration {duration}",
            ),
            _InfoBlock(
                "Host",
                _text(self.offer.datacenter or self.offer.hosting_type, "consumer"),
                _fmt_bool(self.offer.static_ip, "Static IP", "No static IP"),
            ),
        ]

        for index, block in enumerate(blocks):
            row = index // 5
            col = index % 5
            grid.addWidget(block, row, col)
            grid.setColumnStretch(col, 1)

        grid.addWidget(self._actions_widget(), 1, 4, Qt.AlignRight | Qt.AlignBottom)
        grid.setColumnStretch(4, 1)
        self.body().addLayout(grid)

    def _actions_widget(self) -> QWidget:
        wrap = QWidget()
        root = QVBoxLayout(wrap)
        root.setContentsMargins(0, t.SPACE_5, 0, 0)
        root.setSpacing(0)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(t.SPACE_2)

        details_btn = QPushButton("Details")
        details_btn.setProperty("variant", "ghost")
        details_btn.setMinimumWidth(90)
        details_btn.clicked.connect(lambda: self.details_clicked.emit(self.offer))

        self.rent_btn = QPushButton("Rent")
        self.rent_btn.setMinimumWidth(128)
        self.rent_btn.clicked.connect(lambda: self.rent_clicked.emit(self.offer))

        actions.addWidget(details_btn)
        actions.addWidget(self.rent_btn)
        root.addLayout(actions)
        return wrap
