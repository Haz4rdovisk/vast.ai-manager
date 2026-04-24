"""Reusable editor for llama-server parameters."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QLabel,
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

        self.ctx_spin = self._spin(root, "Context length", 128, 262144, 4096, 1024)
        self.ngl_spin = self._spin(root, "GPU layers", 0, 999, 99, 1)
        self.threads_spin = self._spin(root, "Threads (0=auto)", 0, 128, 0, 1)
        self.batch_spin = self._spin(root, "Batch size", 32, 4096, 512, 32)
        self.parallel_spin = self._spin(root, "Parallel requests", 1, 16, 1, 1)

        root.addWidget(QLabel("Repeat penalty"))
        self.repeat_spin = QDoubleSpinBox()
        self.repeat_spin.setRange(0.0, 3.0)
        self.repeat_spin.setSingleStep(0.05)
        self.repeat_spin.setValue(1.10)
        self.repeat_spin.valueChanged.connect(self._emit)
        root.addWidget(self.repeat_spin)

        root.addWidget(QLabel("KV cache type"))
        self.kv_combo = QComboBox()
        self.kv_combo.addItems(["bf16", "f16", "q8_0", "q4_0"])
        self.kv_combo.currentIndexChanged.connect(self._emit)
        root.addWidget(self.kv_combo)

        self.fa_chk = QCheckBox("Flash attention")
        self.fa_chk.setChecked(True)
        self.fa_chk.stateChanged.connect(self._emit)
        root.addWidget(self.fa_chk)

        root.addWidget(QLabel("Host"))
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.textChanged.connect(self._emit)
        root.addWidget(self.host_edit)

        self.port_spin = self._spin(root, "Port", 1024, 65535, 11434, 1)

        root.addWidget(QLabel("Extra args"))
        self.extra_edit = QLineEdit()
        self.extra_edit.textChanged.connect(self._emit)
        root.addWidget(self.extra_edit)

    def _spin(self, root, label: str, minimum: int, maximum: int, default: int, step: int):
        root.addWidget(QLabel(label))
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(default)
        spin.setSingleStep(step)
        spin.valueChanged.connect(self._emit)
        root.addWidget(spin)
        return spin

    def set_params(self, params: ServerParams):
        self._params = params
        self._set_model_path(params.model_path)
        self.ctx_spin.setValue(params.context_length)
        self.ngl_spin.setValue(params.gpu_layers)
        self.threads_spin.setValue(params.threads)
        self.batch_spin.setValue(params.batch_size)
        self.parallel_spin.setValue(params.parallel_requests)
        self.repeat_spin.setValue(params.repeat_penalty)

        index = self.kv_combo.findText(params.kv_cache_type)
        if index >= 0:
            self.kv_combo.setCurrentIndex(index)
        self.fa_chk.setChecked(params.flash_attention)
        self.host_edit.setText(params.host)
        self.port_spin.setValue(params.port)
        self.extra_edit.setText(params.extra_args)

    def current_params(self) -> ServerParams:
        return ServerParams(
            model_path=self.model_combo.currentData() or "",
            context_length=self.ctx_spin.value(),
            gpu_layers=self.ngl_spin.value(),
            threads=self.threads_spin.value(),
            batch_size=self.batch_spin.value(),
            parallel_requests=self.parallel_spin.value(),
            repeat_penalty=self.repeat_spin.value(),
            host=self.host_edit.text().strip() or "127.0.0.1",
            port=self.port_spin.value(),
            flash_attention=self.fa_chk.isChecked(),
            kv_cache_type=self.kv_combo.currentText(),
            extra_args=self.extra_edit.text().strip(),
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
