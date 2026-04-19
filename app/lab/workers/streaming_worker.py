"""QThread that streams a remote bash script line-by-line."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class StreamingRemoteWorker(QThread):
    line = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, ssh_service, host: str, port: int, script: str, parent=None):
        super().__init__(parent)
        self.ssh = ssh_service
        self.host = host
        self.port = port
        self.script = script

    def run(self):
        try:
            ok, out = self.ssh.stream_script(
                self.host,
                self.port,
                self.script,
                on_line=self.line.emit,
            )
            self.finished.emit(ok, out)
        except Exception as exc:
            self.finished.emit(False, str(exc))
