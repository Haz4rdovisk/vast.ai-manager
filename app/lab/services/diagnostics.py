"""Rule-based classifier for actionable llama-server log diagnostics."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ServerDiagnostic:
    code: str
    title: str
    detail: str
    fix_hint: str
    fix_action: str | None = None


_RULES = [
    (
        "vram_oom",
        ["CUDA error: out of memory", "CUDA out of memory", "cudaErrorMemoryAllocation"],
        "GPU out of memory",
        "Lower GPU layers (-ngl) or pick a smaller quantization.",
    ),
    (
        "model_missing",
        ["failed to open", "No such file or directory", "error: unable to load model"],
        "Model file not found",
        "Check the model path on the instance.",
    ),
    (
        "cuda_mismatch",
        ["CUDA driver version is insufficient", "forward compatibility was attempted"],
        "CUDA driver / runtime mismatch",
        "Re-install llama.cpp to rebuild against the instance's CUDA.",
    ),
    (
        "port_busy",
        ["bind: Address already in use", "failed to bind", "error: listen"],
        "Port already in use",
        "Stop the running server or choose a different port.",
    ),
    (
        "quant_unsupported",
        ["unknown quantization", "unsupported model format"],
        "Unsupported quantization",
        "Choose a different GGUF file.",
    ),
]

_ACTIONS = {
    "vram_oom": "lower_ngl",
    "model_missing": "pick_model",
    "port_busy": "free_port",
    "cuda_mismatch": "reinstall_llamacpp",
}


def classify_server_log(log: str) -> ServerDiagnostic | None:
    if not log:
        return None

    for code, needles, title, fix_hint in _RULES:
        for needle in needles:
            if needle in log:
                return ServerDiagnostic(
                    code=code,
                    title=title,
                    detail=_extract_context(log, needle),
                    fix_hint=fix_hint,
                    fix_action=_ACTIONS.get(code),
                )

    return None


def _extract_context(log: str, needle: str, window: int = 160) -> str:
    index = log.find(needle)
    if index < 0:
        return needle

    start = max(0, index - 40)
    end = min(len(log), index + window)
    return log[start:end].strip()
