"""Configure view - full parameter editor for llama-server."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.lab.services.model_params import build_launch_command, params_summary
from app.lab.state.models import ServerParams
from app.ui.components.page_header import PageHeader
from app.ui.components.primitives import GlassCard, SectionHeader
from app.ui.components.server_params_form import ServerParamsForm


class ConfigureView(QWidget):
    launch_requested = Signal(object)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        root.addWidget(PageHeader(
            "Configure llama-server",
            "Tune inference parameters before launching the model server.",
        ))

        params_card = GlassCard()
        params_card.body().addWidget(SectionHeader("CORE", "Inference Settings"))
        self.params_form = ServerParamsForm([])
        self.params_form.changed.connect(self._on_form_changed)
        params_card.body().addWidget(self.params_form)
        root.addWidget(params_card)

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
        params = self.params_form.current_params()
        params.model_path = path
        self.params_form.set_params(params)
        self._update_preview()

    def _refresh_models(self, files):
        paths = [f.path for f in files]
        self.params_form.set_model_paths(paths)
        self.launch_btn.setEnabled(bool(paths))
        self._update_preview()

    def _gather_params(self) -> ServerParams:
        return self.params_form.current_params()

    def _on_form_changed(self, params: ServerParams):
        self._update_preview(params)

    def _update_preview(self, params: ServerParams | None = None):
        current = params or self._gather_params()
        st = self.store.current_state
        binary = (
            (st.setup.llamacpp_path if st else "")
            or "/opt/llama.cpp/build/bin/llama-server"
        )
        cmd = build_launch_command(current, binary)
        self.preview.setPlainText(cmd)
        self.summary_lbl.setText(params_summary(current))

    def _launch(self):
        params = self._gather_params()
        if not params.model_path:
            return
        if self.store.selected_instance_id:
            self.store.set_server_params(self.store.selected_instance_id, params)
        self.launch_requested.emit(params)
