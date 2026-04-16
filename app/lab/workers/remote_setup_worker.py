"""Worker for long-running remote setup operations: install, download, launch."""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.remote_setup import (
    script_install_llmfit, script_start_llmfit_serve,
    script_install_llamacpp, script_download_model,
    script_stop_llama_server, script_delete_model,
)
from app.lab.services.model_params import build_launch_script


class RemoteSetupWorker(QThread):
    """Runs a single remote operation. Reusable for different actions."""
    progress = Signal(str)          # status message
    finished = Signal(bool, str)    # success, output

    def __init__(self, ssh_service, host: str, port: int,
                 action: str, **kwargs):
        super().__init__()
        self.ssh = ssh_service
        self.host = host
        self.port = port
        self.action = action
        self.kwargs = kwargs

    def run(self):
        try:
            script = self._build_script()
            self.progress.emit(f"Running: {self.action}...")
            ok, output = self.ssh.run_script(self.host, self.port, script)
            self.finished.emit(ok, output)
        except Exception as e:
            self.finished.emit(False, str(e))

    def _build_script(self) -> str:
        if self.action == "install_llmfit":
            return script_install_llmfit()
        elif self.action == "start_llmfit":
            return script_start_llmfit_serve()
        elif self.action == "install_llamacpp":
            return script_install_llamacpp()
        elif self.action == "download_model":
            return script_download_model(
                self.kwargs["repo_id"],
                self.kwargs["filename"],
                self.kwargs.get("dest_dir", "/workspace"),
            )
        elif self.action == "launch_server":
            return build_launch_script(
                self.kwargs["params"],
                self.kwargs.get("binary_path", ""),
            )
        elif self.action == "stop_server":
            return script_stop_llama_server()
        elif self.action == "delete_model":
            return script_delete_model(self.kwargs["path"])
        else:
            raise ValueError(f"Unknown action: {self.action}")
