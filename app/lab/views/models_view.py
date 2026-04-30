"""Global Model Library — GGUF manager across all connected instances."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QFrame, QSplitter, QComboBox, QGridLayout,
    QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Signal, Qt, QSize
from app import theme as t
from app.ui.components.page_header import PageHeader
from app.ui.components.lock_screen import LockScreen
import qtawesome as qta
from app.ui.components.primitives import GlassCard, StatusPill
from app.ui.components.server_params_form import ServerParamsForm
from app.ui.brand_manager import BrandManager
from app.lab.state.models import RemoteGGUF, ServerParams


class InstanceSelector(QComboBox):
    """Studio-style instance picker pill for model cards."""

    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        self._compact = compact
        self.setMinimumHeight(38)
        self.setMaximumHeight(38)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if compact:
            self.setMaximumWidth(288)
        self.setStyleSheet(
            f"""
            QComboBox {{
                background: {t.SURFACE_3};
                border: 1px solid {t.BORDER_MED};
                border-left: 3px solid rgba(255,255,255,0.18);
                border-radius: 10px;
                color: {t.TEXT_HI};
                padding-left: 14px;
                padding-right: 30px;
                font-size: 13px;
                font-weight: 600;
                min-height: 38px;
                max-height: 38px;
            }}
            QComboBox[connected="true"] {{
                border-left: 3px solid {t.OK};
            }}
            QComboBox:hover {{
                background: #303a4f;
                border-color: {t.BORDER_HI};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 22px;
                subcontrol-position: right center;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t.SURFACE_2};
                color: {t.TEXT_HI};
                border: 1px solid {t.BORDER_MED};
                border-radius: {t.RADIUS_MD}px;
                selection-background-color: {t.ACCENT};
                padding: 4px;
            }}
            """
        )

    def refresh(self, instances: list[tuple[int, RemoteGGUF]], connected_iids: set[int]):
        """Populate with instances. instances = [(iid, gguf), ...]."""
        self.blockSignals(True)
        old_data = self.currentData()
        self.clear()
        for iid, gguf in instances:
            label = f"Instance #{iid}"
            if self._compact:
                tag = "Connected" if iid in connected_iids else "Offline"
                self.addItem(label, iid)
                self.setItemData(self.count() - 1, tag, Qt.ToolTipRole)
            else:
                tag = "Connected" if iid in connected_iids else "Disconnected"
                self.addItem(label, iid)
                self.setItemData(self.count() - 1, tag, Qt.ToolTipRole)
        # Restore selection if possible
        if old_data is not None:
            idx = self.findData(old_data)
            if idx >= 0:
                self.setCurrentIndex(idx)
        self.blockSignals(False)
        self._refresh_accent()

    def _refresh_accent(self):
        iid = self.currentData()
        connected = iid is not None
        self.setProperty("connected", "true" if connected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class ConfigurePanel(GlassCard):
    """Right-side Studio-style settings panel for model configuration."""

    launch_requested = Signal(object, int)   # ServerParams, iid
    save_requested = Signal(object, int, str)  # ServerParams, iid, path

    def __init__(self, store, parent=None):
        super().__init__(parent=parent)
        self.store = store
        self._current_path: str | None = None
        self._current_iid: int | None = None
        self._current_filename: str | None = None
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        self._lay.setSpacing(t.SPACE_4)

        header_row = QHBoxLayout()
        title = QLabel("Settings")
        title.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 16px; font-weight: 700;"
        )
        header_row.addWidget(title)
        header_row.addStretch()
        self._model_count_lbl = QLabel("")
        self._model_count_lbl.setProperty("role", "muted")
        header_row.addWidget(self._model_count_lbl)
        self._lay.addLayout(header_row)

        picker_label_style = (
            f"color: {t.TEXT_LOW}; font-size: 11px; font-weight: 700;"
            f" letter-spacing: 0.6px; text-transform: uppercase;"
        )

        self._picker_grid = QGridLayout()
        self._picker_grid.setContentsMargins(0, 0, 0, 0)
        self._picker_grid.setHorizontalSpacing(t.SPACE_4)
        self._picker_grid.setVerticalSpacing(t.SPACE_3)
        self._picker_grid.setColumnStretch(0, 1)
        self._picker_grid.setColumnStretch(1, 5)

        inst_lbl = QLabel("Instance")
        inst_lbl.setStyleSheet(picker_label_style)
        self._instance_combo = QComboBox()
        self._instance_combo.setObjectName("studio-instance-picker")
        self._instance_combo.setMinimumWidth(0)
        self._instance_combo.setMaximumWidth(16777215)
        self._instance_combo.setMinimumContentsLength(11)
        self._instance_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        self._instance_field = self._build_picker_field(inst_lbl, self._instance_combo)
        self._picker_grid.addWidget(self._instance_field, 0, 0)

        model_lbl = QLabel("Model")
        model_lbl.setStyleSheet(picker_label_style)
        self._model_picker = QComboBox()
        self._model_picker.setObjectName("studio-model-picker")
        self._model_picker.setMinimumWidth(0)
        self._model_picker.setMaximumWidth(16777215)
        self._model_picker.setMinimumContentsLength(24)
        self._model_picker.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._model_field = self._build_picker_field(model_lbl, self._model_picker)
        self._picker_grid.addWidget(self._model_field, 0, 1)
        self._lay.addLayout(self._picker_grid)

        section_lbl = QLabel("Model configuration")
        section_lbl.setProperty("role", "section")
        self._lay.addWidget(section_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._form_host = QWidget()
        form_lay = QVBoxLayout(self._form_host)
        form_lay.setContentsMargins(0, 0, t.SPACE_3, 0)
        form_lay.setSpacing(t.SPACE_2)
        self._form = ServerParamsForm([])
        self._form.set_model_field_visible(False)
        form_lay.addWidget(self._form)
        form_lay.addStretch()
        scroll.setWidget(self._form_host)
        self._lay.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, t.SPACE_2, 0, 0)
        actions.setSpacing(t.SPACE_3)
        actions.addStretch()
        self._save_btn = QPushButton("Save Config")
        self._save_btn.setProperty("variant", "ghost")
        self._save_btn.setMinimumHeight(40)
        self._save_btn.setMinimumWidth(144)
        self._save_btn.clicked.connect(self._on_save)
        actions.addWidget(self._save_btn)
        self._lay.addLayout(actions)

    def _build_picker_field(self, label: QLabel, control: QWidget) -> QWidget:
        field = QWidget()
        lay = QVBoxLayout(field)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_2)
        lay.addWidget(label)
        lay.addWidget(control)
        return field

    def _refresh_form(self):
        if self._current_path is None:
            return
        iid = self._instance_combo.currentData() or self._current_iid
        st = self.store.get_state(iid) if iid else None
        initial_p = st.model_configs.get(self._current_path) if st else None
        params = initial_p or ServerParams(model_path=self._current_path)
        params.model_path = self._current_path
        self._form.set_model_paths([self._current_path])
        self._form.set_params(params)

    def set_model(self, filename: str, path: str, instances: list[tuple[int, RemoteGGUF]],
                  connected_iids: set[int], default_iid: int | None = None):
        """Load a model into the panel."""
        self._current_filename = filename
        self._current_path = path
        self._current_iid = default_iid

        self._instance_combo.blockSignals(True)
        old_data = self._instance_combo.currentData()
        self._instance_combo.clear()
        for iid, _gguf in instances:
            label = f"Instance #{iid}"
            self._instance_combo.addItem(label, iid)
            tag = "Connected" if iid in connected_iids else "Disconnected"
            self._instance_combo.setItemData(self._instance_combo.count() - 1, tag, Qt.ToolTipRole)
        if default_iid is not None:
            idx = self._instance_combo.findData(default_iid)
            if idx >= 0:
                self._instance_combo.setCurrentIndex(idx)
        elif old_data is not None:
            idx = self._instance_combo.findData(old_data)
            if idx >= 0:
                self._instance_combo.setCurrentIndex(idx)
        self._instance_combo.blockSignals(False)
        self._refresh_instance_combo_accent()

        self._model_picker.blockSignals(True)
        self._model_picker.clear()
        self._model_picker.addItem(BrandManager.get_icon(filename), filename, path)
        self._model_picker.setCurrentIndex(0)
        self._model_picker.blockSignals(False)

        self._model_count_lbl.setText(
            f"{len(instances)} instance" if len(instances) == 1 else f"{len(instances)} instances"
        )
        self._refresh_form()

    def _on_instance_changed(self, index: int):
        iid = self._instance_combo.itemData(index)
        self._current_iid = iid
        self._refresh_instance_combo_accent()
        if iid is not None:
            self._refresh_form()

    def _refresh_instance_combo_accent(self):
        connected = self._instance_combo.currentIndex() >= 0
        self._instance_combo.setProperty("connected", "true" if connected else "false")
        self._instance_combo.style().unpolish(self._instance_combo)
        self._instance_combo.style().polish(self._instance_combo)

    def _on_save(self):
        if self._current_iid is not None and self._current_path is not None:
            params = self._form.current_params()
            params.model_path = self._current_path
            self.save_requested.emit(params, self._current_iid, self._current_path)

    def _on_launch(self):
        if self._current_iid is not None and self._current_path is not None:
            params = self._form.current_params()
            params.model_path = self._current_path
            self.launch_requested.emit(params, self._current_iid)


class ModelsView(QWidget):
    launch_requested = Signal(object, int)   # ServerParams, iid
    stop_requested = Signal(int)             # iid
    delete_requested = Signal(str, int)      # path, iid
    rescan_requested = Signal()
    navigate_requested = Signal(str)
    instances_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("models-view")
        self.setStyleSheet(
            f"""
            QWidget#models-view {{
                background: {t.BG_DEEP};
            }}
            QWidget#models-settings {{
                background: transparent;
            }}
            QComboBox#studio-instance-picker,
            QComboBox#studio-model-picker {{
                min-height: 38px;
                max-height: 38px;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
            }}
            QComboBox#studio-instance-picker {{
                background: {t.SURFACE_3};
                border: 1px solid {t.BORDER_MED};
                border-left: 3px solid rgba(255,255,255,0.18);
                color: {t.TEXT_HI};
                padding-left: 14px;
                padding-right: 38px;
            }}
            QComboBox#studio-instance-picker[connected="true"] {{
                border-left: 3px solid {t.OK};
            }}
            QComboBox#studio-instance-picker:hover {{
                background: #303a4f;
                border-color: {t.BORDER_HI};
            }}
            QComboBox#studio-model-picker {{
                background: {t.SURFACE_3};
                border: 1px solid {t.BORDER_MED};
                color: {t.TEXT_HI};
                padding-left: 14px;
                padding-right: 42px;
            }}
            QComboBox#studio-model-picker:hover {{
                background: #303a4f;
                border-color: rgba(179,160,255,0.44);
            }}
            QComboBox#studio-model-picker:focus {{
                background: #303a4f;
                border-color: rgba(179,160,255,0.52);
            }}
            QComboBox#studio-model-picker:disabled {{
                background: {t.SURFACE_3};
                border: 1px solid rgba(255,255,255,0.06);
                color: {t.TEXT_MID};
                font-weight: 600;
            }}
            QComboBox#studio-instance-picker::drop-down,
            QComboBox#studio-model-picker::drop-down {{
                border: none;
                width: 22px;
                subcontrol-position: right center;
                margin-right: 6px;
            }}
            QWidget#models-view QComboBox,
            QWidget#models-view QLineEdit,
            QWidget#models-view QSpinBox,
            QWidget#models-view QDoubleSpinBox {{
                background: {t.SURFACE_3};
                color: {t.TEXT_HI};
                border: 1px solid {t.BORDER_MED};
                border-radius: 12px;
                padding: 7px 14px;
                min-height: 34px;
            }}
            QWidget#models-view QComboBox:focus,
            QWidget#models-view QLineEdit:focus,
            QWidget#models-view QSpinBox:focus,
            QWidget#models-view QDoubleSpinBox:focus {{
                border-color: rgba(179,160,255,0.42);
                background: #303a4f;
            }}
            QWidget#models-view QComboBox::drop-down {{
                border: none;
                width: 24px;
                margin-right: 4px;
            }}
            QWidget#models-view QPushButton {{
                border-radius: 12px;
                min-height: 36px;
            }}
            QPushButton#model-card-configure-btn,
            QPushButton#model-card-eject-btn,
            QPushButton#model-card-launch-btn,
            QPushButton#model-card-delete-btn {{
                min-height: 54px;
                max-height: 54px;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton#model-card-configure-btn {{
                padding: 0 18px;
            }}
            QPushButton#model-card-eject-btn {{
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.10);
                color: {t.TEXT_HI};
                padding: 0 18px;
            }}
            QPushButton#model-card-eject-btn:hover:enabled {{
                background: rgba(240,85,106,0.10);
                border-color: rgba(240,85,106,0.45);
                color: {t.ERR};
            }}
            QPushButton#model-card-eject-btn:disabled {{
                color: {t.TEXT_MID};
                background: rgba(255,255,255,0.02);
                border-color: rgba(255,255,255,0.06);
            }}
            QPushButton#model-card-delete-btn {{
                background: rgba(240,85,106,0.12);
                border: 1px solid rgba(240,85,106,0.34);
                color: {t.ERR};
                padding: 0;
            }}
            QPushButton#model-card-delete-btn:hover:enabled {{
                background: rgba(240,85,106,0.20);
                border-color: rgba(240,85,106,0.54);
            }}
            QPushButton#model-card-launch-btn {{
                padding: 0 20px;
            }}
            QWidget#models-view QFrame#SolidCard QScrollArea,
            QWidget#models-view QFrame#SolidCard QScrollArea::viewport,
            QWidget#models-view QFrame#SolidCard QScrollArea > QWidget,
            QWidget#models-view QFrame#SolidCard QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            QWidget#models-view QScrollArea,
            QWidget#models-view QScrollArea > QWidget,
            QWidget#models-view QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            QWidget#models-view QCheckBox {{
                color: {t.TEXT};
                spacing: 8px;
            }}
            QWidget#models-view QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 5px;
                background: #111820;
            }}
            QWidget#models-view QCheckBox::indicator:checked {{
                background: {t.ACCENT};
                border-color: {t.ACCENT};
            }}
            """
        )
        self._model_index: dict[str, list[tuple[int, RemoteGGUF]]] = {}
        self._selected_iid_for_model: dict[str, int] = {}
        self._connected_iids: set[int] = set()
        self._side_panel_last_width = 400
        self._open_config_key: tuple[str, int] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        # Header
        header = PageHeader("Model Library", "")
        self.ctx_lbl = header.subtitle_label
        refresh_btn = QPushButton("\u21BB Rescan")
        refresh_btn.setObjectName("rescan-btn")
        refresh_btn.setStyleSheet(f"""
            QPushButton#rescan-btn {{
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.10);
                color: {t.TEXT_HI};
                min-height: 38px;
                max-height: 38px;
                padding: 0 18px;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#rescan-btn:hover:enabled {{
                background: rgba(255,255,255,0.08);
                border-color: rgba(255,255,255,0.15);
            }}
        """)
        refresh_btn.clicked.connect(self.rescan_requested.emit)
        header.add_action(refresh_btn)
        root.addWidget(header)

        # Layout stack: lock | empty | content
        self.layout_stack = QStackedWidget()
        root.addWidget(self.layout_stack, 1)

        # 1. Lock Screen
        self.lock_screen = LockScreen(
            title="SSH Tunnel Required",
            message="An active SSH connection is required to browse and manage GGUF models across your instances."
        )
        self.lock_screen.instances_requested.connect(self.instances_requested.emit)
        self.layout_stack.addWidget(self.lock_screen)

        # 2. Empty State (SSH active, no models)
        self.empty_state = QWidget()
        empty_lay = QVBoxLayout(self.empty_state)
        empty_lay.setAlignment(Qt.AlignCenter)
        empty_icon = QLabel()
        empty_icon.setPixmap(qta.icon("mdi.folder-open-outline", color=t.ACCENT).pixmap(64, 64))
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_title = QLabel("No Models Found")
        empty_title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 20px; font-weight: 600;")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_msg = QLabel("No GGUF models found on any connected instance.\nBrowse the Model Store to get started.")
        empty_msg.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 14px;")
        empty_msg.setWordWrap(True)
        empty_msg.setFixedWidth(400)
        empty_msg.setAlignment(Qt.AlignCenter)
        go_discover_btn = QPushButton("\u2726 Discover Models")
        go_discover_btn.setObjectName("lock-screen-cta")
        go_discover_btn.setFixedSize(220, 44)
        go_discover_btn.setProperty("variant", "primary")
        go_discover_btn.clicked.connect(lambda: self.navigate_requested.emit("discover"))
        empty_lay.addStretch()
        empty_lay.addWidget(empty_icon)
        empty_lay.addSpacing(t.SPACE_3)
        empty_lay.addWidget(empty_title)
        empty_lay.addSpacing(t.SPACE_2)
        empty_lay.addWidget(empty_msg)
        empty_lay.addSpacing(t.SPACE_4)
        empty_lay.addWidget(go_discover_btn, 0, Qt.AlignCenter)
        empty_lay.addStretch()
        self.layout_stack.addWidget(self.empty_state)

        # 3. Main content
        self.content_widget = QWidget()
        content_lay = QVBoxLayout(self.content_widget)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        # Splitter: list | configure panel
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        # Left: scroll list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 100)
        self.list_lay.setSpacing(t.SPACE_5)
        self.scroll.setWidget(self.list_host)
        self.splitter.addWidget(self.scroll)

        # Right: configure panel with a real composition gap from the list
        self.side_panel = QWidget()
        self.side_panel.setObjectName("models-settings")
        self.side_panel.setMinimumWidth(392)
        self.side_panel.setMaximumWidth(520)
        panel_lay = QVBoxLayout(self.side_panel)
        panel_lay.setContentsMargins(t.SPACE_2, 0, t.SPACE_2, t.SPACE_3)
        panel_lay.setSpacing(0)
        self.configure_panel = ConfigurePanel(self.store)
        self.configure_panel.setVisible(False)
        self.configure_panel.launch_requested.connect(self.launch_requested.emit)
        self.configure_panel.save_requested.connect(
            lambda p, iid, path: self.store.save_model_config(iid, path, p)
        )
        panel_lay.addWidget(self.configure_panel)
        self.splitter.addWidget(self.side_panel)
        self.splitter.setSizes([1, 0])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        content_lay.addWidget(self.splitter, 1)
        self.layout_stack.addWidget(self.content_widget)

        # Signals
        self.store.instance_state_updated.connect(lambda *_: self._render())
        self.store.remote_gguf_changed.connect(lambda *_: self._render())
        self._render()

    def _set_config_panel_visible(self, visible: bool) -> None:
        self.configure_panel.setVisible(visible)
        total = self.splitter.width()
        if visible:
            if total > 0:
                panel_width = min(max(392, self._side_panel_last_width), 520)
                self.splitter.setSizes([max(1, total - panel_width), panel_width])
            else:
                self.splitter.setSizes([1060, 440])
        else:
            sizes = self.splitter.sizes()
            if len(sizes) == 2 and sizes[1] > 0:
                self._side_panel_last_width = sizes[1]
            self.splitter.setSizes([1, 0])
            self._open_config_key = None

    def _build_model_index(self) -> dict[str, list[tuple[int, RemoteGGUF]]]:
        index: dict[str, list[tuple[int, RemoteGGUF]]] = {}
        self._connected_iids.clear()
        for iid, state in self.store.instance_states.items():
            if state.setup.probed:
                self._connected_iids.add(iid)
            for gguf in state.gguf:
                index.setdefault(gguf.filename, []).append((iid, gguf))
        for filename in index:
            index[filename].sort(key=lambda x: x[0])
        return index

    def _update_subtitle(self):
        total_unique = len(self._model_index)
        total_instances = len(self._connected_iids)
        if total_unique == 0:
            self.ctx_lbl.setText("No models found across connected instances")
        else:
            inst_text = f"{total_instances} instance" + ("" if total_instances == 1 else "s")
            model_text = f"{total_unique} model" if total_unique == 1 else f"{total_unique} models"
            self.ctx_lbl.setText(f"{model_text} across {inst_text}")

    def _render(self):
        self._model_index = self._build_model_index()
        self._update_subtitle()

        # Determine target state
        if not self._connected_iids:
            target_idx = 0  # Lock screen
        elif not self._model_index:
            target_idx = 1  # Empty state
        else:
            target_idx = 2  # Content

        if self.layout_stack.currentIndex() != target_idx:
            self.layout_stack.setCurrentIndex(target_idx)

        # Only render list content if on content page
        if target_idx != 2:
            return

        # Clear list
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Render cards
        for filename, instances in self._model_index.items():
            card = self._build_model_card(filename, instances)
            self.list_lay.addWidget(card)

        self.list_lay.addStretch()

    def _build_model_card(self, filename: str, instances: list[tuple[int, RemoteGGUF]]) -> GlassCard:
        card = GlassCard(raised=True)
        card._lay.setSpacing(0)
        card._lay.setContentsMargins(0, 0, 0, 0)

        # Header widget
        header_widget = QWidget()
        header_lay = QVBoxLayout(header_widget)
        header_lay.setContentsMargins(t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_5)
        header_lay.setSpacing(t.SPACE_4)

        # Row 1: Brand Icon + Title + Size pill
        r1 = QHBoxLayout()
        r1.setSpacing(t.SPACE_3)

        icon_lbl = QLabel()
        icon_pix = BrandManager.get_icon(filename).pixmap(32, 32)
        icon_lbl.setPixmap(icon_pix)
        icon_lbl.setFixedSize(32, 32)
        r1.addWidget(icon_lbl)

        name_lbl = QLabel(filename)
        name_lbl.setStyleSheet(
            f"font-size: 14pt; font-weight: 700; color: {t.TEXT_HI};"
        )
        r1.addWidget(name_lbl)
        r1.addStretch()

        # Use size from first instance (they should be identical)
        first_gguf = instances[0][1]
        pill = StatusPill(first_gguf.size_display or "\u2014", "info")
        r1.addWidget(pill)
        header_lay.addLayout(r1)

        # Row 2: Path
        path_lbl = QLabel(first_gguf.path)
        path_lbl.setStyleSheet(
            f"font-family: {t.FONT_MONO}; font-size: 10px;"
            f" color: {t.TEXT_LOW};"
        )
        header_lay.addWidget(path_lbl)

        # Row 3: Actions
        r3 = QHBoxLayout()
        r3.setContentsMargins(0, t.SPACE_1, 0, 0)
        r3.setSpacing(t.SPACE_3)

        configure_btn = QPushButton("Configure")
        configure_btn.setObjectName("model-card-configure-btn")
        configure_btn.setProperty("variant", "secondary")
        configure_btn.setIcon(qta.icon("mdi.cog-outline", color=t.TEXT_HI))
        configure_btn.setIconSize(QSize(16, 16))
        configure_btn.setMinimumWidth(132)
        configure_btn.setMinimumHeight(54)
        configure_btn.setMaximumHeight(54)

        del_btn = QPushButton()
        del_btn.setObjectName("model-card-delete-btn")
        del_btn.setToolTip("Delete model")
        del_btn.setIcon(qta.icon("mdi.delete-outline", color=t.ERR))
        del_btn.setIconSize(QSize(18, 18))
        del_btn.setMinimumSize(54, 54)
        del_btn.setMaximumSize(54, 54)

        stop_btn = QPushButton("Eject")
        stop_btn.setObjectName("model-card-eject-btn")
        stop_btn.setIcon(qta.icon("mdi.eject-outline", color=t.TEXT_HI))
        stop_btn.setIconSize(QSize(16, 16))
        stop_btn.setMinimumWidth(132)
        stop_btn.setMinimumHeight(54)
        stop_btn.setMaximumHeight(54)

        # Determine default instance for this model
        default_iid = self._selected_iid_for_model.get(filename)
        if default_iid is None:
            # Prefer first connected instance
            for iid, _ in instances:
                if iid in self._connected_iids:
                    default_iid = iid
                    break
            if default_iid is None:
                default_iid = instances[0][0]
            self._selected_iid_for_model[filename] = default_iid

        # Instance selector
        instance_selector = InstanceSelector(compact=True)
        instance_selector.refresh(instances, self._connected_iids)
        idx = instance_selector.findData(default_iid)
        if idx >= 0:
            instance_selector.setCurrentIndex(idx)

        def refresh_stop_state(current_iid: int | None = None) -> None:
            iid = current_iid or instance_selector.currentData() or default_iid
            stop_btn.setEnabled(self._is_server_running_for_model(iid, first_gguf.path))

        def on_instance_changed(new_iid):
            self._selected_iid_for_model[filename] = new_iid
            refresh_stop_state(new_iid)

        instance_selector.currentIndexChanged.connect(
            lambda idx: on_instance_changed(instance_selector.itemData(idx))
        )

        # Delete handler
        def on_delete():
            iid = instance_selector.currentData() or default_iid
            self._confirm_delete(first_gguf.path, filename, iid)
        del_btn.clicked.connect(on_delete)

        def on_stop():
            iid = instance_selector.currentData() or default_iid
            self.stop_requested.emit(iid)
        stop_btn.clicked.connect(on_stop)

        # Launch handler
        launch_btn = QPushButton("Launch Server")
        launch_btn.setObjectName("model-card-launch-btn")
        launch_btn.setIcon(qta.icon("mdi.play", color="white"))
        launch_btn.setIconSize(QSize(14, 14))
        launch_btn.setMinimumWidth(176)
        launch_btn.setMinimumHeight(54)
        launch_btn.setMaximumHeight(54)

        def on_launch():
            iid = instance_selector.currentData() or default_iid
            st = self.store.get_state(iid) if iid else None
            params = st.model_configs.get(first_gguf.path) if st else None
            if params is None:
                params = ServerParams(model_path=first_gguf.path)
            self.launch_requested.emit(params, iid)
        launch_btn.clicked.connect(on_launch)

        # Configure handler
        def on_configure():
            iid = instance_selector.currentData() or default_iid
            config_key = (first_gguf.path, iid)
            if self.configure_panel.isVisible() and self._open_config_key == config_key:
                self._set_config_panel_visible(False)
            else:
                self.configure_panel.set_model(filename, first_gguf.path, instances, self._connected_iids, iid)
                self._open_config_key = config_key
                self._set_config_panel_visible(True)
        configure_btn.clicked.connect(on_configure)
        refresh_stop_state()

        r3.addWidget(configure_btn)
        r3.addWidget(del_btn)
        r3.addStretch()
        r3.addWidget(instance_selector)
        r3.addWidget(stop_btn)
        r3.addWidget(launch_btn)

        header_lay.addLayout(r3)
        card._lay.addWidget(header_widget)
        return card

    def _is_server_running_for_model(self, iid: int | None, model_path: str) -> bool:
        if iid is None:
            return False
        st = self.store.get_state(iid)
        running_path = (st.setup.llama_server_model or "").strip('"')
        return bool(st.setup.llama_server_running and running_path == model_path)

    def _on_splitter_moved(self, *_args) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) == 2 and sizes[1] > 0:
            self._side_panel_last_width = sizes[1]

    def _confirm_delete(self, path: str, name: str, iid: int):
        reply = QMessageBox.question(
            self, "Delete model",
            f"Remove {name} from Instance #{iid}?\n{path}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(path, iid)
