from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.models import Instance
from app.theme import ACCENT, ERR, FONT_MONO, OK, TEXT, TEXT_HI


_TITLES = {
    "start": "Confirmar Start em",
    "stop": "Confirmar Stop em",
    "connect": "Confirmar Connect em",
    "disconnect": "Confirmar Disconnect em",
    "destroy": "Destroy permanente em",
    "label": "Aplicar label em",
}


class ConfirmBulkDialog(QDialog):
    """Modal listing affected instances, aggregate cost, and per-action options."""

    def __init__(self, action: str, instances: list[Instance], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirmar")
        self.setMinimumWidth(420)
        self.action = action
        self.instances = list(instances)

        lay = QVBoxLayout(self)
        title = QLabel(f"{_TITLES.get(action, action)} {len(instances)} instâncias")
        font = title.font()
        font.setPointSize(11)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color: {TEXT_HI};")
        lay.addWidget(title)

        self.lst = QListWidget()
        for inst in instances:
            item = QListWidgetItem(
                f"#{inst.id}   {inst.num_gpus or 1}× {inst.gpu_name}   "
                f"${(inst.dph or 0):.3f}/hr"
            )
            self.lst.addItem(item)
        lay.addWidget(self.lst)

        aggregate = sum(float(inst.dph or 0) for inst in instances)
        verb = "Você economizará" if action in ("stop", "disconnect", "destroy") else "Custo agregado:"
        self.summary = QLabel(f"{verb} ${aggregate:.3f}/hr")
        color = OK if verb.startswith("Você") else TEXT
        self.summary.setStyleSheet(f"color: {color}; font-family: {FONT_MONO};")
        lay.addWidget(self.summary)

        self.auto_connect_check: QCheckBox | None = None
        self.label_input: QLineEdit | None = None
        self.understand_check: QCheckBox | None = None

        if action == "start":
            self.auto_connect_check = QCheckBox("Conectar tunnels após start")
            self.auto_connect_check.setChecked(True)
            lay.addWidget(self.auto_connect_check)
        if action == "label":
            self.label_input = QLineEdit()
            self.label_input.setPlaceholderText("novo label (vazio = sem label)")
            lay.addWidget(self.label_input)
        if action == "destroy":
            self.understand_check = QCheckBox("Eu entendo que isto é irreversível")
            lay.addWidget(self.understand_check)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("Confirmar")
        self.confirm_btn.clicked.connect(self.accept)
        bg = ERR if action == "destroy" else ACCENT
        self.confirm_btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: white; border: none;"
            f" border-radius: 6px; padding: 6px 14px; }}"
        )
        row.addWidget(cancel)
        row.addWidget(self.confirm_btn)
        lay.addLayout(row)

        if action == "destroy":
            self.confirm_btn.setEnabled(False)
            self.understand_check.toggled.connect(self.confirm_btn.setEnabled)

    def summary_text(self) -> str:
        return self.summary.text()

    def list_text(self) -> str:
        return "\n".join(self.lst.item(i).text() for i in range(self.lst.count()))

    def collect_opts(self) -> dict:
        out: dict = {}
        if self.auto_connect_check is not None:
            out["auto_connect"] = self.auto_connect_check.isChecked()
        if self.label_input is not None:
            out["label"] = self.label_input.text()
        return out
