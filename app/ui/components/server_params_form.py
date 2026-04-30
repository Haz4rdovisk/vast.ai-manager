"""Reusable editor for llama-server parameters."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.lab.state.models import ServerParams


class ServerParamsForm(QWidget):
    changed = Signal(object)

    def __init__(self, model_paths: list[str], parent=None):
        super().__init__(parent)
        self._params = ServerParams()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_3)

        self.model_label = QLabel("Model")
        root.addWidget(self.model_label)
        self.model_combo = QComboBox()
        for path in model_paths:
            self.model_combo.addItem(path.rsplit("/", 1)[-1], path)
        self.model_combo.currentIndexChanged.connect(self._emit)
        root.addWidget(self.model_combo)

        self._core_grid = QGridLayout()
        self._core_grid.setContentsMargins(0, 0, 0, 0)
        self._core_grid.setHorizontalSpacing(t.SPACE_4)
        self._core_grid.setVerticalSpacing(t.SPACE_4)
        self._core_grid.setColumnStretch(0, 1)
        self._core_grid.setColumnStretch(1, 1)

        self._secondary_grid = QGridLayout()
        self._secondary_grid.setContentsMargins(0, 0, 0, 0)
        self._secondary_grid.setHorizontalSpacing(t.SPACE_4)
        self._secondary_grid.setVerticalSpacing(t.SPACE_4)
        self._secondary_grid.setColumnStretch(0, 1)
        self._secondary_grid.setColumnStretch(1, 1)

        self._sampling_grid = QGridLayout()
        self._sampling_grid.setContentsMargins(0, 0, 0, 0)
        self._sampling_grid.setHorizontalSpacing(t.SPACE_4)
        self._sampling_grid.setVerticalSpacing(t.SPACE_4)
        self._sampling_grid.setColumnStretch(0, 1)
        self._sampling_grid.setColumnStretch(1, 1)

        self._toggle_grid = QGridLayout()
        self._toggle_grid.setContentsMargins(0, 0, 0, 0)
        self._toggle_grid.setHorizontalSpacing(t.SPACE_4)
        self._toggle_grid.setVerticalSpacing(t.SPACE_4)
        self._toggle_grid.setColumnStretch(0, 1)
        self._toggle_grid.setColumnStretch(1, 1)

        self.ctx_spin = self._spin(128, 262144, 4096, 1024)
        self.ngl_spin = self._spin(0, 999, 99, 1)
        self.threads_spin = self._spin(0, 128, 0, 1)
        self.threads_spin.setSpecialValueText("auto")
        self.threads_batch_spin = self._spin(0, 128, 0, 1)
        self.threads_batch_spin.setSpecialValueText("auto")
        self.batch_spin = self._spin(32, 4096, 512, 32)
        self.ubatch_spin = self._spin(32, 16384, 512, 32)
        self.parallel_spin = self._spin(1, 16, 1, 1)
        self.max_tokens_spin = self._spin(-1, 1048576, -1, 128)
        self.max_tokens_spin.setSpecialValueText("infinite")

        self.temperature_spin = self._float_spin(0.0, 5.0, 0.80, 0.05)
        self.repeat_spin = self._float_spin(0.0, 3.0, 1.10, 0.05)
        self.dynatemp_range_spin = self._float_spin(0.0, 5.0, 0.00, 0.05)
        self.dynatemp_exp_spin = self._float_spin(0.0, 5.0, 1.00, 0.05)
        self.top_p_spin = self._float_spin(0.0, 1.0, 0.95, 0.01)
        self.min_p_spin = self._float_spin(0.0, 1.0, 0.05, 0.01)
        self.xtc_probability_spin = self._float_spin(0.0, 1.0, 0.00, 0.01)
        self.xtc_threshold_spin = self._float_spin(0.0, 1.0, 0.10, 0.01)
        self.typical_p_spin = self._float_spin(0.0, 1.0, 1.00, 0.01)
        self.top_k_spin = self._spin(0, 1000, 40, 1)

        self.kv_combo = QComboBox()
        self.kv_combo.addItems(["bf16", "f16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1", "f32"])
        self.kv_combo.currentIndexChanged.connect(self._emit)

        self.samplers_edit = QLineEdit(ServerParams().samplers)
        self.samplers_edit.setPlaceholderText("penalties;dry;top_n_sigma;top_k;typ_p;top_p;min_p;xtc;temperature")
        self.samplers_edit.textChanged.connect(self._emit)

        self.fa_chk = QCheckBox("Enable")
        self.fa_chk.setChecked(True)
        self.fa_chk.stateChanged.connect(self._emit)

        self.cont_batching_chk = QCheckBox("Enable")
        self.cont_batching_chk.setChecked(True)
        self.cont_batching_chk.stateChanged.connect(self._emit)

        self.mlock_chk = QCheckBox("Enable")
        self.mlock_chk.stateChanged.connect(self._emit)

        self.mmap_chk = QCheckBox("Enable")
        self.mmap_chk.setChecked(True)
        self.mmap_chk.stateChanged.connect(self._emit)

        self.context_shift_chk = QCheckBox("Enable")
        self.context_shift_chk.stateChanged.connect(self._emit)

        self.no_warmup_chk = QCheckBox("Skip warmup")
        self.no_warmup_chk.setChecked(True)
        self.no_warmup_chk.stateChanged.connect(self._emit)

        self.backend_sampling_chk = QCheckBox("Enable")
        self.backend_sampling_chk.stateChanged.connect(self._emit)

        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.textChanged.connect(self._emit)
        self.port_spin = self._spin(1024, 65535, 11434, 1)

        self.ctx_field = self._field("Context length", self.ctx_spin)
        self.ngl_field = self._field("GPU layers", self.ngl_spin)
        self.threads_field = self._field("Threads (0=auto)", self.threads_spin)
        self.batch_field = self._field("Batch size", self.batch_spin)
        self.parallel_field = self._field("Parallel requests", self.parallel_spin)
        self.ubatch_field = self._field("uBatch size", self.ubatch_spin)
        self.threads_batch_field = self._field("Batch threads (0=auto)", self.threads_batch_spin)
        self.kv_field = self._field("KV cache type", self.kv_combo)
        self.host_field = self._field("Host", self.host_edit)
        self.port_field = self._field("Port", self.port_spin)
        self.temperature_field = self._field("Temperature", self.temperature_spin)
        self.top_k_field = self._field("Top K", self.top_k_spin)
        self.top_p_field = self._field("Top P", self.top_p_spin)
        self.min_p_field = self._field("Min P", self.min_p_spin)
        self.repeat_field = self._field("Repeat penalty", self.repeat_spin)
        self.max_tokens_field = self._field("Max tokens", self.max_tokens_spin)
        self.dynatemp_range_field = self._field("Dynamic temp range", self.dynatemp_range_spin)
        self.dynatemp_exp_field = self._field("Dynamic temp exponent", self.dynatemp_exp_spin)
        self.xtc_probability_field = self._field("XTC probability", self.xtc_probability_spin)
        self.xtc_threshold_field = self._field("XTC threshold", self.xtc_threshold_spin)
        self.typical_p_field = self._field("Typical P", self.typical_p_spin)
        self.samplers_field = self._field("Samplers", self.samplers_edit)
        self.fa_field = self._toggle_field("Flash attention", self.fa_chk)
        self.cont_batching_field = self._toggle_field("Continuous batching", self.cont_batching_chk)
        self.mlock_field = self._toggle_field("Lock model in RAM", self.mlock_chk)
        self.mmap_field = self._toggle_field("Memory map model", self.mmap_chk)
        self.context_shift_field = self._toggle_field("Context shift", self.context_shift_chk)
        self.no_warmup_field = self._toggle_field("Warmup", self.no_warmup_chk)
        self.backend_sampling_field = self._toggle_field("Backend sampling", self.backend_sampling_chk)

        self._core_grid.addWidget(self.ctx_field, 0, 0)
        self._core_grid.addWidget(self.ngl_field, 0, 1)
        self._core_grid.addWidget(self.threads_field, 1, 0)
        self._core_grid.addWidget(self.batch_field, 1, 1)

        root.addLayout(self._core_grid)
        self._secondary_grid.addWidget(self.parallel_field, 0, 0)
        self._secondary_grid.addWidget(self.ubatch_field, 0, 1)
        self._secondary_grid.addWidget(self.threads_batch_field, 1, 0)
        self._secondary_grid.addWidget(self.kv_field, 1, 1)
        self._secondary_grid.addWidget(self.port_field, 2, 0)
        self._secondary_grid.addWidget(self.host_field, 2, 1)
        root.addLayout(self._secondary_grid)

        self._toggle_grid.addWidget(self.fa_field, 0, 0)
        self._toggle_grid.addWidget(self.cont_batching_field, 0, 1)
        self._toggle_grid.addWidget(self.mlock_field, 1, 0)
        self._toggle_grid.addWidget(self.mmap_field, 1, 1)
        self._toggle_grid.addWidget(self.context_shift_field, 2, 0)
        self._toggle_grid.addWidget(self.no_warmup_field, 2, 1)
        root.addLayout(self._toggle_grid)

        self._sampling_grid.addWidget(self.temperature_field, 0, 0)
        self._sampling_grid.addWidget(self.top_k_field, 0, 1)
        self._sampling_grid.addWidget(self.top_p_field, 1, 0)
        self._sampling_grid.addWidget(self.min_p_field, 1, 1)
        self._sampling_grid.addWidget(self.repeat_field, 2, 0)
        self._sampling_grid.addWidget(self.max_tokens_field, 2, 1)
        root.addLayout(self._sampling_grid)

        self.misc_sampling_toggle = QPushButton("Show Misc Sampling \u25BE")
        self.misc_sampling_toggle.setProperty("variant", "ghost")
        self.misc_sampling_toggle.clicked.connect(self._toggle_misc_sampling)
        root.addWidget(self.misc_sampling_toggle)

        self.misc_sampling_container = QWidget()
        self.misc_sampling_container.setVisible(False)
        misc_lay = QVBoxLayout(self.misc_sampling_container)
        misc_lay.setContentsMargins(0, 0, 0, 0)
        misc_lay.setSpacing(t.SPACE_3)

        self._misc_sampling_grid = QGridLayout()
        self._misc_sampling_grid.setContentsMargins(0, 0, 0, 0)
        self._misc_sampling_grid.setHorizontalSpacing(t.SPACE_4)
        self._misc_sampling_grid.setVerticalSpacing(t.SPACE_4)
        self._misc_sampling_grid.setColumnStretch(0, 1)
        self._misc_sampling_grid.setColumnStretch(1, 1)
        self._misc_sampling_grid.addWidget(self.dynatemp_range_field, 0, 0)
        self._misc_sampling_grid.addWidget(self.dynatemp_exp_field, 0, 1)
        self._misc_sampling_grid.addWidget(self.xtc_probability_field, 1, 0)
        self._misc_sampling_grid.addWidget(self.xtc_threshold_field, 1, 1)
        self._misc_sampling_grid.addWidget(self.typical_p_field, 2, 0)
        self._misc_sampling_grid.addWidget(self.backend_sampling_field, 2, 1)
        self._misc_sampling_grid.addWidget(self.samplers_field, 3, 0, 1, 2)
        misc_lay.addLayout(self._misc_sampling_grid)
        root.addWidget(self.misc_sampling_container)

        root.addWidget(QLabel("Extra args"))
        self.extra_edit = QLineEdit()
        self.extra_edit.textChanged.connect(self._emit)
        root.addWidget(self.extra_edit)

    def _spin(self, minimum: int, maximum: int, default: int, step: int):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(default)
        spin.setSingleStep(step)
        spin.valueChanged.connect(self._emit)
        return spin

    def _float_spin(self, minimum: float, maximum: float, default: float, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setValue(default)
        spin.setSingleStep(step)
        spin.valueChanged.connect(self._emit)
        return spin

    def _field(self, label: str, control: QWidget) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: {t.FONT_SIZE_LABEL}px; color: {t.TEXT};"
            f" font-weight: 500;"
        )
        lay.addWidget(lbl)
        lay.addWidget(control)
        return wrap

    def _toggle_field(self, label: str, control: QWidget) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: {t.FONT_SIZE_LABEL}px; color: {t.TEXT};"
            f" font-weight: 500;"
        )
        lay.addWidget(lbl)
        lay.addWidget(control)
        return wrap

    def _toggle_misc_sampling(self) -> None:
        visible = self.misc_sampling_container.isHidden()
        self.misc_sampling_container.setVisible(visible)
        self.misc_sampling_toggle.setText(
            "Hide Misc Sampling \u25B4" if visible else "Show Misc Sampling \u25BE"
        )

    def set_params(self, params: ServerParams):
        self._params = params
        self._set_model_path(params.model_path)
        self.ctx_spin.setValue(params.context_length)
        self.ngl_spin.setValue(params.gpu_layers)
        self.threads_spin.setValue(params.threads)
        self.threads_batch_spin.setValue(params.threads_batch)
        self.batch_spin.setValue(params.batch_size)
        self.ubatch_spin.setValue(params.ubatch_size)
        self.parallel_spin.setValue(params.parallel_requests)
        self.temperature_spin.setValue(params.temperature)
        self.dynatemp_range_spin.setValue(params.dynatemp_range)
        self.dynatemp_exp_spin.setValue(params.dynatemp_exp)
        self.top_k_spin.setValue(params.top_k)
        self.top_p_spin.setValue(params.top_p)
        self.min_p_spin.setValue(params.min_p)
        self.xtc_probability_spin.setValue(params.xtc_probability)
        self.xtc_threshold_spin.setValue(params.xtc_threshold)
        self.typical_p_spin.setValue(params.typical_p)
        self.repeat_spin.setValue(params.repeat_penalty)
        self.max_tokens_spin.setValue(params.max_tokens)

        index = self.kv_combo.findText(params.kv_cache_type)
        if index >= 0:
            self.kv_combo.setCurrentIndex(index)
        self.samplers_edit.setText(params.samplers)
        self.fa_chk.setChecked(params.flash_attention)
        self.cont_batching_chk.setChecked(params.continuous_batching)
        self.mlock_chk.setChecked(params.mlock)
        self.mmap_chk.setChecked(params.mmap)
        self.context_shift_chk.setChecked(params.context_shift)
        self.no_warmup_chk.setChecked(params.no_warmup)
        self.backend_sampling_chk.setChecked(params.backend_sampling)
        self.host_edit.setText(params.host)
        self.port_spin.setValue(params.port)
        self.extra_edit.setText(params.extra_args)

    def current_params(self) -> ServerParams:
        return ServerParams(
            model_path=self.model_combo.currentData() or "",
            context_length=self.ctx_spin.value(),
            gpu_layers=self.ngl_spin.value(),
            threads=self.threads_spin.value(),
            threads_batch=self.threads_batch_spin.value(),
            batch_size=self.batch_spin.value(),
            ubatch_size=self.ubatch_spin.value(),
            parallel_requests=self.parallel_spin.value(),
            temperature=self.temperature_spin.value(),
            dynatemp_range=self.dynatemp_range_spin.value(),
            dynatemp_exp=self.dynatemp_exp_spin.value(),
            top_k=self.top_k_spin.value(),
            top_p=self.top_p_spin.value(),
            min_p=self.min_p_spin.value(),
            xtc_probability=self.xtc_probability_spin.value(),
            xtc_threshold=self.xtc_threshold_spin.value(),
            typical_p=self.typical_p_spin.value(),
            repeat_penalty=self.repeat_spin.value(),
            max_tokens=self.max_tokens_spin.value(),
            samplers=self.samplers_edit.text().strip(),
            backend_sampling=self.backend_sampling_chk.isChecked(),
            host=self.host_edit.text().strip() or "127.0.0.1",
            port=self.port_spin.value(),
            flash_attention=self.fa_chk.isChecked(),
            continuous_batching=self.cont_batching_chk.isChecked(),
            context_shift=self.context_shift_chk.isChecked(),
            mlock=self.mlock_chk.isChecked(),
            mmap=self.mmap_chk.isChecked(),
            kv_cache_type=self.kv_combo.currentText(),
            extra_args=self.extra_edit.text().strip(),
            no_warmup=self.no_warmup_chk.isChecked(),
        )

    def set_model_paths(self, paths: list[str]):
        current = self.model_combo.currentData()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for path in paths:
            self.model_combo.addItem(path.rsplit("/", 1)[-1], path)
        if current:
            self._set_model_path(current)
        self.model_combo.blockSignals(False)

    def _set_model_path(self, path: str) -> None:
        if not path:
            return
        index = self.model_combo.findData(path)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

    def set_model_field_visible(self, visible: bool) -> None:
        self.model_label.setVisible(visible)
        self.model_combo.setVisible(visible)

    def _emit(self, *_):
        self.changed.emit(self.current_params())
