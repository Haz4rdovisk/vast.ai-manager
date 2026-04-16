"""Aggregates known health problems across hardware/runtime/library into a
single list of DiagnosticsItem. UX-ready messages."""
from __future__ import annotations
from app.lab.state.models import (
    DiagnosticsItem, HardwareSpec, ModelFile, RuntimeStatus,
)


def collect_diagnostics(hw: HardwareSpec, runtime: RuntimeStatus,
                        library: list[ModelFile]) -> list[DiagnosticsItem]:
    out: list[DiagnosticsItem] = []

    if not runtime.installed:
        out.append(DiagnosticsItem(
            id="runtime_missing", level="err",
            title="llama.cpp runtime not found",
            detail="Download and install a prebuilt binary, or point the Runtime "
                   "view at an existing install.",
            fix_action="open_runtime",
        ))
    elif not runtime.validated:
        out.append(DiagnosticsItem(
            id="runtime_unverified", level="warn",
            title="Runtime binary found but version unknown",
            detail="The binary didn't report a version \u2014 it may be outdated or "
                   "incompatible.",
            fix_action="open_runtime",
        ))

    if not hw.gpus:
        level = "info" if hw.ram_total_gb >= 32 else "warn"
        out.append(DiagnosticsItem(
            id="no_gpu", level=level,
            title="No CUDA GPU detected",
            detail="Inference will run on CPU. Fine for small models; "
                   "bigger models will be slow.",
        ))
    elif runtime.installed and runtime.backend == "cpu" and hw.gpus:
        out.append(DiagnosticsItem(
            id="runtime_cpu_only", level="warn",
            title="Runtime compiled without GPU support",
            detail="You have a CUDA GPU, but the llama.cpp binary only supports CPU. "
                   "Install a CUDA-enabled build to unlock offload.",
            fix_action="open_runtime",
        ))

    if hw.disk_free_gb and hw.disk_free_gb < 20:
        out.append(DiagnosticsItem(
            id="low_disk", level="warn",
            title="Low free disk space",
            detail=f"Only {hw.disk_free_gb:.0f} GB free. Most GGUF files are 4\u201330 GB.",
        ))

    if hw.ram_total_gb and hw.ram_total_gb < 16:
        out.append(DiagnosticsItem(
            id="low_ram", level="warn",
            title="Low system RAM",
            detail="Under 16 GB \u2014 large contexts and bigger models will struggle.",
        ))

    bad = [m for m in library if not m.valid]
    if bad:
        sample = ", ".join(m.name for m in bad[:3])
        out.append(DiagnosticsItem(
            id="invalid_models", level="warn",
            title=f"{len(bad)} model file(s) unreadable",
            detail=f"Failed to parse: {sample}. "
                   f"Files may be incomplete or corrupted.",
            fix_action="rescan_library",
        ))

    return out
