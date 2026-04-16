from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class InstanceState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


class TunnelStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass
class Instance:
    id: int
    state: InstanceState
    gpu_name: str
    num_gpus: int
    gpu_ram_gb: float
    gpu_util: float | None
    gpu_temp: float | None
    vram_usage_gb: float | None
    cpu_name: str | None
    cpu_cores: int | None
    cpu_util: float | None
    ram_total_gb: float | None
    ram_used_gb: float | None
    disk_usage_gb: float | None
    disk_space_gb: float | None
    inet_down_mbps: float | None
    inet_up_mbps: float | None
    image: str | None
    dph: float
    duration_seconds: int | None
    ssh_host: str | None
    ssh_port: int | None
    # Provider / location / hardware metadata (all optional — Vast may omit any).
    geolocation: str | None = None
    country: str | None = None
    hostname: str | None = None
    host_id: int | None = None
    machine_id: int | None = None
    datacenter: str | None = None
    hosting_type: str | None = None
    cuda_max_good: float | None = None
    cpu_arch: str | None = None
    mobo_name: str | None = None
    os_version: str | None = None
    pcie_gen: float | None = None
    pcie_bw_gbps: float | None = None
    disk_bw_mbps: float | None = None
    dlperf: float | None = None
    reliability: float | None = None
    inet_down_billed_gb: float | None = None
    inet_up_billed_gb: float | None = None
    storage_total_cost: float | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class UserInfo:
    balance: float
    email: str | None = None


@dataclass
class AppConfig:
    api_key: str = ""
    refresh_interval_seconds: int = 30
    default_tunnel_port: int = 11434
    terminal_preference: str = "auto"
    auto_connect_on_activate: bool = True
    ssh_key_path: str = ""
    on_connect_script: str = ""
    model_runner_template: str = (
        "pkill -f \"llama-server\"\n"
        "nohup /opt/llama.cpp/build/bin/llama-server \\\n"
        "  -m \"{model_path}\" \\\n"
        "  --host 127.0.0.1 \\\n"
        "  --port 11434 \\\n"
        "  --jinja \\\n"
        "  -c 81920 \\\n"
        "  -ngl 99 \\\n"
        "  -fa on \\\n"
        "  -ctk bf16 \\\n"
        "  -ctv bf16 \\\n"
        "  --repeat-penalty 1.10 \\\n"
        "  -np 1 \\\n"
        "  --no-warmup \\\n"
        "  > /tmp/llama-server.log 2>&1 &"
    )
    schema_version: int = 2
