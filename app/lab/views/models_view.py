"""Models view — lists GGUF files with perfect horizontal alignment."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QFrame,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, StatusPill
from app.ui.components.model_config_form import ModelConfigForm


class ModelsView(QWidget):
    launch_requested = Signal(object)   # ServerParams
    delete_requested = Signal(str)      # model path
    rescan_requested = Signal()
    navigate_requested = Signal(str)    # nav key
    back_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._expanded_path = None
        self._forms: dict[str, ModelConfigForm] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        # Breadcrumbs
        nav_lay = QHBoxLayout()
        self.back_btn = QPushButton("\u2190 Back")
        self.back_btn.setProperty("variant", "ghost")
        self.back_btn.clicked.connect(self.back_requested.emit)
        nav_lay.addWidget(self.back_btn)
        
        self.ctx_lbl = QLabel("Dashboard > Instance > Models")
        self.ctx_lbl.setProperty("role", "muted")
        nav_lay.addWidget(self.ctx_lbl)
        nav_lay.addStretch()
        root.addLayout(nav_lay)

        # Header
        head = QHBoxLayout()
        head.addWidget(SectionHeader("REMOTE FILES", "Manage Models & Inference"))
        head.addStretch()
        refresh_btn = QPushButton("\u21BB Rescan")
        refresh_btn.clicked.connect(self.rescan_requested.emit)
        head.addWidget(refresh_btn)
        dl_btn = QPushButton("\u2726 Discover More")
        dl_btn.clicked.connect(lambda: self.navigate_requested.emit("discover"))
        head.addWidget(dl_btn)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 100) # Bottom padding for scroll
        self.list_lay.setSpacing(t.SPACE_6)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.store.instance_changed.connect(self._on_instance_changed)
        self.store.remote_gguf_changed.connect(self._render)

    def _on_instance_changed(self, iid: int):
        self.ctx_lbl.setText(f"Dashboard > Instance #{iid} > Models" if iid else "Dashboard > Models")

    def _render(self, files):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        
        self._forms.clear()

        if not files:
            empty = GlassCard()
            empty.body().addWidget(QLabel("No GGUF models found. Download some from Discover!"))
            self.list_lay.addWidget(empty)
            self.list_lay.addStretch()
            return

        iid = self.store.selected_instance_id
        st = self.store.get_state(iid) if iid else None

        for f in files:
            card = GlassCard(raised=True)
            card._lay.setSpacing(0)
            card._lay.setContentsMargins(0, 0, 0, 0)
            
            # --- Grid-based Professional Header ---
            header_widget = QWidget()
            header_lay = QVBoxLayout(header_widget)
            header_lay.setContentsMargins(t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_5)
            header_lay.setSpacing(t.SPACE_4)
            
            # Row 1: Title & Pill
            r1 = QHBoxLayout()
            name_lbl = QLabel(f.filename)
            name_lbl.setProperty("role", "title")
            name_lbl.setStyleSheet("font-size: 13pt; font-weight: 700;")
            r1.addWidget(name_lbl)
            r1.addStretch()
            pill = StatusPill(f.size_display, "info")
            r1.addWidget(pill)
            header_lay.addLayout(r1)
            
            # Row 2: Path (Mono)
            path_lbl = QLabel(f.path)
            path_lbl.setProperty("role", "muted")
            path_lbl.setStyleSheet(f"font-family: 'Consolas'; font-size: 9pt; color: {t.TEXT_LOW}; margin-bottom: 4px;")
            header_lay.addWidget(path_lbl)
            
            # Row 3: Action Row (Horizontal Alignment for ALL buttons)
            r3 = QHBoxLayout()
            r3.setSpacing(t.SPACE_3)
            
            expand_btn = QPushButton("\u2699 Configure")
            expand_btn.setMinimumWidth(130)
            expand_btn.setProperty("variant", "secondary" if f.path != self._expanded_path else "ghost")
            
            del_btn = QPushButton("Delete")
            del_btn.setProperty("variant", "ghost")
            del_btn.setMinimumWidth(100)
            del_btn.clicked.connect(lambda _=False, p=f.path, n=f.filename: self._confirm_delete(p, n))
            
            r3.addWidget(expand_btn)
            r3.addWidget(del_btn)
            r3.addStretch()
            
            launch_h_btn = QPushButton("\u25B6  Launch Server")
            launch_h_btn.setProperty("variant", "primary")
            launch_h_btn.setMinimumHeight(40)
            launch_h_btn.setMinimumWidth(200)
            r3.addWidget(launch_h_btn)
            
            header_lay.addLayout(r3)
            
            card._lay.addWidget(header_widget)

            # --- Config Drawer ---
            config_drawer = QWidget()
            config_lay = QVBoxLayout(config_drawer)
            config_lay.setContentsMargins(t.SPACE_5, 0, t.SPACE_5, t.SPACE_5)
            
            sep = QFrame()
            sep.setStyleSheet(f"background: {t.SURFACE_3}; max-height: 1px; border: none; margin-bottom: 10px;")
            config_lay.addWidget(sep)
            
            # Initial params from store
            initial_p = st.model_configs.get(f.path) if st else None
            form = ModelConfigForm(f.path, self.store, initial_params=initial_p)
            self._forms[f.path] = form
            
            # Wiring
            def make_save(p=f.path, s_iid=iid):
                def on_save(params):
                    self.store.save_model_config(s_iid, p, params)
                return on_save
            form.save_requested.connect(make_save())
            
            def make_launch(fm=form):
                def on_launch():
                    self.launch_requested.emit(fm.gather_params())
                return on_launch
            launch_h_btn.clicked.connect(make_launch())
            
            config_lay.addWidget(form)
            config_drawer.setVisible(f.path == self._expanded_path)
            card._lay.addWidget(config_drawer)
            
            if f.path == self._expanded_path:
                expand_btn.setText("Close")
            
            # Toggle logic
            def make_toggle(p=f.path, c=config_drawer, b=expand_btn):
                def toggle():
                    is_visible = c.isVisible()
                    c.setVisible(not is_visible)
                    b.setText("Close" if not is_visible else "\u2699 Configure")
                    b.setProperty("variant", "ghost" if not is_visible else "secondary")
                    b.style().unpolish(b); b.style().polish(b)
                    self._expanded_path = p if not is_visible else None
                return toggle
            expand_btn.clicked.connect(make_toggle())
            
            self.list_lay.addWidget(card)

        self.list_lay.addStretch()

    def _confirm_delete(self, path: str, name: str):
        reply = QMessageBox.question(self, "Delete model", f"Remove {name}?\n{path}", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes: self.delete_requested.emit(path)
