"""Probe one persisted remote install job over SSH."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.lab.services.remote_setup import parse_check_job_output, script_check_job
from app.lab.state.models import JobDescriptor


class RemoteJobProbe(QThread):
    result = Signal(str, dict)

    def __init__(self, ssh_service, host: str, port: int, desc: JobDescriptor, parent=None):
        super().__init__(parent)
        self.ssh = ssh_service
        self.host = host
        self.port = port
        self.desc = desc

    def run(self) -> None:
        try:
            ok, output = self.ssh.run_script(
                self.host,
                self.port,
                script_check_job(self.desc.key),
            )
        except Exception:
            self.result.emit("MISSING", {})
            return
        if not ok:
            self.result.emit("MISSING", {})
            return
        status, state = parse_check_job_output(output)
        self.result.emit(status, state)
