"""Models view — GGUF file manager. Glassmorphism redesign."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QFrame,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.page_header import PageHeader
from app.ui.components.primitives import GlassCard, StatusPill
from app.ui.components.model_config_form import ModelConfigForm


class ModelsView(QWidget):
    launch_requested = Signal(object)
    delete_requested = Signal(str)
    rescan_requested = Signal()
    navigate_requested = Signal(str)
    back_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._expanded_path = None
        self._forms: dict[str, ModelConfigForm] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        # Header
        header = PageHeader("Manage Models", "Studio > Instance > Models")
        self.back_btn = QPushButton("\u2190 Back")
        self.back_btn.setProperty("variant", "ghost")
        self.back_btn.clicked.connect(self.back_requested.emit)
        header.add_action(self.back_btn)
        self.ctx_lbl = header.subtitle_label
        refresh_btn = QPushButton("\u21BB Rescan")
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.rescan_requested.emit)
        header.add_action(refresh_btn)
        dl_btn = QPushButton("\u2726 Discover More")
        dl_btn.clicked.connect(
            lambda: self.navigate_requested.emit("discover")
        )
        header.add_action(dl_btn)
        root.addWidget(header)

        # Scroll list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 100)
        self.list_lay.setSpacing(t.SPACE_5)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.store.instance_changed.connect(self._on_instance_changed)
        self.store.remote_gguf_changed.connect(self._render)

    def _on_instance_changed(self, iid: int):
        self.ctx_lbl.setText(
            f"Studio \u203a Instance #{iid} \u203a Models"
            if iid else "Studio \u203a Models"
        )

    def _render(self, files):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._forms.clear()

        if not files:
            empty = GlassCard()
            ec = empty.body()
            icon = QLabel("\u25A4")
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet(f"font-size: 32pt; color: {t.TEXT_LOW};")
            ec.addWidget(icon)
            msg = QLabel("No GGUF models found on this instance.")
            msg.setAlignment(Qt.AlignCenter)
            msg.setProperty("role", "muted")
            ec.addWidget(msg)
            hint = QLabel("Download models from Discover to get started.")
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet(f"color: {t.TEXT_LOW};")
            ec.addWidget(hint)
            go = QPushButton("\u2726 Go to Discover")
            go.setProperty("variant", "ghost")
            go.setFixedWidth(160)
            go.clicked.connect(
                lambda: self.navigate_requested.emit("discover")
            )
            wrap = QHBoxLayout()
            wrap.addStretch()
            wrap.addWidget(go)
            wrap.addStretch()
            ec.addLayout(wrap)
            self.list_lay.addWidget(empty)
            self.list_lay.addStretch()
            return

        iid = self.store.selected_instance_id
        st = self.store.get_state(iid) if iid else None

        for f in files:
            card = GlassCard(raised=True)
            card._lay.setSpacing(0)
            card._lay.setContentsMargins(0, 0, 0, 0)

            # Header widget
            header_widget = QWidget()
            header_lay = QVBoxLayout(header_widget)
            header_lay.setContentsMargins(
                t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_5
            )
            header_lay.setSpacing(t.SPACE_3)

            # Row 1: Title + Size pill
            r1 = QHBoxLayout()
            name_lbl = QLabel(f.filename)
            name_lbl.setStyleSheet(
                f"font-size: 14pt; font-weight: 700; color: {t.TEXT_HI};"
            )
            r1.addWidget(name_lbl)
            r1.addStretch()
            pill = StatusPill(f.size_display, "info")
            r1.addWidget(pill)
            header_lay.addLayout(r1)

            # Row 2: Path
            path_lbl = QLabel(f.path)
            path_lbl.setStyleSheet(
                f"font-family: {t.FONT_MONO}; font-size: 10px;"
                f" color: {t.TEXT_LOW};"
            )
            header_lay.addWidget(path_lbl)

            # Row 3: Actions
            r3 = QHBoxLayout()
            r3.setSpacing(t.SPACE_2)

            expand_btn = QPushButton("\u2699 Configure")
            expand_btn.setProperty("variant", "ghost")
            expand_btn.setMinimumWidth(130)

            del_btn = QPushButton("Delete")
            del_btn.setProperty("variant", "ghost")
            del_btn.setMinimumWidth(90)
            del_btn.clicked.connect(
                lambda _=False, p=f.path, n=f.filename:
                    self._confirm_delete(p, n)
            )

            r3.addWidget(expand_btn)
            r3.addWidget(del_btn)
            r3.addStretch()

            launch_btn = QPushButton("\u25B6  Launch Server")
            launch_btn.setMinimumHeight(40)
            launch_btn.setMinimumWidth(180)
            r3.addWidget(launch_btn)

            header_lay.addLayout(r3)
            card._lay.addWidget(header_widget)

            # Config Drawer
            config_drawer = QWidget()
            config_lay = QVBoxLayout(config_drawer)
            config_lay.setContentsMargins(
                t.SPACE_5, 0, t.SPACE_5, t.SPACE_5
            )

            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet(
                f"background: {t.SURFACE_3}; margin-bottom: 10px;"
            )
            config_lay.addWidget(sep)

            initial_p = st.model_configs.get(f.path) if st else None
            form = ModelConfigForm(
                f.path, self.store, initial_params=initial_p
            )
            self._forms[f.path] = form

            def make_save(p=f.path, s_iid=iid):
                def on_save(params):
                    self.store.save_model_config(s_iid, p, params)
                return on_save
            form.save_requested.connect(make_save())

            def make_launch(fm=form):
                def on_launch():
                    self.launch_requested.emit(fm.gather_params())
                return on_launch
            launch_btn.clicked.connect(make_launch())

            config_lay.addWidget(form)
            config_drawer.setVisible(f.path == self._expanded_path)
            card._lay.addWidget(config_drawer)

            if f.path == self._expanded_path:
                expand_btn.setText("Close")

            def make_toggle(p=f.path, c=config_drawer, b=expand_btn):
                def toggle():
                    is_visible = c.isVisible()
                    c.setVisible(not is_visible)
                    b.setText(
                        "Close" if not is_visible else "\u2699 Configure"
                    )
                    self._expanded_path = p if not is_visible else None
                return toggle
            expand_btn.clicked.connect(make_toggle())

            self.list_lay.addWidget(card)

        self.list_lay.addStretch()

    def _confirm_delete(self, path: str, name: str):
        reply = QMessageBox.question(
            self, "Delete model",
            f"Remove {name}?\n{path}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(path)
