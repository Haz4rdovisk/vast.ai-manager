"""Configure view \u2014 full parameter editor for llama-server."""
from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPlainTextEdit, QLineEdit, QScrollArea,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader
from app.lab.state.models import ServerParams
from app.lab.services.model_params import build_launch_command, params_summary


class ConfigureView(QWidget):
    launch_requested = Signal(object)   # ServerParams

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._params = ServerParams()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        root.addWidget(SectionHeader("PARAMETERS", "Configure llama-server"))

        # --- Model selector ---
        model_card = GlassCard()
        model_card.body().addWidget(QLabel("Model (GGUF path on instance):"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(400)
        self.model_combo.currentIndexChanged.connect(self._update_preview)
        model_card.body().addWidget(self.model_combo)
        root.addWidget(model_card)

        # --- Core parameters ---
        core_card = GlassCard()
        core_card.body().addWidget(SectionHeader("CORE", "Inference Settings"))
        grid = QVBoxLayout()
        grid.setSpacing(t.SPACE_3)

        # Context length
        ctx_row = QHBoxLayout()
        ctx_row.addWidget(QLabel("Context length:"))
        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(128, 131072)
        self.ctx_spin.setValue(4096)
        self.ctx_spin.setSingleStep(1024)
        self.ctx_spin.valueChanged.connect(self._update_preview)
        ctx_row.addWidget(self.ctx_spin)
        ctx_row.addStretch()
        grid.addLayout(ctx_row)

        # GPU layers
        ngl_row = QHBoxLayout()
        ngl_row.addWidget(QLabel("GPU layers (ngl):"))
        self.ngl_spin = QSpinBox()
        self.ngl_spin.setRange(0, 999)
        self.ngl_spin.setValue(99)
        self.ngl_spin.valueChanged.connect(self._update_preview)
        ngl_row.addWidget(self.ngl_spin)
        ngl_hint = QLabel("99 = offload all layers to GPU")
        ngl_hint.setProperty("role", "muted")
        ngl_row.addWidget(ngl_hint)
        ngl_row.addStretch()
        grid.addLayout(ngl_row)

        # Threads
        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("Threads:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, 128)
        self.threads_spin.setValue(0)
        self.threads_spin.setSpecialValueText("auto")
        self.threads_spin.valueChanged.connect(self._update_preview)
        thr_row.addWidget(self.threads_spin)
        thr_row.addStretch()
        grid.addLayout(thr_row)

        # Batch size
        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("Batch size:"))
        self.batch_combo = QComboBox()
        self.batch_combo.addItems(["128", "256", "512", "1024", "2048"])
        self.batch_combo.setCurrentText("512")
        self.batch_combo.currentTextChanged.connect(self._update_preview)
        batch_row.addWidget(self.batch_combo)
        batch_row.addStretch()
        grid.addLayout(batch_row)

        # Parallel requests
        np_row = QHBoxLayout()
        np_row.addWidget(QLabel("Parallel requests:"))
        self.np_spin = QSpinBox()
        self.np_spin.setRange(1, 16)
        self.np_spin.setValue(1)
        self.np_spin.valueChanged.connect(self._update_preview)
        np_row.addWidget(self.np_spin)
        np_row.addStretch()
        grid.addLayout(np_row)

        core_card.body().addLayout(grid)
        root.addWidget(core_card)

        # --- Advanced ---
        adv_card = GlassCard()
        adv_card.body().addWidget(SectionHeader("ADVANCED", "Fine-tuning"))
        adv = QVBoxLayout()
        adv.setSpacing(t.SPACE_3)

        # Repeat penalty
        rp_row = QHBoxLayout()
        rp_row.addWidget(QLabel("Repeat penalty:"))
        self.rp_spin = QDoubleSpinBox()
        self.rp_spin.setRange(0.0, 3.0)
        self.rp_spin.setSingleStep(0.05)
        self.rp_spin.setValue(1.10)
        self.rp_spin.valueChanged.connect(self._update_preview)
        rp_row.addWidget(self.rp_spin)
        rp_row.addStretch()
        adv.addLayout(rp_row)

        # Flash attention
        fa_row = QHBoxLayout()
        self.fa_check = QCheckBox("Flash attention")
        self.fa_check.setChecked(True)
        self.fa_check.stateChanged.connect(self._update_preview)
        fa_row.addWidget(self.fa_check)
        fa_row.addStretch()
        adv.addLayout(fa_row)

        # KV cache type
        kv_row = QHBoxLayout()
        kv_row.addWidget(QLabel("KV cache type:"))
        self.kv_combo = QComboBox()
        self.kv_combo.addItems(["bf16", "f16", "q8_0", "q4_0"])
        self.kv_combo.setCurrentText("bf16")
        self.kv_combo.currentTextChanged.connect(self._update_preview)
        kv_row.addWidget(self.kv_combo)
        kv_row.addStretch()
        adv.addLayout(kv_row)

        # Host / Port
        hp_row = QHBoxLayout()
        hp_row.addWidget(QLabel("Host:"))
        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setFixedWidth(120)
        self.host_input.textChanged.connect(self._update_preview)
        hp_row.addWidget(self.host_input)
        hp_row.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(11434)
        self.port_spin.valueChanged.connect(self._update_preview)
        hp_row.addWidget(self.port_spin)
        hp_row.addStretch()
        adv.addLayout(hp_row)

        # Extra args
        extra_row = QHBoxLayout()
        extra_row.addWidget(QLabel("Extra args:"))
        self.extra_input = QLineEdit()
        self.extra_input.setPlaceholderText("e.g. --mlock --verbose")
        self.extra_input.textChanged.connect(self._update_preview)
        extra_row.addWidget(self.extra_input, 1)
        adv.addLayout(extra_row)

        adv_card.body().addLayout(adv)
        root.addWidget(adv_card)

        # --- Command preview ---
        prev_card = GlassCard()
        prev_card.body().addWidget(SectionHeader("PREVIEW", "Command that will run"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(140)
        font = self.preview.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        self.preview.setFont(font)
        prev_card.body().addWidget(self.preview)
        root.addWidget(prev_card)

        # Launch button
        launch_row = QHBoxLayout()
        launch_row.addStretch()
        self.summary_lbl = QLabel("")
        self.summary_lbl.setProperty("role", "muted")
        launch_row.addWidget(self.summary_lbl)
        self.launch_btn = QPushButton("\u25B6  Launch llama-server")
        self.launch_btn.setMinimumHeight(40)
        self.launch_btn.clicked.connect(self._launch)
        launch_row.addWidget(self.launch_btn)
        root.addLayout(launch_row)

        root.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.store.remote_gguf_changed.connect(self._refresh_models)
        self._update_preview()

    def select_model(self, path: str):
        """Pre-select a model for launch."""
        idx = self.model_combo.findData(path)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    def _refresh_models(self, files):
        self.model_combo.clear()
        for f in files:
            self.model_combo.addItem(f.filename, f.path)
        self.launch_btn.setEnabled(self.model_combo.count() > 0)

    def _gather_params(self) -> ServerParams:
        return ServerParams(
            model_path=self.model_combo.currentData() or "",
            context_length=self.ctx_spin.value(),
            gpu_layers=self.ngl_spin.value(),
            threads=self.threads_spin.value(),
            batch_size=int(self.batch_combo.currentText() or "512"),
            parallel_requests=self.np_spin.value(),
            repeat_penalty=self.rp_spin.value(),
            host=self.host_input.text().strip() or "127.0.0.1",
            port=self.port_spin.value(),
            flash_attention=self.fa_check.isChecked(),
            kv_cache_type=self.kv_combo.currentText(),
            extra_args=self.extra_input.text().strip(),
        )

    def _update_preview(self, *_):
        p = self._gather_params()
        binary = self.store.setup_status.llamacpp_path or "/opt/llama.cpp/build/bin/llama-server"
        cmd = build_launch_command(p, binary)
        self.preview.setPlainText(cmd)
        self.summary_lbl.setText(params_summary(p))

    def _launch(self):
        p = self._gather_params()
        if not p.model_path:
            return
        self.store.set_server_params(p)
        self.launch_requested.emit(p)
