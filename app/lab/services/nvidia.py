"""Thin wrapper around `nvidia-smi`. Keeps parsing pure so it's unit-testable."""
from __future__ import annotations
import subprocess
import sys
from app.lab.state.models import GPUInfo


def parse_nvidia_smi_csv(text: str) -> list[GPUInfo]:
    """Parse `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap
    --format=csv,noheader,nounits` output. Returns one GPUInfo per row.
    Malformed rows are silently skipped — the query above should always be
    well-formed, but drivers occasionally emit a blank first line."""
    gpus: list[GPUInfo] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        name, mem_mb, driver, compute = parts[0], parts[1], parts[2], parts[3]
        try:
            vram_gb = float(mem_mb) / 1024.0
        except ValueError:
            continue
        try:
            cc = float(compute)
            cuda_capable = cc >= 3.5
        except ValueError:
            cuda_capable = True  # NVIDIA GPU responded -> assume CUDA OK
        gpus.append(GPUInfo(
            name=name, vram_total_gb=vram_gb, driver=driver,
            cuda_capable=cuda_capable,
        ))
    return gpus


def query_nvidia_smi(timeout_s: float = 3.0) -> list[GPUInfo]:
    """Invoke nvidia-smi; return [] if the binary is missing or fails."""
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,driver_version,compute_cap",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout_s,
            creationflags=creationflags,
        )
        if res.returncode != 0:
            return []
        return parse_nvidia_smi_csv(res.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
