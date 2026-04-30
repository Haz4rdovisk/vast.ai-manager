"""Reusable model configuration form — glassmorphism polish."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPlainTextEdit, QLineEdit, QFrame,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.lab.state.models import ServerParams
from app.lab.services.model_params import build_launch_command, params_summary


class ModelConfigForm(QWidget):
    """A compact configuration form for a single model."""
    save_requested = Signal(object)  # ServerParams

    def __init__(self, model_path: str, store, initial_params: ServerParams = None,
                 target_iid: int | None = None, parent=None):
        super().__init__(parent)
        self._path = model_path
        self._store = store
        self._target_iid = target_iid
        self._params = initial_params or ServerParams(model_path=model_path)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, t.SPACE_3, 0, 0)
        lay.setSpacing(t.SPACE_4)

        # 1. Core controls
        grid_frame = QWidget()
        grid = QVBoxLayout(grid_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(t.SPACE_4)

        # Row 1: Context & GPU Layers
        r1 = QHBoxLayout()
        r1.setSpacing(t.SPACE_4)
        r1.addWidget(self._labeled_control(
            "Context Size:",
            self._init_spin(128, 131072, self._params.context_length, 1024, "ctx")
        ), 1)
        r1.addWidget(self._labeled_control(
            "GPU Layers:",
            self._init_spin(0, 999, self._params.gpu_layers, 1, "ngl")
        ), 1)
        grid.addLayout(r1)

        # Row 2: Threads & Batch
        r2 = QHBoxLayout()
        r2.setSpacing(t.SPACE_4)
        self.threads_spin = self._init_spin(0, 128, self._params.threads, 1, "threads")
        self.threads_spin.setSpecialValueText("auto")
        r2.addWidget(self._labeled_control("Threads:", self.threads_spin), 1)

        self.batch_combo = QComboBox()
        self.batch_combo.addItems(["128", "256", "512", "1024", "2048"])
        self.batch_combo.setCurrentText(str(self._params.batch_size))
        self.batch_combo.currentTextChanged.connect(self._update_preview)
        r2.addWidget(self._labeled_control("Batch Size:", self.batch_combo), 1)
        grid.addLayout(r2)

        # Row 3: Parallel & Flash Attention
        r3 = QHBoxLayout()
        r3.setSpacing(t.SPACE_4)
        r3.addWidget(self._labeled_control(
            "Parallel Req:",
            self._init_spin(1, 16, self._params.parallel_requests, 1, "np")
        ), 1)
        self.fa_check = QCheckBox("Flash Attention")
        self.fa_check.setChecked(self._params.flash_attention)
        self.fa_check.stateChanged.connect(self._update_preview)
        r3.addWidget(self._labeled_control("Acceleration:", self.fa_check), 1)
        grid.addLayout(r3)

        lay.addWidget(grid_frame)

        # 2. Advanced toggle
        self.adv_toggle = QPushButton("Show Advanced \u25BE")
        self.adv_toggle.setProperty("variant", "ghost")
        self.adv_toggle.setFixedWidth(168)
        self.adv_toggle.clicked.connect(self._toggle_advanced)
        lay.addWidget(self.adv_toggle)

        self.adv_container = QWidget()
        self.adv_container.setVisible(False)
        adv_lay = QVBoxLayout(self.adv_container)
        adv_lay.setContentsMargins(0, 0, 0, 0)
        adv_lay.setSpacing(t.SPACE_4)

        adv_frame = QWidget()
        adv_frame_lay = QVBoxLayout(adv_frame)
        adv_frame_lay.setContentsMargins(0, 0, 0, 0)
        adv_frame_lay.setSpacing(t.SPACE_4)

        extra_row = QHBoxLayout()
        extra_row.setSpacing(t.SPACE_3)
        extra_lbl = QLabel("Extra Args:")
        extra_lbl.setStyleSheet(
            f"font-size: {t.FONT_SIZE_LABEL}px; color: {t.TEXT_MID}; font-weight: 600;"
        )
        extra_row.addWidget(extra_lbl)
        self.extra_input = QLineEdit(self._params.extra_args)
        self.extra_input.setPlaceholderText("--mlock --verbose ...")
        self.extra_input.textChanged.connect(self._update_preview)
        extra_row.addWidget(self.extra_input, 1)
        adv_frame_lay.addLayout(extra_row)

        adv_r2 = QHBoxLayout()
        adv_r2.setSpacing(t.SPACE_4)
        self.kv_combo = QComboBox()
        self.kv_combo.addItems(["bf16", "f16", "q8_0", "q4_0"])
        self.kv_combo.setCurrentText(self._params.kv_cache_type)
        self.kv_combo.currentTextChanged.connect(self._update_preview)
        adv_r2.addWidget(self._labeled_control("KV Cache:", self.kv_combo), 1)

        self.rp_spin = QDoubleSpinBox()
        self.rp_spin.setRange(0.0, 3.0)
        self.rp_spin.setValue(self._params.repeat_penalty)
        self.rp_spin.setSingleStep(0.1)
        self.rp_spin.valueChanged.connect(self._update_preview)
        adv_r2.addWidget(self._labeled_control("Penalty:", self.rp_spin), 1)
        adv_frame_lay.addLayout(adv_r2)
        adv_lay.addWidget(adv_frame)
        lay.addWidget(self.adv_container)

        # 3. Preview
        preview_lbl = QLabel("Command Preview:")
        preview_lbl.setStyleSheet(
            f"font-size: {t.FONT_SIZE_LABEL}px; color: {t.TEXT_MID}; font-weight: 600;"
        )
        lay.addWidget(preview_lbl)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(92)
        self.preview.setMaximumHeight(108)
        self.preview.setStyleSheet(
            f"background: {t.BG_VOID}; color: {t.TEXT_HI};"
            f" font-family: {t.FONT_MONO}; font-size: {t.FONT_SIZE_MONO}px;"
            f" border: 1px solid {t.BORDER_LOW};"
            f" border-radius: {t.RADIUS_MD}px;"
            f" padding: 10px;"
        )
        lay.addWidget(self.preview)

        # 4. Summary / internal action row
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        self.summary_lbl = QLabel("")
        self.summary_lbl.setProperty("role", "muted")
        actions.addWidget(self.summary_lbl)
        actions.addStretch()

        self.save_btn = QPushButton("\u21E9  Save Config")
        self.save_btn.setProperty("variant", "ghost")
        self.save_btn.setMinimumHeight(36)
        self.save_btn.setFixedWidth(140)
        self.save_btn.clicked.connect(self._on_save)
        actions.addWidget(self.save_btn)
        lay.addLayout(actions)

        self._apply_visual_polish()
        self._update_preview()

    def _toggle_advanced(self):
        vis = not self.adv_container.isVisible()
        self.adv_container.setVisible(vis)
        self.adv_toggle.setText(
            "Hide Advanced \u25B4" if vis else "Show Advanced \u25BE"
        )

    def _init_spin(self, min_v, max_v, def_v, step, key) -> QSpinBox:
        s = QSpinBox()
        s.setRange(min_v, max_v)
        s.setValue(def_v)
        s.setSingleStep(step)
        s.valueChanged.connect(self._update_preview)
        setattr(self, f"{key}_spin", s)
        return s

    def _labeled_control(self, label, control) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(7)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: {t.FONT_SIZE_LABEL}px; color: {t.TEXT_LOW};"
            f" font-weight: 600;"
        )
        l.addWidget(lbl)
        l.addWidget(control)
        return w

    def _apply_visual_polish(self):
        form_shell = (
            f"background: rgba(255,255,255,0.02);"
            f"border: 1px solid {t.BORDER_LOW};"
            f"border-radius: {t.RADIUS_LG}px;"
        )
        self.adv_container.setStyleSheet(form_shell)
        self.adv_container.layout().setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)

        soft_row = (
            f"background: transparent;"
            f"border: none;"
        )
        for widget in self.findChildren(QWidget):
            if widget is self or widget is self.adv_container:
                continue
            name = widget.metaObject().className()
            if name in {"QLineEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox", "QPlainTextEdit"}:
                continue
            if name in {"QCheckBox", "QPushButton", "QLabel"}:
                continue
            if widget.layout() is not None and widget.parent() is self:
                continue
            if widget.layout() is not None:
                widget.setStyleSheet(soft_row)

    def gather_params(self) -> ServerParams:
        return ServerParams(
            model_path=self._path,
            context_length=self.ctx_spin.value(),
            gpu_layers=self.ngl_spin.value(),
            threads=self.threads_spin.value(),
            batch_size=int(self.batch_combo.currentText() or "512"),
            parallel_requests=self.np_spin.value(),
            repeat_penalty=self.rp_spin.value(),
            flash_attention=self.fa_check.isChecked(),
            kv_cache_type=self.kv_combo.currentText(),
            extra_args=self.extra_input.text().strip(),
            host="127.0.0.1",
            port=11434,
        )

    def _update_preview(self, *_):
        p = self.gather_params()
        iid = self._target_iid or self._store.selected_instance_id
        st = (
            self._store.get_state(iid)
            if iid else None
        )
        binary = (
            (st.setup.llamacpp_path if st else "")
            or "/opt/llama.cpp/build/bin/llama-server"
        )
        cmd = build_launch_command(p, binary)
        self.preview.setPlainText(cmd)
        self.summary_lbl.setText(params_summary(p))

    def _on_save(self):
        p = self.gather_params()
        self.save_requested.emit(p)
