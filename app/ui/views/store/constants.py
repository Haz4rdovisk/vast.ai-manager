"""Static lists used by the Store filter UI. Values here match the strings
the Vast API returns for the corresponding fields — do not localize."""
from __future__ import annotations
from app.models_rental import OfferQuery

# Top consumer + datacenter GPUs in 2026 — a curated subset; other models still
# reachable via the "All GPUs" dropdown using `show_instance_filters` output.
POPULAR_GPUS: list[str] = [
    "RTX 5090", "RTX 5080", "RTX 4090", "RTX 4080", "RTX 3090", "RTX 3080",
    "RTX 6000 Ada", "L40S", "L40", "L4", "A100 SXM4 80GB", "A100 PCIE 80GB",
    "A100 SXM4 40GB", "H100 SXM5 80GB", "H100 PCIE", "H100 NVL", "H200",
    "B200", "A6000", "A5000", "A40", "V100",
]

GPU_ARCHS: list[tuple[str, str]] = [
    ("Any", ""), ("Blackwell", "blackwell"), ("Hopper", "hopper"),
    ("Ada Lovelace", "ada"), ("Ampere", "ampere"),
    ("Turing", "turing"), ("Volta", "volta"),
]

CPU_ARCHS: list[tuple[str, str]] = [
    ("Any", ""), ("x86_64", "amd64"), ("ARM64", "arm64"),
]

# Vast georegion tokens (server-side); country codes pass through as-is.
REGIONS: list[tuple[str, str]] = [
    ("All Regions", ""),
    ("North America", "North_America"),
    ("Europe", "Europe"),
    ("Asia", "Asia"),
    ("South America", "South_America"),
    ("Oceania", "Oceania"),
    ("Africa", "Africa"),
]

COUNTRIES: list[tuple[str, str]] = [
    ("Any", ""),
    ("United States", "US"), ("Canada", "CA"), ("Mexico", "MX"),
    ("Brazil", "BR"), ("Argentina", "AR"), ("Chile", "CL"),
    ("United Kingdom", "GB"), ("Germany", "DE"), ("France", "FR"),
    ("Netherlands", "NL"), ("Sweden", "SE"), ("Finland", "FI"),
    ("Norway", "NO"), ("Iceland", "IS"), ("Poland", "PL"), ("Spain", "ES"),
    ("Italy", "IT"), ("Portugal", "PT"), ("Romania", "RO"), ("Bulgaria", "BG"),
    ("Ukraine", "UA"), ("Estonia", "EE"), ("Ireland", "IE"),
    ("Japan", "JP"), ("South Korea", "KR"), ("Taiwan", "TW"),
    ("Singapore", "SG"), ("Hong Kong", "HK"), ("India", "IN"),
    ("Australia", "AU"), ("New Zealand", "NZ"),
    ("UAE", "AE"), ("Saudi Arabia", "SA"), ("Israel", "IL"),
    ("South Africa", "ZA"),
]

HOSTING_TYPES: list[tuple[str, str]] = [
    ("Any", ""), ("Datacenter", "datacenter"),
    ("Consumer", "consumer"), ("Cluster", "cluster"),
]

PRESETS: dict[str, OfferQuery] = {
    "LLM Inference 24GB+": OfferQuery(
        min_gpu_ram_gb=24, min_num_gpus=1, min_reliability=0.97,
        min_inet_down_mbps=300,
    ),
    "LLM Training 80GB+": OfferQuery(
        min_gpu_ram_gb=80, min_num_gpus=2, min_cpu_ram_gb=256,
        min_disk_space_gb=500, min_inet_down_mbps=1000,
        min_reliability=0.98, datacenter_only=True,
    ),
    "Diffusion 16GB": OfferQuery(
        min_gpu_ram_gb=16, min_num_gpus=1, max_dph=0.6,
        min_reliability=0.95,
    ),
    "Cheap CUDA dev": OfferQuery(
        min_gpu_ram_gb=8, max_dph=0.25, min_reliability=0.95,
    ),
    "8x H100 cluster": OfferQuery(
        gpu_names=["H100 SXM5 80GB", "H100 NVL", "H200"],
        min_num_gpus=8, datacenter_only=True,
    ),
}
