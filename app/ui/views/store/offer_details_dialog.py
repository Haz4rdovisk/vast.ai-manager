"""Read-only details dialog for Vast marketplace offers."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.models_rental import Offer
from app.ui.components.primitives import GlassCard


def _raw_float(offer: Offer, *names: str) -> float | None:
    for name in names:
        value = offer.raw.get(name)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _num(value: float | int | None, suffix: str = "", decimals: int = 1) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number.is_integer():
        text = f"{number:.0f}"
    else:
        text = f"{number:.{decimals}f}"
    return f"{text} {suffix}".strip()


def _money(value: float | None, unit: str = "hr") -> str:
    if value is None:
        return "-"
    digits = 3 if value < 1 else 2
    return f"${value:.{digits}f}/{unit}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _price_rows(offer: Offer) -> list[tuple[str, str]]:
    total_hour = max(float(offer.dph_total or 0), 0.0)
    storage_gb = (
        _raw_float(offer, "allocated_storage", "allocated_storage_gb", "disk_gb")
        or offer.disk_space_gb
        or 0.0
    )
    storage_month = max(float(offer.storage_cost or 0.0) * storage_gb, 0.0)
    storage_hour = storage_month / (30.0 * 24.0) if storage_month else 0.0
    gpu_hour = max(total_hour - storage_hour, 0.0)
    up = _raw_float(offer, "inet_up_cost")
    down = _raw_float(offer, "inet_down_cost")

    def tb(value: float | None) -> str:
        return "-" if value is None else f"${value * 1000:.3f}/TB"

    return [
        ("GPU", f"{_money(gpu_hour)}  {_money(gpu_hour * 24, 'day')}  {_money(gpu_hour * 24 * 30, 'mo')}"),
        ("Storage", f"{_money(storage_hour)}  {_money(storage_hour * 24, 'day')}  {_money(storage_hour * 24 * 30, 'mo')}"),
        ("Total", f"{_money(total_hour)}  {_money(total_hour * 24, 'day')}  {_money(total_hour * 24 * 30, 'mo')}"),
        ("Internet", f"Up {tb(up)}  Down {tb(down)}"),
    ]


class OfferDetailsDialog(QDialog):
    def __init__(self, offer: Offer, parent=None):
        super().__init__(parent)
        self.offer = offer
        self.setWindowTitle(f"Offer details #{offer.id}")
        self.setMinimumSize(760, 660)

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_5)
        root.setSpacing(t.SPACE_4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(t.SPACE_4)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(4)
        self.title_lbl = QLabel(f"{offer.num_gpus}x {_text(offer.gpu_name, 'Unknown GPU')}")
        self.title_lbl.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 26px; font-weight: 850;"
        )
        meta = QLabel(
            "    ".join(
                value
                for value in (
                    f"m:{offer.machine_id}",
                    f"host:{_text(offer.host_id)}",
                    _text(offer.country or offer.geolocation, ""),
                    _text(offer.hosting_type, ""),
                )
                if value
            )
        )
        meta.setStyleSheet(f"color: {t.TEXT}; font-size: 13px; font-weight: 750;")
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(meta)
        header.addLayout(title_box, 1)

        self.price_lbl = QLabel(_money(offer.effective_price()))
        self.price_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.price_lbl.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 28px; font-weight: 900;"
        )
        header.addWidget(self.price_lbl)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(t.SPACE_3)

        gpu_mem_bw = _raw_float(offer, "gpu_mem_bw", "gpu_mem_bandwidth")
        pcie_bw = _raw_float(offer, "pcie_bw", "pcie_bandwidth")
        pci_gen = _raw_float(offer, "pci_gen")
        total_flops = _raw_float(offer, "total_flops", "flops", "total_flops_tflops")
        compute = offer.compute_cap / 100 if offer.compute_cap else None

        content_lay.addWidget(
            self._section(
                "GPU",
                [
                    ("Model", f"{offer.num_gpus}x {_text(offer.gpu_name)}"),
                    ("Total compute", _num(total_flops, "TFLOPS")),
                    ("VRAM", f"{_num(offer.gpu_total_ram_gb, 'GB')} total / {_num(offer.gpu_ram_gb, 'GB')} per GPU"),
                    ("Memory bandwidth", _num(gpu_mem_bw, "GB/s")),
                    ("CUDA / compute cap", f"CUDA {_num(offer.cuda_max_good)} / CC {_num(compute)}"),
                    ("Arch", _text(offer.gpu_arch)),
                ],
            )
        )
        content_lay.addWidget(
            self._section(
                "Host",
                [
                    ("Machine", f"m:{offer.machine_id}"),
                    ("Host", f"host:{_text(offer.host_id)}"),
                    ("Location", _text(offer.geolocation or offer.country)),
                    ("Datacenter", _text(offer.datacenter)),
                    ("Hosting", _text(offer.hosting_type)),
                    ("Verified / rentable", f"{offer.verified} / {offer.rentable}"),
                ],
            )
        )
        content_lay.addWidget(
            self._section(
                "System",
                [
                    ("CPU", _text(offer.cpu_name)),
                    ("CPU cores", _num(offer.cpu_cores)),
                    ("CPU RAM", _num(offer.cpu_ram_gb, "GB")),
                    ("Disk", _num(offer.disk_space_gb, "GB")),
                    ("Disk bandwidth", _num(offer.disk_bw_mbps, "MB/s")),
                    ("PCIe", f"{_num(pcie_bw, 'GB/s')}  PCIe {_num(pci_gen)}"),
                ],
            )
        )
        content_lay.addWidget(
            self._section(
                "Network & Reliability",
                [
                    ("Down / up", f"{_num(offer.inet_down_mbps, 'Mbps')} down / {_num(offer.inet_up_mbps, 'Mbps')} up"),
                    ("Ports", _num(offer.direct_port_count)),
                    ("Static IP", "Yes" if offer.static_ip else "No"),
                    ("Reliability", _percent(offer.reliability)),
                    ("Max duration", _num(offer.duration_days, "days")),
                    ("DLPerf", f"{_num(offer.dlperf)} / {_num(offer.dlperf_per_dphtotal, 'DLPerf/$')}"),
                ],
            )
        )
        content_lay.addWidget(self._section("Price Breakdown", _price_rows(offer)))
        content_lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        close = QPushButton("Close")
        close.setProperty("variant", "ghost")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        root.addLayout(actions)

    def _section(self, title: str, rows: list[tuple[str, str]]) -> GlassCard:
        card = GlassCard()
        heading = QLabel(title)
        heading.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: 16px; font-weight: 850;"
        )
        card.body().addWidget(heading)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(t.SPACE_5)
        grid.setVerticalSpacing(t.SPACE_2)
        for index, (label, value) in enumerate(rows):
            row = index // 2
            col = (index % 2) * 2
            key = QLabel(label)
            is_total = label.lower() == "total"
            key_color = t.OK if is_total else t.TEXT
            value_color = t.OK if is_total else t.TEXT_HI
            key.setStyleSheet(f"color: {key_color}; font-size: 12px; font-weight: 800;")
            val = QLabel(value)
            val.setWordWrap(True)
            val.setStyleSheet(f"color: {value_color}; font-size: 14px; font-weight: 800;")
            grid.addWidget(key, row, col)
            grid.addWidget(val, row, col + 1)
            grid.setColumnStretch(col + 1, 1)
        card.body().addLayout(grid)
        return card
