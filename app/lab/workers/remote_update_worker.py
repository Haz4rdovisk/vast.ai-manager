"""Worker to check for pending updates on remote components."""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.remote_setup import script_check_remote_updates, parse_probe_output

class RemoteUpdateWorker(QThread):
    finished = Signal(dict) # {llmfit_behind: int, llamacpp_behind: int}
    failed = Signal(str)

    def __init__(self, ssh_service, host: str, port: int, parent=None):
        super().__init__(parent)
        self.ssh = ssh_service
        self.host = host
        self.port = port

    def run(self):
        try:
            ok, output = self.ssh.run_script(self.host, self.port, script_check_remote_updates())
            if not ok:
                self.failed.emit(f"Update check failed: {output[:200]}")
                return
            
            # Simple extraction
            res = {}
            for line in output.splitlines():
                if "=" in line:
                    key, val = line.partition("=")[::2]
                    res[key.strip()] = int(val.strip()) if val.strip().isdigit() else 0
            
            self.finished.emit({
                "llmfit": res.get("LLMFIT_BEHIND", 0),
                "llamacpp": res.get("LLAMACPP_BEHIND", 0)
            })
        except Exception as e:
            self.failed.emit(str(e))
