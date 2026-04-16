from app.services.vast_service import parse_instance, parse_user_info
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


def test_parse_user_info():
    raw = {"credit": 42.18, "email": "u@example.com"}
    u = parse_user_info(raw)
    assert u.balance == 42.18
    assert u.email == "u@example.com"


def test_parse_user_info_missing_fields():
    u = parse_user_info({})
    assert u.balance == 0.0
    assert u.email is None
