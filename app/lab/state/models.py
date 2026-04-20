"""Plain dataclasses for the Lab V2 state tree — remote-instance-first."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

HealthLevel = Literal["ok", "warn", "err", "info", "unknown"]


@dataclass
class RemoteGPU:
    name: str
    vram_gb: float | None = None


@dataclass
class RemoteSystem:
    """Hardware info from LLMfit /api/v1/system or SSH probing."""
    cpu_name: str = ""
    cpu_cores: int = 0
    cpu_usage_pct: float = 0.0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    ram_usage_pct: float = 0.0
    has_gpu: bool = False
    gpu_name: str | None = None
    gpu_vram_gb: float | None = None
    gpu_usage_pct: float = 0.0
    gpu_vram_usage_pct: float = 0.0
    gpu_temp: float = 0.0
    gpu_count: int = 0
    backend: str = ""
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_usage_pct: float = 0.0
    net_rx_kbps: float = 0.0
    net_tx_kbps: float = 0.0
    uptime_seconds: int = 0
    gpus: list[RemoteGPU] = field(default_factory=list)


@dataclass
class RemoteModel:
    """A model recommendation from LLMfit /api/v1/models."""
    name: str
    provider: str = ""
    parameter_count: str = ""
    params_b: float = 0.0
    context_length: int = 0
    use_case: str = ""
    category: str = ""
    fit_level: str = ""          # "perfect"|"good"|"marginal"|"too_tight"
    fit_label: str = ""
    run_mode: str = ""           # "gpu"|"cpu"|"partial"
    score: float = 0.0
    score_components: dict = field(default_factory=dict)
    estimated_tps: float = 0.0
    runtime: str = ""
    runtime_label: str = ""
    best_quant: str = ""
    memory_required_gb: float = 0.0
    memory_available_gb: float = 0.0
    utilization_pct: float = 0.0
    notes: list[str] = field(default_factory=list)
    gguf_sources: list[str] = field(default_factory=list)


@dataclass
class RemoteGGUF:
    """A GGUF file found on the remote instance."""
    path: str
    filename: str
    size_bytes: int = 0
    size_display: str = ""


@dataclass
class ScoredCatalogModel:
    """Flat DTO for scored catalog entries kept in LabStore."""
    name: str
    provider: str
    params_b: float
    best_quant: str
    use_case: str
    fit_level: str
    fit_label: str
    run_mode: str
    score: float
    utilization_pct: float
    memory_required_gb: float
    memory_available_gb: float
    estimated_tps: float
    gguf_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SetupStatus:
    """Tracks what's installed on the remote instance."""
    llmfit_installed: bool = False
    llmfit_serving: bool = False
    llamacpp_installed: bool = False
    llamacpp_path: str = ""
    llama_server_running: bool = False
    llama_server_model: str = ""
    llama_server_port: int = 11434
    model_count: int = 0
    probed: bool = False        # True after first probe completes


@dataclass
class ServerParams:
    """Full llama-server parameter configuration."""
    model_path: str = ""
    context_length: int = 4096
    gpu_layers: int = 99
    threads: int = 0               # 0 = auto
    batch_size: int = 512
    parallel_requests: int = 1
    repeat_penalty: float = 1.10
    host: str = "127.0.0.1"
    port: int = 11434
    flash_attention: bool = True
    kv_cache_type: str = "bf16"    # bf16|f16|q8_0|q4_0
    extra_args: str = ""
    no_warmup: bool = True


@dataclass
class InstallJob:
    kind: str
    stage: str
    percent: int = 0
    log_tail: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class DownloadJob:
    repo_id: str
    filename: str
    percent: int = 0
    bytes_downloaded: int = 0
    bytes_total: int = 0
    speed: str = ""
    error: str = ""
    done: bool = False


@dataclass
class LabInstanceState:
    """Grouped state for a single remote instance in the Lab."""
    iid: int
    system: RemoteSystem = field(default_factory=RemoteSystem)
    models: list[RemoteModel] = field(default_factory=list)
    gguf: list[RemoteGGUF] = field(default_factory=list)
    scored_models: list[ScoredCatalogModel] = field(default_factory=list)
    setup: SetupStatus = field(default_factory=SetupStatus)
    server_params: ServerParams = field(default_factory=ServerParams)
    model_configs: dict[str, ServerParams] = field(default_factory=dict)
    install_job: InstallJob | None = None
    download_job: DownloadJob | None = None
    busy_keys: set[str] = field(default_factory=set)


@dataclass
class DiagnosticsItem:
    id: str
    level: HealthLevel
    title: str
    detail: str
    fix_action: str | None = None


@dataclass
class JobDescriptor:
    """Durable descriptor for an install/download job on a remote instance."""

    key: str
    iid: int
    repo_id: str
    filename: str
    quant: str
    size_bytes: int
    needs_llamacpp: bool
    remote_state_path: str
    remote_log_path: str
    started_at: float
    stage: str = "starting"
    percent: int = 0
    bytes_downloaded: int = 0
    speed: str = ""
    error: str | None = None


def build_job_key(iid: int, repo_id: str, quant: str) -> str:
    """Build a stable, filesystem-safe key for a remote job."""
    slug = repo_id.replace("/", "-").lower()
    return f"{iid}-{slug}-{quant.lower()}"
