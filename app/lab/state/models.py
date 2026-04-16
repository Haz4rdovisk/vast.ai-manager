"""Plain dataclasses for the Lab state tree. No Qt. Serializable via asdict."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

HealthLevel = Literal["ok", "warn", "err", "info", "unknown"]


@dataclass
class GPUInfo:
    name: str
    vram_total_gb: float
    driver: str | None = None
    cuda_capable: bool = False


@dataclass
class HardwareSpec:
    os_name: str = ""
    os_version: str = ""
    cpu_name: str = ""
    cpu_cores_physical: int = 0
    cpu_cores_logical: int = 0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    gpus: list[GPUInfo] = field(default_factory=list)
    # Best-guess backend label: "cuda", "rocm", "metal", "cpu".
    best_backend: str = "cpu"


@dataclass
class RuntimeStatus:
    installed: bool = False
    version: str | None = None
    binary_path: str | None = None
    backend: str | None = None     # "cuda"|"cpu"|...
    validated: bool = False
    error: str | None = None


@dataclass
class ModelFile:
    path: str
    name: str               # display name ("Qwen2.5-7B-Instruct-Q4_K_M")
    size_bytes: int
    architecture: str = ""  # from GGUF header ("llama", "qwen2", ...)
    param_count_b: float = 0.0
    context_length: int = 0
    quant: str = ""         # "Q4_K_M", "Q8_0", ...
    valid: bool = True
    error: str | None = None


@dataclass
class CatalogEntry:
    id: str                   # stable key, e.g. "qwen2.5-7b-instruct-q4km"
    family: str               # "Qwen2.5"
    display_name: str
    params_b: float
    quant: str
    repo_id: str              # HF repo
    filename: str             # GGUF filename in repo
    approx_size_gb: float
    approx_vram_gb: float     # full GPU offload
    approx_ram_gb: float      # full CPU
    context_length: int
    use_cases: list[str] = field(default_factory=list)  # ["coding","chat","long_context"]
    quality_tier: int = 3     # 1..5
    notes: str = ""


@dataclass
class Recommendation:
    entry: CatalogEntry
    fit: Literal["excellent", "good", "tight", "not_recommended"]
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    model_name: str
    timestamp: float
    tokens_per_sec: float
    ttft_ms: float
    prompt_eval_tok_per_sec: float
    ram_peak_gb: float | None = None
    vram_peak_gb: float | None = None


@dataclass
class DiagnosticsItem:
    id: str
    level: HealthLevel
    title: str
    detail: str
    fix_action: str | None = None   # handler key, e.g. "install_runtime"
