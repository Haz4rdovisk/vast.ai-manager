from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from app.models import Instance
from app.theme import BORDER_LOW, FONT_DISPLAY, FONT_MONO, TEXT_HI, TEXT_LOW, TEXT_MID


def _fmt(value, suffix: str = "", default: str = "—") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _trunc(value: str | None, limit: int) -> str:
    text = value or "—"
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _Cell(QFrame):
    def __init__(self, label: str, value: str, sub: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._label = QLabel(label.upper())
        lf = self._label.font()
        lf.setFamily(FONT_DISPLAY)
        lf.setPointSize(7)
        self._label.setFont(lf)
        self._label.setStyleSheet(f"color: {TEXT_LOW}; letter-spacing: 1px;")

        self._value = QLabel(value)
        vf = self._value.font()
        vf.setFamily(FONT_MONO)
        vf.setPointSize(9)
        self._value.setFont(vf)
        self._value.setStyleSheet(f"color: {TEXT_HI};")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        lay.addWidget(self._label)
        lay.addWidget(self._value)

        if sub:
            sub_label = QLabel(sub)
            sf = sub_label.font()
            sf.setPointSize(8)
            sub_label.setFont(sf)
            sub_label.setStyleSheet(f"color: {TEXT_MID};")
            lay.addWidget(sub_label)

    def value_text(self) -> str:
        return self._value.text()


class SpecsGrid(QFrame):
    """Dense 7-column grid of instance hardware/performance data."""

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"SpecsGrid {{ border-top: 1px solid {BORDER_LOW}; padding-top: 10px; }}"
        )
        self._cells: dict[str, _Cell] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 10, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)

        cells = [
            ("instance", "Instance", _fmt(inst.id), f"Host {_fmt(inst.host_id)}"),
            ("cuda", "CUDA", _fmt(inst.cuda_max_good), f"{_fmt(inst.total_flops, ' TFLOPS')}"),
            ("dlperf", "DLPerf", _fmt(inst.dlperf), f"{_fmt(inst.flops_per_dphtotal, '/$/hr')}"),
            (
                "network",
                "Network",
                f"↓ {_fmt(inst.inet_down_mbps, ' Mbps')}",
                f"↑ {_fmt(inst.inet_up_mbps, ' Mbps')}",
            ),
            (
                "cpu",
                "CPU",
                _trunc(inst.cpu_name, 14),
                f"{_fmt(inst.cpu_cores, ' cores')} · {_fmt(inst.ram_used_gb)}/{_fmt(inst.ram_total_gb, ' GB')}",
            ),
            (
                "disk",
                "Disk",
                f"{_fmt(inst.disk_usage_gb)}/{_fmt(inst.disk_space_gb, ' GB')}",
                f"{_fmt(inst.disk_bw_mbps, ' MB/s')}",
            ),
            (
                "mobo",
                "Mobo",
                _trunc(inst.mobo_name, 14),
                f"PCIe {_fmt(inst.pcie_gen)} · {_fmt(inst.pcie_bw_gbps, ' GB/s')}",
            ),
        ]
        for col, (key, label, value, sub) in enumerate(cells):
            cell = _Cell(label, value, sub, self)
            self._cells[key] = cell
            grid.addWidget(cell, 0, col)
            grid.setColumnStretch(col, 1)

    def value_text(self, key: str) -> str:
        return self._cells[key].value_text() if key in self._cells else ""
