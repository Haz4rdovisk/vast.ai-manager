from app.models_rental import OfferQuery, OfferType, OfferSort
from app.services.offer_query import build_offer_query


def test_defaults():
    q_dict, order, limit, storage = build_offer_query(OfferQuery())
    assert q_dict["verified"] == {"eq": True}
    assert q_dict["rentable"] == {"eq": True}
    assert q_dict["rented"] == {"eq": False}
    assert q_dict["external"] == {"eq": False}
    assert order == "score-"
    assert limit == 64
    assert storage == 10.0


def test_gpu_names_single_and_multi():
    single = build_offer_query(OfferQuery(gpu_names=["RTX 4090"]))[0]
    assert single["gpu_name"] == {"eq": "RTX 4090"}

    multi = build_offer_query(OfferQuery(gpu_names=["RTX 4090", "RTX 3090"]))[0]
    assert multi["gpu_name"] == {"in": ["RTX 4090", "RTX 3090"]}


def test_numeric_bounds():
    q = OfferQuery(
        min_num_gpus=2, max_num_gpus=4,
        min_gpu_ram_gb=24, min_gpu_total_ram_gb=80,
        min_cpu_cores=8, min_cpu_ram_gb=32,
        min_disk_space_gb=200, min_disk_bw_mbps=1000,
        min_inet_down_mbps=500, min_inet_up_mbps=500,
        min_direct_port_count=10, max_dph=0.8,
        min_reliability=0.97, min_duration_days=7,
        min_compute_cap=800, min_cuda=12.0,
    )
    d, *_ = build_offer_query(q)
    assert d["num_gpus"] == {"gte": 2, "lte": 4}
    assert d["gpu_ram"] == {"gte": 24 * 1000}              # MiB in Vast units (mult 1000)
    assert d["gpu_total_ram"] == {"gte": 80 * 1000}
    assert d["cpu_cores"] == {"gte": 8}
    assert d["cpu_ram"] == {"gte": 32 * 1000}
    assert d["disk_space"] == {"gte": 200}
    assert d["disk_bw"] == {"gte": 1000}
    assert d["inet_down"] == {"gte": 500}
    assert d["inet_up"] == {"gte": 500}
    assert d["direct_port_count"] == {"gte": 10}
    assert d["dph_total"] == {"lte": 0.8}
    assert d["reliability"] == {"gte": 0.97}
    assert d["duration"] == {"gte": 7 * 86400.0}           # seconds (mult 86400)
    assert d["compute_cap"] == {"gte": 800}
    assert d["cuda_max_good"] == {"gte": 12.0}


def test_bid_type_switches_price_target_and_default():
    q = OfferQuery(offer_type=OfferType.INTERRUPTIBLE, max_bid=0.25)
    d, *_ = build_offer_query(q)
    # For bid offers we filter min_bid ceiling and leave rented free
    assert d["min_bid"] == {"lte": 0.25}
    assert "rented" not in d or d["rented"] == {"eq": False}


def test_datacenter_and_country():
    d, *_ = build_offer_query(
        OfferQuery(datacenter_only=True, country="US", region="North_America",
                   hosting_type="datacenter")
    )
    assert d["hosting_type"] == {"eq": "datacenter"}
    assert d["geolocation"] == {"eq": "US"}


def test_sort_maps_to_order_string():
    _, order, *_ = build_offer_query(OfferQuery(sort=OfferSort.DPH_ASC))
    assert order == "dph_total"
    _, order, *_ = build_offer_query(OfferQuery(sort=OfferSort.DLPERF_PER_DPH_DESC))
    assert order == "dlperf_per_dphtotal-"


def test_storage_forwarded():
    _, _, _, storage = build_offer_query(OfferQuery(storage_gib=25.0))
    assert storage == 25.0


def test_no_default_when_all_three_safety_flags_off():
    # When the user explicitly opens up the search we still pass the individual
    # constraints — build_offer_query never drops the keys, it just flips them.
    q = OfferQuery(verified=False, rentable=True, rented=False, external=True)
    d, *_ = build_offer_query(q)
    assert d["verified"] == {"eq": False}
    assert d["external"] == {"eq": True}
