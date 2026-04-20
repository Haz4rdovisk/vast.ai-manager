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
            from app.lab.services.remote_setup import script_master_probe
            # Run one unified script
            ok, output = self.ssh.run_script(self.host, self.port, script_master_probe())
            if not ok:
                self.failed.emit(f"SSH probe failed: {output[:200]}")
                return

            # Parse blocks
            blocks = {}
            current_block = None
            block_content = []
            
            for line in output.splitlines():
                if line.endswith("_START===") and line.startswith("==="):
                    current_block = line.strip("=").replace("_START", "")
                    block_content = []
                    continue
                if line.endswith("_END===") and line.startswith("==="):
                    if current_block:
                        blocks[current_block] = "\n".join(block_content)
                    current_block = None
                    continue
                if current_block:
                    block_content.append(line)

            # 1. Process Setup status
            setup_out = blocks.get("SETUP", "")
            if setup_out:
                info = parse_probe_output(setup_out)
                status = SetupStatus(
                    llmfit_installed=info.get("LLMFIT_INSTALLED") == "yes",
                    llmfit_serving=info.get("LLMFIT_SERVING") == "yes",
                    llamacpp_installed=info.get("LLAMACPP_INSTALLED") == "yes",
                    llamacpp_path=info.get("LLAMACPP_PATH", ""),
                    llama_server_running=info.get("LLAMA_RUNNING") == "yes",
                    llama_server_model=info.get("LLAMA_MODEL", ""),
                    llama_server_port=int(info.get("LLAMA_PORT", "11434") or "11434"),
                    model_count=int(info.get("MODEL_COUNT", "0") or "0"),
                    probed=True,
                )
                self.setup_ready.emit(status)

            # 2. Process GGUF models
            models_out = blocks.get("MODELS", "")
            if models_out:
                raw_models = parse_model_list("===MODELS_START===\n" + models_out + "\n===MODELS_END===")
                gguf_list = [RemoteGGUF(**m) for m in raw_models]
                self.gguf_ready.emit(gguf_list)

            # 3. Process LLMfit System Recommendation
            sys_out = blocks.get("SYSTEM", "")
            if sys_out:
                data = parse_json_output(sys_out)
                if data:
                    self.system_ready.emit(parse_system(data))

            # 4. Process LLMfit Model Recommendations
            rec_out = blocks.get("RECOMMEND", "")
            if rec_out:
                data = parse_json_output(rec_out)
                if data:
                    self.models_ready.emit(parse_models(data))

            # 5. Process Raw Telemetry (High Priority Fallback for Gauges)
            tel_out = blocks.get("TELEMETRY", "")
            if tel_out:
                info = parse_probe_output(tel_out)
                # Helper to merge with existing system info if any
                def _safe_float(k):
                    v = info.get(k, "0").replace("%", "").strip()
                    return float(v) if v and v[0].isdigit() or v.startswith(".") else 0.0

                # If system_ready wasn't emitted by LLMfit, we emit a basic one now
                # In a real app, we'd merge these. For now, let's update specific fields.
                # Actually, the store handles the update if we emit a system object.
                sys = RemoteSystem(
                    cpu_cores=int(_safe_float("CPU_CORES")),
                    cpu_usage_pct=_safe_float("CPU_LOAD"),
                    ram_total_gb=_safe_float("RAM_TOTAL_MB") / 1024,
                    ram_usage_pct=_safe_float("RAM_PERCENT"),
                    gpu_usage_pct=_safe_float("GPU_LOAD"),
                    gpu_name=info.get("GPU_NAME", "GPU"),
                    gpu_temp=_safe_float("GPU_TEMP"),
                    gpu_vram_usage_pct=_safe_float("VRAM_PERCENT"),
                    gpu_vram_gb=_safe_float("VRAM_TOTAL_MB") / 1024,
                    disk_total_gb=_safe_float("DISK_TOTAL_MB") / 1024,
                    disk_used_gb=_safe_float("DISK_USED_MB") / 1024,
                    disk_usage_pct=_safe_float("DISK_PERCENT"),
                    net_rx_kbps=_safe_float("NET_RX_KBPS"),
                    net_tx_kbps=_safe_float("NET_TX_KBPS"),
                    uptime_seconds=int(info.get("UPTIME_SEC", "0")),
                    has_gpu=info.get("GPU_LOAD") is not None
                )
                self.system_ready.emit(sys)

        except Exception as e:
            self.failed.emit(str(e))
