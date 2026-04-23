from __future__ import annotations
from typing import Any
from app.models_rental import OfferQuery, OfferSort, OfferType


def _gte(v): return {"gte": v}
def _lte(v): return {"lte": v}
def _eq(v):  return {"eq": v}
def _enum_value(v): return getattr(v, "value", v)


_REGION_COUNTRIES: dict[str, list[str]] = {
    "AF": "DZ,AO,BJ,BW,BF,BI,CM,CV,CF,TD,KM,CD,CG,DJ,EG,GQ,ER,ET,GA,GM,GH,GN,GW,KE,LS,LR,LY,MW,MA,ML,MR,MU,MZ,NA,NE,NG,RW,SH,ST,SN,SC,SL,SO,ZA,SS,SD,SZ,TZ,TG,TN,UG,YE,ZM,ZW".split(","),
    "AS": "AE,AM,AZ,BD,BH,BN,BT,MM,KH,KP,PH,IN,ID,IR,IQ,IL,JP,JO,KZ,MY,MV,MN,NP,KR,PK,QA,SA,SG,LK,SY,TW,TJ,TH,TR,TM,VN,HK,CN,OM".split(","),
    "EU": "AL,AD,AT,BY,BE,BA,BG,HR,CY,CZ,DK,EE,FI,FR,GE,DE,GR,HU,IS,IT,LV,LI,LT,LU,MT,MD,MC,ME,NL,NO,PL,PT,RO,RU,RS,SK,SI,ES,SE,CH,UA,GB,VA,MK".split(","),
    "LC": "AG,AR,BS,BB,BZ,BO,BR,CL,CO,CR,CU,DO,EC,SV,GY,HT,HN,JM,MX,NI,PA,PY,PE,PR,RD,SUR,TT,UR,VZ".split(","),
    "NA": ["CA", "US"],
    "OC": "AU,FJ,GU,KI,MH,FM,NR,NZ,PG,PW,SL,TO,TV,VU".split(","),
}

_REGION_ALIASES = {
    "north_america": "NA",
    "north america": "NA",
    "europe": "EU",
    "asia": "AS",
    "south_america": "LC",
    "south america": "LC",
    "latin_america": "LC",
    "latin america": "LC",
    "oceania": "OC",
    "africa": "AF",
}


def _region_countries(region: str | None) -> list[str]:
    if not region:
        return []
    token = str(region).strip()
    key = token.upper()
    if key not in _REGION_COUNTRIES:
        key = _REGION_ALIASES.get(token.lower(), "")
    return list(_REGION_COUNTRIES.get(key, []))


def _order_for(q: OfferQuery) -> str:
    order = str(_enum_value(q.sort))
    offer_type = str(_enum_value(q.offer_type))
    if offer_type == OfferType.INTERRUPTIBLE.value:
        if order == OfferSort.DPH_ASC.value:
            return "min_bid"
        if order == OfferSort.DPH_DESC.value:
            return "min_bid-"
    return order


def build_offer_query(q: OfferQuery) -> tuple[dict[str, Any], str, int | None, float]:
    """Translate a UI OfferQuery into (query_dict, order_string, limit, storage_gib)
    suitable for VastAI.search_offers(query=dict, order=..., limit=..., storage=...)."""
    d: dict[str, Any] = {}

    # Safety / provenance flags. None means "include both states".
    if q.verified is not None:
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
    offer_type = _enum_value(q.offer_type)
    if offer_type == OfferType.INTERRUPTIBLE.value and q.max_bid is not None:
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
    if q.region and "geolocation" not in d:
        countries = _region_countries(q.region)
        if countries:
            d["geolocation"] = {"in": countries}
    if q.datacenter_only or q.hosting_type == "datacenter":
        d["datacenter"] = _eq(True)
    elif q.hosting_type == "consumer":
        d["datacenter"] = _eq(False)
    if q.host_id is not None:
        d["host_id"] = _eq(int(q.host_id))
    if q.machine_id is not None:
        d["machine_id"] = _eq(int(q.machine_id))
    if q.cluster_id is not None:
        d["cluster_id"] = _eq(int(q.cluster_id))

    return d, _order_for(q), q.limit, q.storage_gib
