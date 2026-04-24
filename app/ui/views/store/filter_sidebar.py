"""Store filter sidebar — every Vast search_offers dimension exposed.
Emits OfferQuery via query_changed (debounced)."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit,
    QScrollArea, QSizePolicy, QToolButton,
)
from PySide6.QtCore import Signal, Qt, QTimer
from app import theme as t
from app.models_rental import OfferQuery, OfferType, OfferSort
from app.ui.components.primitives import GlassCard
from app.ui.views.store.constants import (
    POPULAR_GPUS, GPU_ARCHS, CPU_ARCHS, REGIONS, COUNTRIES,
    HOSTING_TYPES, PRESETS,
)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "section")
    return lbl


class CollapsibleSection(GlassCard):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        root = self.body()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_2)

        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toggle.setStyleSheet(
            f"QToolButton {{ color: {t.TEXT_MID}; background: transparent;"
            f" border: none; font-size: {t.FONT_SIZE_LABEL}px;"
            f" font-weight: 700; letter-spacing: 1.5px; text-align: left;"
            f" padding: 9px 14px 3px 14px; }}"
            f"QToolButton:hover {{ color: {t.TEXT_HI}; }}"
        )
        self.toggle.toggled.connect(self._set_expanded)
        root.addWidget(self.toggle)

        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(t.SPACE_4, 0, t.SPACE_4, t.SPACE_3)
        self.body_lay.setSpacing(t.SPACE_3)
        root.addWidget(self.body)
        self._set_expanded(True)

    def _set_expanded(self, expanded: bool):
        self.body.setVisible(expanded)
        self.toggle.setText(("- " if expanded else "+ ") + self._title)


def _section(parent_lay: QVBoxLayout, title: str) -> QVBoxLayout:
    section = CollapsibleSection(title)
    parent_lay.addWidget(section)
    return section.body_lay


def _row(key: str, widget: QWidget) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    k = QLabel(key)
    k.setProperty("role", "muted")
    k.setWordWrap(True)
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    lay.addWidget(k)
    lay.addWidget(widget)
    return w


class FilterSidebar(QFrame):
    query_changed = Signal(object)    # OfferQuery
    search_clicked = Signal()
    gpu_count_changed = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, t.SPACE_2, t.SPACE_4)
        lay.setSpacing(t.SPACE_3)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self._debounce = QTimer(self); self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._emit_query)

        # ── Preset ───────────────────────────────────────────────
        preset_lay = _section(lay, "Preset")
        self.preset_cb = QComboBox()
        self.preset_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preset_cb.addItem("Custom", None)
        for name in PRESETS:
            self.preset_cb.addItem(name, name)
        self.preset_cb.currentIndexChanged.connect(self._apply_preset)
        preset_lay.addWidget(self.preset_cb)

        self.type_cb = QComboBox()
        self.type_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, val in [("On-demand", OfferType.ON_DEMAND),
                           ("Interruptible (bid)", OfferType.INTERRUPTIBLE),
                           ("Reserved", OfferType.RESERVED)]:
            self.type_cb.addItem(label, val)
        self.type_cb.currentIndexChanged.connect(self._kick)

        self.sort_cb = QComboBox()
        self.sort_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, val in [
            ("Price (inc.)", OfferSort.DPH_ASC),
            ("Price (dec.)", OfferSort.DPH_DESC),
            ("Best score", OfferSort.SCORE_DESC),
            ("Best DLPerf", OfferSort.DLPERF_DESC),
            ("Best DLPerf / $", OfferSort.DLPERF_PER_DPH_DESC),
            ("Best FLOPS / $", OfferSort.FLOPS_PER_DPH_DESC),
            ("Most reliable", OfferSort.RELIABILITY_DESC),
            ("Fastest net", OfferSort.INET_DOWN_DESC),
            ("Most GPUs", OfferSort.NUM_GPUS_DESC),
            ("Largest VRAM", OfferSort.GPU_RAM_DESC),
            ("Longest uptime", OfferSort.DURATION_DESC),
        ]:
            self.sort_cb.addItem(label, val)
        self.sort_cb.currentIndexChanged.connect(self._kick)

        # ── GPU ──────────────────────────────────────────────────
        gpu_lay = _section(lay, "GPU")
        self.gpu_cb = QComboBox()
        self.gpu_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.gpu_cb.addItem("GPUs", "")
        for g in POPULAR_GPUS:
            self.gpu_cb.addItem(g, g)
        self.gpu_cb.currentIndexChanged.connect(self._kick)

        self.gpu_arch_cb = QComboBox()
        self.gpu_arch_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, val in GPU_ARCHS:
            self.gpu_arch_cb.addItem(label, val)
        self.gpu_arch_cb.currentIndexChanged.connect(self._kick)
        gpu_lay.addWidget(_row("Arch", self.gpu_arch_cb))

        self.min_gpus = QSpinBox(); self.min_gpus.setRange(0, 64); self.min_gpus.setValue(0)
        self.min_gpus.setSpecialValueText("Any min")
        self.min_gpus.valueChanged.connect(self._kick)
        self.max_gpus = QSpinBox(); self.max_gpus.setRange(0, 64); self.max_gpus.setValue(0)
        self.max_gpus.setSpecialValueText("Any max")
        self.max_gpus.valueChanged.connect(self._kick)

        self.min_vram = QDoubleSpinBox(); self.min_vram.setRange(0, 1024)
        self.min_vram.setDecimals(0); self.min_vram.setSuffix(" GB")
        self.min_vram.valueChanged.connect(self._kick)
        gpu_lay.addWidget(_row("Min VRAM / GPU", self.min_vram))

        self.min_total_vram = QDoubleSpinBox(); self.min_total_vram.setRange(0, 4096)
        self.min_total_vram.setDecimals(0); self.min_total_vram.setSuffix(" GB")
        self.min_total_vram.valueChanged.connect(self._kick)
        gpu_lay.addWidget(_row("Min total VRAM", self.min_total_vram))

        self.min_cuda = QDoubleSpinBox(); self.min_cuda.setRange(0, 15); self.min_cuda.setDecimals(1)
        self.min_cuda.setSingleStep(0.1)
        self.min_cuda.valueChanged.connect(self._kick)
        gpu_lay.addWidget(_row("Min CUDA", self.min_cuda))

        self.min_cc = QSpinBox(); self.min_cc.setRange(0, 999); self.min_cc.setSingleStep(10)
        self.min_cc.valueChanged.connect(self._kick)
        gpu_lay.addWidget(_row("Min compute cap", self.min_cc))

        # ── Compute (CPU / RAM / Disk) ───────────────────────────
        compute_lay = _section(lay, "Compute")
        self.min_cores = QSpinBox(); self.min_cores.setRange(0, 256)
        self.min_cores.valueChanged.connect(self._kick)
        compute_lay.addWidget(_row("Min CPU cores", self.min_cores))

        self.min_cpu_ram = QDoubleSpinBox(); self.min_cpu_ram.setRange(0, 4096)
        self.min_cpu_ram.setDecimals(0); self.min_cpu_ram.setSuffix(" GB")
        self.min_cpu_ram.valueChanged.connect(self._kick)
        compute_lay.addWidget(_row("Min CPU RAM", self.min_cpu_ram))

        self.cpu_arch_cb = QComboBox()
        self.cpu_arch_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, val in CPU_ARCHS:
            self.cpu_arch_cb.addItem(label, val)
        self.cpu_arch_cb.currentIndexChanged.connect(self._kick)
        compute_lay.addWidget(_row("CPU arch", self.cpu_arch_cb))

        self.min_disk = QDoubleSpinBox(); self.min_disk.setRange(0, 100000)
        self.min_disk.setDecimals(0); self.min_disk.setSuffix(" GB")
        self.min_disk.valueChanged.connect(self._kick)
        compute_lay.addWidget(_row("Min disk", self.min_disk))

        self.min_disk_bw = QDoubleSpinBox(); self.min_disk_bw.setRange(0, 20000)
        self.min_disk_bw.setDecimals(0); self.min_disk_bw.setSuffix(" MB/s")
        self.min_disk_bw.valueChanged.connect(self._kick)
        compute_lay.addWidget(_row("Min disk BW", self.min_disk_bw))

        # ── Network ──────────────────────────────────────────────
        network_lay = _section(lay, "Network")
        self.min_inet_down = QDoubleSpinBox(); self.min_inet_down.setRange(0, 100000)
        self.min_inet_down.setDecimals(0); self.min_inet_down.setSuffix(" Mbps")
        self.min_inet_down.valueChanged.connect(self._kick)
        network_lay.addWidget(_row("Min down", self.min_inet_down))

        self.min_inet_up = QDoubleSpinBox(); self.min_inet_up.setRange(0, 100000)
        self.min_inet_up.setDecimals(0); self.min_inet_up.setSuffix(" Mbps")
        self.min_inet_up.valueChanged.connect(self._kick)
        network_lay.addWidget(_row("Min up", self.min_inet_up))

        self.min_ports = QSpinBox(); self.min_ports.setRange(0, 200)
        self.min_ports.valueChanged.connect(self._kick)
        network_lay.addWidget(_row("Min open ports", self.min_ports))

        self.static_ip = QCheckBox("Static IP required")
        self.static_ip.stateChanged.connect(self._kick)
        network_lay.addWidget(self.static_ip)

        # ── Pricing ──────────────────────────────────────────────
        pricing_lay = _section(lay, "Pricing")
        self.max_dph = QDoubleSpinBox(); self.max_dph.setRange(0, 50); self.max_dph.setDecimals(2)
        self.max_dph.setSingleStep(0.05); self.max_dph.setSuffix(" $/h")
        self.max_dph.valueChanged.connect(self._kick)
        pricing_lay.addWidget(_row("Max price", self.max_dph))

        self.max_bid = QDoubleSpinBox(); self.max_bid.setRange(0, 50); self.max_bid.setDecimals(2)
        self.max_bid.setSingleStep(0.05); self.max_bid.setSuffix(" $/h")
        self.max_bid.valueChanged.connect(self._kick)
        pricing_lay.addWidget(_row("Max bid", self.max_bid))

        self.max_storage = QDoubleSpinBox(); self.max_storage.setRange(0, 10); self.max_storage.setDecimals(3)
        self.max_storage.setSingleStep(0.01); self.max_storage.setSuffix(" $/GB·mo")
        self.max_storage.valueChanged.connect(self._kick)
        pricing_lay.addWidget(_row("Max storage cost", self.max_storage))

        # ── Reliability & Location ───────────────────────────────
        location_lay = _section(lay, "Reliability & Location")
        self.min_rel = QDoubleSpinBox(); self.min_rel.setRange(0, 1); self.min_rel.setDecimals(3)
        self.min_rel.setSingleStep(0.005)
        self.min_rel.setSpecialValueText("Any")
        self.min_rel.setValue(0)
        self.min_rel.valueChanged.connect(self._kick)
        location_lay.addWidget(_row("Min reliability", self.min_rel))

        self.min_duration = QDoubleSpinBox(); self.min_duration.setRange(0, 365)
        self.min_duration.setDecimals(1); self.min_duration.setSuffix(" days")
        self.min_duration.valueChanged.connect(self._kick)
        location_lay.addWidget(_row("Min uptime duration", self.min_duration))

        self.region_cb = QComboBox()
        self.region_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, val in REGIONS:
            self.region_cb.addItem(label, val)
        self.region_cb.currentIndexChanged.connect(self._kick)

        self.country_cb = QComboBox()
        self.country_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, val in COUNTRIES:
            self.country_cb.addItem(label, val)
        self.country_cb.currentIndexChanged.connect(self._kick)
        location_lay.addWidget(_row("Country", self.country_cb))

        self.hosting_cb = QComboBox()
        self.hosting_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, val in HOSTING_TYPES:
            self.hosting_cb.addItem(label, val)
        self.hosting_cb.currentIndexChanged.connect(self._kick)
        location_lay.addWidget(_row("Hosting", self.hosting_cb))

        self.datacenter_only = QCheckBox("Datacenter only")
        self.datacenter_only.stateChanged.connect(self._kick)
        location_lay.addWidget(self.datacenter_only)

        self.verified = QCheckBox("Verified machines only"); self.verified.setChecked(True)
        self.verified.stateChanged.connect(self._kick)
        location_lay.addWidget(self.verified)

        self.external_ok = QCheckBox("Include external marketplace")
        self.external_ok.stateChanged.connect(self._kick)
        location_lay.addWidget(self.external_ok)

        # ── Action button ────────────────────────────────────────
        action_lay = _section(lay, "Search")
        search_btn = QPushButton("Search offers")
        search_btn.clicked.connect(self.search_clicked.emit)
        action_lay.addWidget(search_btn)

        reset_btn = QPushButton("Reset filters"); reset_btn.setProperty("variant", "ghost")
        reset_btn.clicked.connect(self.reset)
        action_lay.addWidget(reset_btn)

        lay.addStretch()

    # ─── API ─────────────────────────────────────────────────────
    def _kick(self, *_):
        self._debounce.start()

    def _emit_query(self):
        self.query_changed.emit(self.build_query())

    def build_query(self) -> OfferQuery:
        def opt_float(sp: QDoubleSpinBox) -> float | None:
            return float(sp.value()) if sp.value() > 0 else None
        def opt_int(sp: QSpinBox) -> int | None:
            return int(sp.value()) if sp.value() > 0 else None

        gpu = self.gpu_cb.currentData()
        gpu_list = [gpu] if gpu else []

        return OfferQuery(
            offer_type=self.type_cb.currentData(),
            sort=self.sort_cb.currentData(),
            gpu_names=gpu_list,
            gpu_arch=self.gpu_arch_cb.currentData() or None,
            min_num_gpus=opt_int(self.min_gpus),
            max_num_gpus=opt_int(self.max_gpus),
            min_gpu_ram_gb=opt_float(self.min_vram),
            min_gpu_total_ram_gb=opt_float(self.min_total_vram),
            min_cuda=opt_float(self.min_cuda),
            min_compute_cap=opt_int(self.min_cc),
            min_cpu_cores=opt_int(self.min_cores),
            min_cpu_ram_gb=opt_float(self.min_cpu_ram),
            cpu_arch=self.cpu_arch_cb.currentData() or None,
            min_disk_space_gb=opt_float(self.min_disk),
            min_disk_bw_mbps=opt_float(self.min_disk_bw),
            min_inet_down_mbps=opt_float(self.min_inet_down),
            min_inet_up_mbps=opt_float(self.min_inet_up),
            min_direct_port_count=opt_int(self.min_ports),
            static_ip=self.static_ip.isChecked() or None,
            max_dph=opt_float(self.max_dph),
            max_bid=opt_float(self.max_bid),
            max_storage_cost_per_gb_month=opt_float(self.max_storage),
            min_reliability=float(self.min_rel.value()) if self.min_rel.value() > 0 else None,
            min_duration_days=opt_float(self.min_duration),
            region=self.region_cb.currentData() or None,
            country=self.country_cb.currentData() or None,
            hosting_type=self.hosting_cb.currentData() or None,
            datacenter_only=self.datacenter_only.isChecked(),
            verified=True if self.verified.isChecked() else None,
            external=None if self.external_ok.isChecked() else False,
        )

    def set_gpu_count_filter(self, min_count: object, max_count: object) -> None:
        self.min_gpus.blockSignals(True)
        self.max_gpus.blockSignals(True)
        try:
            self.min_gpus.setValue(int(min_count or 0))
            self.max_gpus.setValue(int(max_count or 0))
        finally:
            self.min_gpus.blockSignals(False)
            self.max_gpus.blockSignals(False)
        self.gpu_count_changed.emit(min_count, max_count)
        self._kick()

    def _apply_preset(self, idx: int):
        name = self.preset_cb.itemData(idx)
        if not name: return
        p = PRESETS.get(name)
        if not p: return
        self.reset(emit=False)
        # Apply preset fields onto controls
        if p.gpu_names:
            g = p.gpu_names[0]
            i = self.gpu_cb.findData(g)
            if i >= 0: self.gpu_cb.setCurrentIndex(i)
        if p.min_num_gpus: self.min_gpus.setValue(int(p.min_num_gpus))
        self.gpu_count_changed.emit(self.min_gpus.value() or None, self.max_gpus.value() or None)
        if p.min_gpu_ram_gb: self.min_vram.setValue(float(p.min_gpu_ram_gb))
        if p.min_cpu_ram_gb: self.min_cpu_ram.setValue(float(p.min_cpu_ram_gb))
        if p.min_disk_space_gb: self.min_disk.setValue(float(p.min_disk_space_gb))
        if p.min_inet_down_mbps: self.min_inet_down.setValue(float(p.min_inet_down_mbps))
        if p.max_dph is not None: self.max_dph.setValue(float(p.max_dph))
        if p.min_reliability is not None: self.min_rel.setValue(float(p.min_reliability))
        if p.datacenter_only: self.datacenter_only.setChecked(True)
        self._kick()

    def reset(self, *, emit: bool = True):
        self.gpu_cb.setCurrentIndex(0); self.gpu_arch_cb.setCurrentIndex(0)
        self.min_gpus.setValue(0); self.max_gpus.setValue(0)
        for w in (self.min_vram, self.min_total_vram, self.min_cuda,
                  self.min_cores, self.min_cpu_ram, self.min_disk, self.min_disk_bw,
                  self.min_inet_down, self.min_inet_up,
                  self.max_dph, self.max_bid, self.max_storage,
                  self.min_duration):
            w.setValue(0)
        self.min_cc.setValue(0); self.min_ports.setValue(0)
        self.min_rel.setValue(0)
        self.cpu_arch_cb.setCurrentIndex(0)
        self.region_cb.setCurrentIndex(0); self.country_cb.setCurrentIndex(0)
        self.hosting_cb.setCurrentIndex(0)
        self.datacenter_only.setChecked(False); self.static_ip.setChecked(False)
        self.verified.setChecked(True); self.external_ok.setChecked(False)
        self.type_cb.setCurrentIndex(0); self.sort_cb.setCurrentIndex(0)
        self.gpu_count_changed.emit(None, None)
        if emit: self._kick()
