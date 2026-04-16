from app.models import Instance, InstanceState, TunnelStatus, UserInfo, AppConfig


def test_instance_state_enum_values():
    assert InstanceState.RUNNING.value == "running"
    assert InstanceState.STOPPED.value == "stopped"


def test_tunnel_status_enum_values():
    assert TunnelStatus.CONNECTED.value == "connected"


def test_app_config_defaults():
    cfg = AppConfig()
    assert cfg.api_key == ""
    assert cfg.refresh_interval_seconds == 30
    assert cfg.default_tunnel_port == 11434
    assert cfg.terminal_preference == "auto"
    assert cfg.auto_connect_on_activate is True


def test_instance_minimal_construction():
    inst = Instance(
        id=1, state=InstanceState.RUNNING, gpu_name="RTX 4090", num_gpus=1,
        gpu_ram_gb=24.0, gpu_util=None, gpu_temp=None, vram_usage_gb=None,
        cpu_name=None, cpu_cores=None, cpu_util=None,
        ram_total_gb=None, ram_used_gb=None,
        disk_usage_gb=None, disk_space_gb=None,
        inet_down_mbps=None, inet_up_mbps=None, image=None,
        dph=0.42, duration_seconds=None, ssh_host=None, ssh_port=None, raw={},
    )
    assert inst.id == 1
    assert inst.state == InstanceState.RUNNING


def test_user_info_minimal():
    u = UserInfo(balance=10.5)
    assert u.balance == 10.5
    assert u.email is None
