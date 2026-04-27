from app.services.vast_service import VastService, parse_instance, parse_user_info
from app.models import InstanceState


def test_parse_instance_running():
    raw = {
        "id": 123, "actual_status": "running", "intended_status": "running",
        "gpu_name": "RTX 4090", "num_gpus": 1, "gpu_ram": 24576,
        "gpu_util": 72.5, "gpu_temp": 68, "cpu_name": "EPYC", "cpu_cores": 16,
        "cpu_util": 0.40, "cpu_ram": 32768, "mem_usage": 18000,
        "vmem_usage": 8192, "disk_usage": 12.5, "disk_space": 50.0,
        "inet_up": 12.4, "inet_down": 100.1, "label": None,
        "image_uuid": "pytorch/pytorch:2.1", "dph_total": 0.42,
        "duration": 11400, "ssh_host": "ssh5.vast.ai", "ssh_port": 12345,
        "reliability2": 0.97, "dlperf": 185.2, "total_flops": 82.5,
        "flops_per_dphtotal": 196.4, "verification": "verified",
        "storage_cost": 0.15,
        "instance": {"discountedTotalPerHour": 0.38},
    }
    inst = parse_instance(raw)
    assert inst.id == 123
    assert inst.state == InstanceState.RUNNING
    assert inst.gpu_name == "RTX 4090"
    assert inst.gpu_ram_gb == 24.0
    assert inst.gpu_util == 72.5  # already %, kept
    assert inst.cpu_util == 40.0  # 0.40 ratio → 40%
    assert inst.vram_usage_gb == 8.0  # 8192 MB → 8 GB
    assert inst.disk_usage_gb == 12.5
    assert inst.disk_space_gb == 50.0
    assert inst.dph == 0.42
    assert inst.ssh_host == "ssh5.vast.ai"
    assert inst.ssh_port == 12345
    assert inst.image == "pytorch/pytorch:2.1"
    assert inst.reliability == 0.97
    assert inst.dlperf == 185.2
    assert inst.total_flops == 82.5
    assert inst.flops_per_dphtotal == 196.4
    assert inst.verification == "verified"
    assert inst.storage_cost_per_gb_month == 0.15
    assert inst.discounted_total_per_hour == 0.38


def test_parse_instance_stopped_drops_telemetry():
    # Stopped instances often carry stale last-known util/vram values.
    # Parser must drop them so the UI doesn't show a fake "running" reading.
    raw = {"id": 7, "actual_status": "exited", "intended_status": "stopped",
           "gpu_name": "RTX 3090", "num_gpus": 1, "gpu_ram": 24576,
           "gpu_util": 88.0, "gpu_temp": 70, "vmem_usage": 4096,
           "cpu_util": 0.55, "mem_usage": 9000,
           "disk_usage": 7.0, "inet_up": 5.0, "inet_down": 9.0,
           "dph_total": 0.28}
    inst = parse_instance(raw)
    assert inst.state == InstanceState.STOPPED
    assert inst.gpu_util is None
    assert inst.gpu_temp is None
    assert inst.vram_usage_gb is None
    assert inst.cpu_util is None
    assert inst.ram_used_gb is None
    assert inst.disk_usage_gb is None
    assert inst.inet_down_mbps is None
    assert inst.inet_up_mbps is None


def test_parse_instance_starting():
    raw = {"id": 8, "actual_status": "loading", "intended_status": "running",
           "gpu_name": "A100", "num_gpus": 1, "gpu_ram": 40960, "dph_total": 1.10}
    inst = parse_instance(raw)
    assert inst.state == InstanceState.STARTING
    assert inst.raw["_is_scheduling"] is False


def test_parse_instance_scheduling_from_intended_running():
    raw = {"id": 9, "actual_status": "exited", "intended_status": "running",
           "gpu_name": "RTX 3090", "num_gpus": 1, "gpu_ram": 24576}
    inst = parse_instance(raw)
    assert inst.state == InstanceState.STARTING
    assert inst.raw["_is_scheduling"] is True


def test_parse_instance_uses_cur_and_next_state_fallbacks():
    raw = {"id": 10, "cur_state": "stopped", "next_state": "running",
           "gpu_name": "RTX 3090", "num_gpus": 1, "gpu_ram": 24576}
    inst = parse_instance(raw)
    assert inst.state == InstanceState.STARTING
    assert inst.raw["_normalized_actual_status"] == "stopped"
    assert inst.raw["_normalized_intended_status"] == "running"
    assert inst.raw["_is_scheduling"] is True


def test_list_instances_overlays_running_target_from_audit_logs(monkeypatch):
    svc = VastService("key")

    def fake_call(fn_name, **kwargs):
        if fn_name == "show_instances":
            return [
                {
                    "id": 9,
                    "actual_status": "exited",
                    "intended_status": "stopped",
                    "gpu_name": "RTX 3090",
                    "num_gpus": 1,
                    "gpu_ram": 24576,
                }
            ]
        if fn_name == "show_audit_logs":
            return [
                {
                    "api_route": "api.instance_PUT",
                    "created_at": 10.0,
                    "args": {"instance_id": 9, "target_state": "running"},
                }
            ]
        raise AssertionError(fn_name)

    monkeypatch.setattr(svc, "_call", fake_call)

    inst = svc.list_instances(include_audit_targets=True)[0]

    assert inst.state == InstanceState.STARTING
    assert inst.raw["_is_scheduling"] is True
    assert inst.raw["_scheduling_source"] == "audit_logs"


def test_list_instances_uses_latest_audit_target(monkeypatch):
    svc = VastService("key")

    def fake_call(fn_name, **kwargs):
        if fn_name == "show_instances":
            return [
                {
                    "id": 9,
                    "actual_status": "exited",
                    "intended_status": "stopped",
                    "gpu_name": "RTX 3090",
                    "num_gpus": 1,
                    "gpu_ram": 24576,
                }
            ]
        if fn_name == "show_audit_logs":
            return [
                {
                    "api_route": "api.instance_PUT",
                    "created_at": 10.0,
                    "args": {"instance_id": 9, "target_state": "running"},
                },
                {
                    "api_route": "api.instance_PUT",
                    "created_at": 20.0,
                    "args": {"instance_id": 9, "target_state": "stopped"},
                },
            ]
        raise AssertionError(fn_name)

    monkeypatch.setattr(svc, "_call", fake_call)

    inst = svc.list_instances(include_audit_targets=True)[0]

    assert inst.state == InstanceState.STOPPED
    assert inst.raw["_is_scheduling"] is False


def test_list_instances_skips_audit_by_default(monkeypatch):
    svc = VastService("key")

    def fake_call(fn_name, **kwargs):
        if fn_name == "show_instances":
            return [
                {
                    "id": 9,
                    "actual_status": "exited",
                    "intended_status": "stopped",
                    "gpu_name": "RTX 3090",
                    "num_gpus": 1,
                    "gpu_ram": 24576,
                }
            ]
        if fn_name == "show_audit_logs":
            raise AssertionError("audit should not block the fast path")
        raise AssertionError(fn_name)

    monkeypatch.setattr(svc, "_call", fake_call)

    inst = svc.list_instances()[0]

    assert inst.state == InstanceState.STOPPED
    assert inst.raw["_is_scheduling"] is False


def test_start_instance_rejects_unsuccessful_response(monkeypatch):
    svc = VastService("key")
    monkeypatch.setattr(
        svc,
        "_call",
        lambda fn_name, **kwargs: {"success": False, "msg": "no capacity"},
    )

    try:
        svc.start_instance(9)
    except Exception as exc:
        assert "no capacity" in str(exc)
    else:
        raise AssertionError("expected start_instance to reject failed response")


def test_parse_user_info():
    raw = {"credit": 42.18, "email": "u@example.com"}
    u = parse_user_info(raw)
    assert u.balance == 42.18
    assert u.email == "u@example.com"


def test_parse_user_info_missing_fields():
    u = parse_user_info({})
    assert u.balance == 0.0
    assert u.email is None


def test_fetch_financial_data_uses_sdk_billing_pages(monkeypatch):
    svc = VastService("key")
    calls = []

    def fake_call(fn_name, **kwargs):
        calls.append((fn_name, kwargs))
        assert fn_name == "show_invoices_v1"
        if kwargs.get("charges"):
            if "next_token" not in kwargs:
                return {
                    "success": True,
                    "results": [{"amount": 1, "end": 10}],
                    "next_token": "next",
                }
            return {"success": True, "results": [{"amount": 2, "end": 20}], "next_token": None}
        return {"success": True, "results": [{"amount": -5, "end": 30}], "next_token": None}

    monkeypatch.setattr(svc, "_call", fake_call)
    monkeypatch.setattr("app.services.vast_service.time.time", lambda: 1_000_000)

    out = svc.fetch_financial_data(days=7)

    assert out["charges"] == [{"amount": 1, "end": 10}, {"amount": 2, "end": 20}]
    assert out["invoices"] == [{"amount": -5, "end": 30}]
    assert out["sync"]["days"] == 7
    assert len(calls) == 3
    assert calls[0][1]["format"] == "tree"
    assert calls[0][1]["start_date"] == 1_000_000 - 7 * 24 * 3600


def test_parse_instance_outbid_from_status_message():
    raw = {
        "id": 20,
        "actual_status": "exited",
        "intended_status": "running",
        "status_msg": "instance terminated: outbid",
    }
    inst = parse_instance(raw)
    assert inst.state == InstanceState.OUTBID
    assert inst.raw.get("_is_outbid") is True


def test_parse_instance_outbid_from_preempted_message():
    raw = {
        "id": 21,
        "actual_status": "offline",
        "intended_status": "running",
        "status_message": "preempted by higher bid",
    }
    inst = parse_instance(raw)
    assert inst.state == InstanceState.OUTBID
    assert inst.raw.get("_is_outbid") is True


def test_parse_instance_not_outbid_when_intended_stopped():
    raw = {
        "id": 22,
        "actual_status": "exited",
        "intended_status": "stopped",
        "status_msg": "outbid",
    }
    inst = parse_instance(raw)
    assert inst.state == InstanceState.STOPPED
    assert inst.raw.get("_is_outbid") is not True
