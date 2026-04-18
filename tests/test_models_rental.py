from app.models_rental import Offer, OfferQuery, OfferType, OfferSort, RentRequest


def test_offer_query_defaults():
    q = OfferQuery()
    assert q.offer_type == OfferType.ON_DEMAND
    assert q.sort == OfferSort.SCORE_DESC
    assert q.verified is True
    assert q.rentable is True
    assert q.rented is False
    assert q.gpu_names == []
    assert q.min_num_gpus is None
    assert q.max_dph is None
    assert q.storage_gib == 10.0
    assert q.limit == 64


def test_offer_dataclass_minimal():
    o = Offer(
        id=1, ask_contract_id=1, machine_id=2, host_id=3,
        gpu_name="RTX 4090", num_gpus=1, gpu_ram_gb=24.0, gpu_total_ram_gb=24.0,
        cpu_name="AMD EPYC", cpu_cores=16, cpu_ram_gb=64.0,
        disk_space_gb=500.0, disk_bw_mbps=2000.0,
        inet_down_mbps=1000.0, inet_up_mbps=1000.0,
        dph_total=0.35, min_bid=None, storage_cost=0.1,
        reliability=0.98, dlperf=22.0, dlperf_per_dphtotal=62.0,
        flops_per_dphtotal=110.0, cuda_max_good=12.4, compute_cap=890,
        verified=True, rentable=True, rented=False, external=False,
        geolocation="US-California, US", country="US", datacenter="DC-X",
        static_ip=True, direct_port_count=20, gpu_arch="ada",
        duration_days=14.5, hosting_type="datacenter",
        raw={},
    )
    assert o.effective_price() == 0.35


def test_rent_request_fields():
    r = RentRequest(
        offer_id=123, image="pytorch/pytorch:latest",
        template_hash=None, disk_gb=30.0, label="test-rent",
        ssh_key_id=1, env={"FOO": "bar"}, onstart_cmd=None,
        jupyter_lab=False, price=None,
    )
    assert r.offer_id == 123
    assert r.disk_gb == 30.0
