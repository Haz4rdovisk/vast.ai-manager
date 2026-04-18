from __future__ import annotations
from typing import Any
from app.models_rental import OfferQuery, OfferType


def _gte(v): return {"gte": v}
def _lte(v): return {"lte": v}
def _eq(v):  return {"eq": v}


def build_offer_query(q: OfferQuery) -> tuple[dict[str, Any], str, int | None, float]:
    """Translate a UI OfferQuery into (query_dict, order_string, limit, storage_gib)
    suitable for VastAI.search_offers(query=dict, order=..., limit=..., storage=...)."""
    d: dict[str, Any] = {}

    # Safety / provenance flags — always emitted (flip, never drop)
    d["verified"] = _eq(bool(q.verified))
    d["rentable"] = _eq(bool(q.rentable))
    d["rented"]   = _eq(bool(q.rented))
    if q.external is not None:
        d["external"] = _eq(bool(q.external))

    # GPU selection
    if q.gpu_names:
        if len(q.gpu_names) == 1:
            d["gpu_name"] = _eq(q.gpu_names[0])
        else:
            d["gpu_name"] = {"in": list(q.gpu_names)}
    if q.min_num_gpus is not None or q.max_num_gpus is not None:
        bounds: dict[str, int] = {}
        if q.min_num_gpus is not None:
            bounds["gte"] = int(q.min_num_gpus)
        if q.max_num_gpus is not None:
            bounds["lte"] = int(q.max_num_gpus)
        d["num_gpus"] = bounds
    if q.min_gpu_ram_gb is not None:
        d["gpu_ram"] = _gte(int(q.min_gpu_ram_gb * 1000))          # mult 1000
    if q.min_gpu_total_ram_gb is not None:
        d["gpu_total_ram"] = _gte(int(q.min_gpu_total_ram_gb * 1000))
    if q.gpu_arch:
        d["gpu_arch"] = _eq(q.gpu_arch)
    if q.min_compute_cap is not None:
        d["compute_cap"] = _gte(int(q.min_compute_cap))
    if q.min_cuda is not None:
        d["cuda_max_good"] = _gte(float(q.min_cuda))
    if q.min_gpu_mem_bw is not None:
        d["gpu_mem_bw"] = _gte(float(q.min_gpu_mem_bw))
    if q.gpu_display_active is not None:
        d["gpu_display_active"] = _eq(bool(q.gpu_display_active))

    # CPU
    if q.min_cpu_cores is not None:
        d["cpu_cores"] = _gte(int(q.min_cpu_cores))
    if q.min_cpu_ram_gb is not None:
        d["cpu_ram"] = _gte(int(q.min_cpu_ram_gb * 1000))
    if q.cpu_arch:
        d["cpu_arch"] = _eq(q.cpu_arch)
    if q.has_avx is not None:
        d["has_avx"] = _eq(bool(q.has_avx))

    # Disk / net
    if q.min_disk_space_gb is not None:
        d["disk_space"] = _gte(float(q.min_disk_space_gb))
    if q.min_disk_bw_mbps is not None:
        d["disk_bw"] = _gte(float(q.min_disk_bw_mbps))
    if q.min_inet_down_mbps is not None:
        d["inet_down"] = _gte(float(q.min_inet_down_mbps))
    if q.min_inet_up_mbps is not None:
        d["inet_up"] = _gte(float(q.min_inet_up_mbps))
    if q.min_direct_port_count is not None:
        d["direct_port_count"] = _gte(int(q.min_direct_port_count))
    if q.static_ip is not None:
        d["static_ip"] = _eq(bool(q.static_ip))

    # Pricing
    if q.offer_type == OfferType.INTERRUPTIBLE and q.max_bid is not None:
        d["min_bid"] = _lte(float(q.max_bid))
    if q.max_dph is not None:
        d["dph_total"] = _lte(float(q.max_dph))
    if q.max_storage_cost_per_gb_month is not None:
        d["storage_cost"] = _lte(float(q.max_storage_cost_per_gb_month))
    if q.max_inet_down_cost is not None:
        d["inet_down_cost"] = _lte(float(q.max_inet_down_cost))
    if q.max_inet_up_cost is not None:
        d["inet_up_cost"] = _lte(float(q.max_inet_up_cost))

    # Reliability / host / location
    if q.min_reliability is not None:
        d["reliability"] = _gte(float(q.min_reliability))
    if q.min_duration_days is not None:
        d["duration"] = _gte(float(q.min_duration_days) * 86400.0)
    if q.country:
        d["geolocation"] = _eq(q.country)
    if q.region:
        # Georegion — Vast recognizes `geolocation` tokens like "North_America"
        # as region when resolved server-side. We emit via same key.
        d.setdefault("geolocation", _eq(q.region))
    if q.datacenter_only and not q.hosting_type:
        d["hosting_type"] = _eq("datacenter")
    if q.hosting_type:
        d["hosting_type"] = _eq(q.hosting_type)
    if q.host_id is not None:
        d["host_id"] = _eq(int(q.host_id))
    if q.machine_id is not None:
        d["machine_id"] = _eq(int(q.machine_id))
    if q.cluster_id is not None:
        d["cluster_id"] = _eq(int(q.cluster_id))

    return d, q.sort.value, q.limit, q.storage_gib
