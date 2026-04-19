from __future__ import annotations
from typing import Any
from app.models_rental import Offer


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _s(v: Any) -> str | None:
    if v is None or isinstance(v, bool):
        return None
    text = str(v).strip()
    return text or None


def _country(geo: str | None) -> str | None:
    if not geo:
        return None
    if "," not in geo:
        return None
    candidate = geo.rsplit(",", 1)[-1].strip()
    return candidate or None


def _hosting_type(raw: dict) -> str | None:
    explicit = _s(raw.get("hosting_type"))
    if explicit:
        return explicit
    dc = raw.get("datacenter")
    if isinstance(dc, bool):
        return "datacenter" if dc else "consumer"
    if isinstance(dc, int) and dc in (0, 1):
        return "datacenter" if dc else "consumer"
    return None


def parse_offer(raw: dict) -> Offer:
    gpu_ram_mb = _f(raw.get("gpu_ram")) or 0.0
    gpu_total_ram_mb = _f(raw.get("gpu_total_ram")) or gpu_ram_mb * (_i(raw.get("num_gpus")) or 1)
    cpu_ram_mb = _f(raw.get("cpu_ram"))
    geo = _s(raw.get("geolocation"))
    return Offer(
        id=_i(raw.get("id")) or 0,
        ask_contract_id=_i(raw.get("ask_contract_id") or raw.get("id")) or 0,
        machine_id=_i(raw.get("machine_id")) or 0,
        host_id=_i(raw.get("host_id")),
        gpu_name=_s(raw.get("gpu_name")) or "Unknown GPU",
        num_gpus=_i(raw.get("num_gpus")) or 1,
        gpu_ram_gb=round(gpu_ram_mb / 1024.0, 2),
        gpu_total_ram_gb=round((gpu_total_ram_mb or 0) / 1024.0, 2),
        cpu_name=_s(raw.get("cpu_name")),
        cpu_cores=_i(raw.get("cpu_cores")),
        cpu_ram_gb=round(cpu_ram_mb / 1024.0, 2) if cpu_ram_mb else None,
        disk_space_gb=_f(raw.get("disk_space")) or 0.0,
        disk_bw_mbps=_f(raw.get("disk_bw")),
        inet_down_mbps=_f(raw.get("inet_down")),
        inet_up_mbps=_f(raw.get("inet_up")),
        dph_total=_f(raw.get("dph_total")) or 0.0,
        min_bid=_f(raw.get("min_bid")),
        storage_cost=_f(raw.get("storage_cost")),
        reliability=_f(raw.get("reliability2") or raw.get("reliability")),
        dlperf=_f(raw.get("dlperf")),
        dlperf_per_dphtotal=_f(raw.get("dlperf_per_dphtotal")),
        flops_per_dphtotal=_f(raw.get("flops_per_dphtotal")),
        cuda_max_good=_f(raw.get("cuda_max_good")),
        compute_cap=_i(raw.get("compute_cap")),
        verified=bool(raw.get("verified")),
        rentable=bool(raw.get("rentable")),
        rented=bool(raw.get("rented")),
        external=bool(raw.get("external")),
        geolocation=geo,
        country=_country(geo),
        datacenter=_s(raw.get("datacenter")),
        static_ip=bool(raw.get("static_ip")),
        direct_port_count=_i(raw.get("direct_port_count")),
        gpu_arch=_s(raw.get("gpu_arch")),
        duration_days=(_f(raw.get("duration")) or 0.0) / 86400.0 if raw.get("duration") else None,
        hosting_type=_hosting_type(raw),
        raw=raw,
    )
