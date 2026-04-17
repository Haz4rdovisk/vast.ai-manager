"""Models view \u2014 lists GGUF files on the remote instance."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox,
)
from PySide6.QtCore import Signal
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader, StatusPill


class ModelsView(QWidget):
    load_requested = Signal(str)      # model path -> opens Configure
    delete_requested = Signal(str)    # model path
    rescan_requested = Signal()
    navigate_requested = Signal(str)  # nav key

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        head.addWidget(SectionHeader("REMOTE FILES", "Models on Instance"))
        head.addStretch()
        refresh_btn = QPushButton("\u21BB Rescan")
        refresh_btn.clicked.connect(self.rescan_requested.emit)
        head.addWidget(refresh_btn)
        dl_btn = QPushButton("\u2726 Download New")
        dl_btn.clicked.connect(lambda: self.navigate_requested.emit("discover"))
        head.addWidget(dl_btn)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(t.SPACE_3)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.store.remote_gguf_changed.connect(self._render)

    def _render(self, files):
        while self.list_lay.count():
            w = self.list_lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        if not files:
            empty = GlassCard()
            lbl = QLabel("No GGUF models found on the instance.")
            lbl.setProperty("role", "muted")
            empty.body().addWidget(lbl)
            hint = QLabel("Go to Discover to download models from HuggingFace.")
            hint.setProperty("role", "muted")
            empty.body().addWidget(hint)
            btn = QPushButton("\u2726 Discover Models")
            btn.clicked.connect(lambda: self.navigate_requested.emit("discover"))
            empty.body().addWidget(btn)
            self.list_lay.addWidget(empty)
            self.list_lay.addStretch()
            return

        for f in files:
            card = GlassCard()
            header = QHBoxLayout()
            name = QLabel(f.filename)
            name.setProperty("role", "title")
            header.addWidget(name)
            header.addStretch()
            header.addWidget(StatusPill(f.size_display or "?", "info"))
            card.body().addLayout(header)

            path_lbl = QLabel(f.path)
            path_lbl.setProperty("role", "muted")
            card.body().addWidget(path_lbl)

            actions = QHBoxLayout()
            actions.addStretch()

            load_btn = QPushButton("\u25B6 Load & Configure")
            load_btn.clicked.connect(
                lambda _=False, p=f.path: self.load_requested.emit(p))
            actions.addWidget(load_btn)

            del_btn = QPushButton("Delete")
            del_btn.setProperty("variant", "ghost")
            del_btn.clicked.connect(
                lambda _=False, p=f.path, n=f.filename: self._confirm_delete(p, n))
            actions.addWidget(del_btn)

            card.body().addLayout(actions)
            self.list_lay.addWidget(card)

        self.list_lay.addStretch()

    def _confirm_delete(self, path: str, name: str):
        reply = QMessageBox.question(
            self, "Delete model",
            f"Remove {name} from the remote instance?\n\n{path}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(path)
