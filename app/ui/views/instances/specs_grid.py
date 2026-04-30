from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout

from app.models import Instance
from app.theme import BORDER_LOW, FONT_DISPLAY, FONT_MONO, TEXT_HI, TEXT_LOW, TEXT_MID


def _fmt(value, suffix: str = "", default: str = "—") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


class _Cell(QFrame):
    def __init__(self, label: str, value: str, sub: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(4)

        self._lbl_title = QLabel(label.upper())
        lf = self._lbl_title.font()
        lf.setFamily(FONT_DISPLAY)
        lf.setPointSize(7)
        self._lbl_title.setFont(lf)
        self._lbl_title.setStyleSheet(f"color: {TEXT_LOW}; letter-spacing: 1px;")

        self._lbl_value = QLabel(value)
        vf = self._lbl_value.font()
        vf.setFamily(FONT_MONO)
        vf.setPointSize(9)
        self._lbl_value.setFont(vf)
        self._lbl_value.setWordWrap(True)
        self._lbl_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._lbl_value.setStyleSheet(f"color: {TEXT_HI};")
        self._lbl_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._lbl_sub = QLabel(sub)
        sf = self._lbl_sub.font()
        sf.setPointSize(8)
        self._lbl_sub.setFont(sf)
        self._lbl_sub.setWordWrap(True)
        self._lbl_sub.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._lbl_sub.setStyleSheet(f"color: {TEXT_MID};")

        lay.addWidget(self._lbl_title)
        lay.addWidget(self._lbl_value)
        lay.addWidget(self._lbl_sub)

    def set_values(self, value: str, sub: str):
        self._lbl_value.setText(value)
        self._lbl_sub.setText(sub)

    def value_text(self) -> str:
        return self._lbl_value.text()


class SpecsGrid(QFrame):
    """Deeply spaced 7-column grid for professional dashboards."""

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self._cells: dict[str, _Cell] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 8, 0, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.grid = grid
        
        self.update_instance(inst)

    def update_instance(self, inst: Instance):
        data = self._get_data(inst)
        if not self._cells:
            for col, (key, label, value, sub) in enumerate(data):
                cell = _Cell(label, value, sub, self)
                self._cells[key] = cell
                self.grid.addWidget(cell, 0, col)
                self.grid.setColumnStretch(col, self._column_stretch(key))
        else:
            for key, label, value, sub in data:
                if key in self._cells:
                    self._cells[key].set_values(value, sub)

    @staticmethod
    def _column_stretch(key: str) -> int:
        return {
            "instance": 2,
            "network": 2,
            "cpu": 3,
            "mobo": 3,
        }.get(key, 1)

    def _get_data(self, inst: Instance):
        return [
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
                _fmt(inst.cpu_name),
                f"{_fmt(inst.cpu_cores, ' cores')} \u00b7 {_fmt(inst.ram_total_gb, ' GB')}",
            ),
            (
                "disk",
                "Disk",
                f"{_fmt(inst.disk_space_gb, ' GB')}",
                f"{_fmt(inst.disk_bw_mbps, ' MB/s')}",
            ),
            (
                "mobo",
                "Mobo",
                _fmt(inst.mobo_name),
                f"PCIe {_fmt(inst.pcie_gen)} \u00b7 {_fmt(inst.pcie_bw_gbps, ' GB/s')}",
            ),
        ]

    def value_text(self, key: str) -> str:
        return self._cells[key].value_text() if key in self._cells else ""
