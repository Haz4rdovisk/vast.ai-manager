"""Probes a remote Vast.ai instance for setup status, models, and LLMfit data."""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.remote_setup import (
    script_check_setup, parse_probe_output,
    script_list_models, parse_model_list,
)
from app.lab.services.remote_llmfit import (
    build_system_query, build_models_query,
    parse_system, parse_models, parse_json_output,
)
from app.lab.state.models import SetupStatus, RemoteGGUF, RemoteSystem, RemoteModel


class RemoteProbeWorker(QThread):
    setup_ready = Signal(object)       # SetupStatus
    system_ready = Signal(object)      # RemoteSystem
    models_ready = Signal(list)        # list[RemoteModel]
    gguf_ready = Signal(list)          # list[RemoteGGUF]
    failed = Signal(str)

    def __init__(self, ssh_service, host: str, port: int, parent=None):
        super().__init__(parent)
        self.ssh = ssh_service
        self.host = host
        self.port = port

    def run(self):
        try:
            # 1. Probe setup status
            ok, output = self.ssh.run_script(self.host, self.port, script_check_setup())
            if not ok:
                self.failed.emit(f"SSH probe failed: {output[:200]}")
                return
            info = parse_probe_output(output)
            status = SetupStatus(
                llmfit_installed=info.get("LLMFIT_INSTALLED") == "yes",
                llmfit_serving=info.get("LLMFIT_SERVING") == "yes",
                llamacpp_installed=info.get("LLAMACPP_INSTALLED") == "yes",
                llamacpp_path=info.get("LLAMACPP_PATH", ""),
                llama_server_running=info.get("LLAMA_RUNNING") == "yes",
                llama_server_model=info.get("LLAMA_MODEL", ""),
                model_count=int(info.get("MODEL_COUNT", "0") or "0"),
                probed=True,
            )
            self.setup_ready.emit(status)

            # 2. List GGUF files
            ok2, output2 = self.ssh.run_script(self.host, self.port, script_list_models())
            if ok2:
                raw_models = parse_model_list(output2)
                gguf_list = [RemoteGGUF(**m) for m in raw_models]
                self.gguf_ready.emit(gguf_list)

            # 3. If llmfit is serving, query it for system + model recommendations
            if status.llmfit_serving:
                ok3, output3 = self.ssh.run_script(
                    self.host, self.port, build_system_query())
                if ok3:
                    data = parse_json_output(output3)
                    if data:
                        self.system_ready.emit(parse_system(data))

                ok4, output4 = self.ssh.run_script(
                    self.host, self.port, build_models_query())
                if ok4:
                    data = parse_json_output(output4)
                    if data:
                        self.models_ready.emit(parse_models(data))

        except Exception as e:
            self.failed.emit(str(e))
