from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class OfferType(str, Enum):
    ON_DEMAND = "on-demand"
    INTERRUPTIBLE = "bid"       # Vast SDK spells it "bid"
    RESERVED = "reserved"


class OfferSort(str, Enum):
    SCORE_DESC = "score-"
    DPH_ASC = "dph_total"
    DPH_DESC = "dph_total-"
    DLPERF_DESC = "dlperf-"
    DLPERF_PER_DPH_DESC = "dlperf_per_dphtotal-"
    FLOPS_PER_DPH_DESC = "flops_per_dphtotal-"
    RELIABILITY_DESC = "reliability-"
    INET_DOWN_DESC = "inet_down-"
    NUM_GPUS_DESC = "num_gpus-"
    GPU_RAM_DESC = "gpu_ram-"
    DURATION_DESC = "duration-"


@dataclass
class Offer:
    """Parsed Vast offer row (bundle)."""
    id: int
    ask_contract_id: int
    machine_id: int
    host_id: int | None
    gpu_name: str
    num_gpus: int
    gpu_ram_gb: float
    gpu_total_ram_gb: float
    cpu_name: str | None
    cpu_cores: int | None
    cpu_ram_gb: float | None
    disk_space_gb: float
    disk_bw_mbps: float | None
    inet_down_mbps: float | None
    inet_up_mbps: float | None
    dph_total: float
    min_bid: float | None
    storage_cost: float | None
    reliability: float | None
    dlperf: float | None
    dlperf_per_dphtotal: float | None
    flops_per_dphtotal: float | None
    cuda_max_good: float | None
    compute_cap: int | None
    verified: bool
    rentable: bool
    rented: bool
    external: bool
    geolocation: str | None
    country: str | None
    datacenter: str | None
    static_ip: bool
    direct_port_count: int | None
    gpu_arch: str | None
    duration_days: float | None
    hosting_type: str | None
    raw: dict = field(default_factory=dict)

    def effective_price(self) -> float:
        """Price shown to user: dph_total for on-demand, min_bid for interruptible."""
        return self.dph_total


@dataclass
class Template:
    id: int
    hash_id: str
    name: str
    image: str
    description: str | None = None
    recommended: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class SshKey:
    id: int
    public_key: str
    label: str | None = None


@dataclass
class OfferQuery:
    """User-facing filter state. Translate to SDK query via build_offer_query."""
    # Offer type / sort / pagination
    offer_type: OfferType = OfferType.ON_DEMAND
    sort: OfferSort = OfferSort.SCORE_DESC
    limit: int = 64
    storage_gib: float = 10.0

    # Default safety flags (no_default=False semantics)
    verified: bool = True
    rentable: bool = True
    rented: bool = False
    external: bool | None = False  # allow external marketplace

    # GPU
    gpu_names: list[str] = field(default_factory=list)    # e.g. ["RTX 4090", "RTX 3090"]
    min_num_gpus: int | None = None
    max_num_gpus: int | None = None
    min_gpu_ram_gb: float | None = None           # per-GPU
    min_gpu_total_ram_gb: float | None = None     # across all GPUs
    gpu_arch: str | None = None                   # "ampere", "ada", "hopper", "blackwell"
    min_compute_cap: int | None = None            # e.g. 800 -> 8.0
    min_cuda: float | None = None                 # cuda_max_good
    min_gpu_mem_bw: float | None = None           # GB/s
    gpu_display_active: bool | None = None

    # CPU
    min_cpu_cores: int | None = None
    min_cpu_ram_gb: float | None = None
    cpu_arch: str | None = None                   # x86_64 / arm64
    has_avx: bool | None = None

    # Disk / network
    min_disk_space_gb: float | None = None
    min_disk_bw_mbps: float | None = None
    min_inet_down_mbps: float | None = None
    min_inet_up_mbps: float | None = None
    min_direct_port_count: int | None = None
    static_ip: bool | None = None

    # Pricing
    max_dph: float | None = None                  # USD per hour
    max_bid: float | None = None                  # interruptible bid ceiling
    max_storage_cost_per_gb_month: float | None = None
    max_inet_down_cost: float | None = None
    max_inet_up_cost: float | None = None

    # Reliability / host / location
    min_reliability: float | None = None          # 0..1
    min_duration_days: float | None = None
    country: str | None = None                    # ISO-ish "US"
    region: str | None = None                     # georegion "North_America"
    datacenter_only: bool = False
    hosting_type: str | None = None               # "datacenter" | "consumer" | "cluster"
    host_id: int | None = None
    machine_id: int | None = None
    cluster_id: int | None = None


@dataclass
class RentRequest:
    offer_id: int
    image: str | None = None                      # docker image
    template_hash: str | None = None              # vast template hash
    disk_gb: float = 10.0
    label: str | None = None
    ssh_key_id: int | None = None
    env: dict[str, str] = field(default_factory=dict)
    onstart_cmd: str | None = None
    jupyter_lab: bool = False
    jupyter_dir: str | None = None
    price: float | None = None                    # for interruptible bid
    runtype: str | None = None                    # "ssh" | "jupyter" | "args"
    args: list[str] | None = None
    force: bool = False
    cancel_unavail: bool = False


@dataclass
class RentResult:
    ok: bool
    new_contract_id: int | None = None
    message: str = ""
    raw: dict = field(default_factory=dict)
