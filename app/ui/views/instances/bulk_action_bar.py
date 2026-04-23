from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from app.theme import BORDER_MED, ERR, SURFACE_2, TEXT, TEXT_HI
from app.ui.components import icons
from app.ui.components.primitives import icon


class BulkActionBar(QFrame):
    """Bottom bar for selection-mode operations."""

    action_clicked = Signal(str)
    clear_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"BulkActionBar {{ background: {SURFACE_2}; border: 1px solid {BORDER_MED};"
            f" border-radius: 8px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        self.count_label = QLabel("0 selecionados")
        self.count_label.setStyleSheet(f"color: {TEXT_HI};")
        lay.addWidget(self.count_label)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFlat(True)
        self.btn_clear.clicked.connect(self.clear_clicked)
        lay.addWidget(self.btn_clear)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {BORDER_MED};")
        lay.addWidget(sep)

        self.btn_start = self._action_btn(icons.PLAY, "Start", "start")
        self.btn_stop = self._action_btn(icons.STOP, "Stop", "stop")
        self.btn_connect = self._action_btn(icons.TUNNEL, "Connect", "connect")
        self.btn_disconnect = self._action_btn(icons.DISCONNECT, "Disconnect", "disconnect")
        self.btn_label = self._action_btn(icons.TAG, "Label", "label")
        self.btn_destroy = self._action_btn(icons.DELETE, "Destroy", "destroy", danger=True)
        for btn in (
            self.btn_start,
            self.btn_stop,
            self.btn_connect,
            self.btn_disconnect,
            self.btn_label,
            self.btn_destroy,
        ):
            lay.addWidget(btn)

    def _action_btn(self, mdi: str, label: str, action: str, *, danger: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setIcon(icon(mdi, color=ERR if danger else TEXT))
        btn.setFlat(True)
        btn.clicked.connect(lambda: self.action_clicked.emit(action))
        return btn

    def set_count(self, count: int) -> None:
        self.count_label.setText(f"{count} selecionados" if count else "Nenhum selecionado")
