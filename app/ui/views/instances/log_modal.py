from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout

from app.theme import FONT_MONO, SURFACE_2, TEXT


class LogModal(QDialog):
    """Shows log lines containing the selected instance tag."""

    def __init__(self, instance_id: int, history: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Logs · instância #{instance_id}")
        self.resize(720, 440)
        self._tag = f"#{instance_id}"

        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            f"QPlainTextEdit {{ background: {SURFACE_2}; color: {TEXT};"
            f" font-family: {FONT_MONO}; }}"
        )
        for line in history:
            self.append_line(line)
        lay.addWidget(self.text)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Fechar")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def append_line(self, line: str) -> None:
        if self._tag in line:
            self.text.appendPlainText(line)

    def body_text(self) -> str:
        return self.text.toPlainText()
