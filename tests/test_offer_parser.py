from app.services.offer_parser import parse_offer


def test_parse_minimal():
    raw = {
        "id": 1234, "ask_contract_id": 1234, "machine_id": 777, "host_id": 99,
        "gpu_name": "RTX 4090", "num_gpus": 2,
        "gpu_ram": 24564, "gpu_total_ram": 49128,
        "cpu_name": "AMD EPYC 7V12", "cpu_cores": 32, "cpu_ram": 131072,
        "disk_space": 500, "disk_bw": 2400,
        "inet_down": 1400, "inet_up": 1200,
        "dph_total": 0.85, "min_bid": 0.32, "storage_cost": 0.10,
        "reliability2": 0.988, "dlperf": 28.1,
        "dlperf_per_dphtotal": 33.0, "flops_per_dphtotal": 120.5,
        "cuda_max_good": 12.4, "compute_cap": 890, "gpu_arch": "ada",
        "verified": True, "rentable": True, "rented": False,
        "external": False, "geolocation": "US-California, US",
        "datacenter": "NV-DC", "static_ip": True, "direct_port_count": 32,
        "duration": 20 * 86400, "hosting_type": "datacenter",
    }
    o = parse_offer(raw)
    assert o.id == 1234
    assert o.gpu_name == "RTX 4090"
    assert o.num_gpus == 2
    assert abs(o.gpu_ram_gb - 24.0) < 0.5
    assert abs(o.gpu_total_ram_gb - 48.0) < 1.0
    assert o.cpu_cores == 32
    assert abs(o.cpu_ram_gb - 128.0) < 1.0
    assert o.dph_total == 0.85
    assert o.min_bid == 0.32
    assert o.reliability == 0.988
    assert o.country == "US"
    assert o.gpu_arch == "ada"
    assert abs((o.duration_days or 0) - 20.0) < 0.1


def test_parse_missing_fields_safe():
    o = parse_offer({"id": 1, "ask_contract_id": 1, "machine_id": 2, "gpu_name": "Unknown", "num_gpus": 1, "dph_total": 0})
    assert o.gpu_ram_gb == 0.0
    assert o.cpu_ram_gb is None
    assert o.verified is False
    assert o.country is None


def test_parse_country_edge_cases():
    # Single-segment geolocation → country should be None (not echoed back)
    o = parse_offer({"id": 1, "ask_contract_id": 1, "machine_id": 2, "gpu_name": "X", "num_gpus": 1, "dph_total": 0, "geolocation": "France"})
    assert o.country is None
    assert o.geolocation == "France"

    # Empty string → None
    o = parse_offer({"id": 1, "ask_contract_id": 1, "machine_id": 2, "gpu_name": "X", "num_gpus": 1, "dph_total": 0, "geolocation": ""})
    assert o.country is None

    # Trailing-comma geolocation → None
    o = parse_offer({"id": 1, "ask_contract_id": 1, "machine_id": 2, "gpu_name": "X", "num_gpus": 1, "dph_total": 0, "geolocation": "Paris,"})
    assert o.country is None
