"""Local hardware detection. psutil for CPU/RAM/disk; nvidia-smi for GPUs;
pure helpers below are Qt-free for testing."""
from __future__ import annotations
import platform
from app.lab.services.nvidia import query_nvidia_smi
from app.lab.state.models import HardwareSpec, GPUInfo


def pick_best_backend(os_name: str, gpus: list[GPUInfo]) -> str:
    if any(g.cuda_capable for g in gpus):
        return "cuda"
    if os_name == "Darwin":
        return "metal"
    return "cpu"


def detect_hardware() -> HardwareSpec:
    """Blocking detection. Safe to call from a worker thread."""
    import psutil
    os_name = platform.system() or "Unknown"
    os_version = platform.version() or platform.release() or ""
    cpu_name = platform.processor() or platform.machine() or "CPU"
    cores_phys = psutil.cpu_count(logical=False) or 0
    cores_log = psutil.cpu_count(logical=True) or 0
    vm = psutil.virtual_memory()
    ram_total = vm.total / (1024 ** 3)
    ram_avail = vm.available / (1024 ** 3)
    # Disk: root of the current drive — good enough; users can refine later.
    disk_root = "/" if os_name != "Windows" else "C:\\"
    try:
        du = psutil.disk_usage(disk_root)
        disk_total = du.total / (1024 ** 3)
        disk_free = du.free / (1024 ** 3)
    except OSError:
        disk_total = disk_free = 0.0

    gpus = query_nvidia_smi()
    return HardwareSpec(
        os_name=os_name,
        os_version=os_version,
        cpu_name=cpu_name.strip(),
        cpu_cores_physical=cores_phys,
        cpu_cores_logical=cores_log,
        ram_total_gb=ram_total,
        ram_available_gb=ram_avail,
        disk_total_gb=disk_total,
        disk_free_gb=disk_free,
        gpus=gpus,
        best_backend=pick_best_backend(os_name, gpus),
    )
