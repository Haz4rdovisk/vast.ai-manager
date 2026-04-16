from app.services.ssh_service import (
    build_ssh_command, build_tunnel_command, build_terminal_launch,
)


def test_build_ssh_command():
    cmd = build_ssh_command("ssh5.vast.ai", 12345)
    assert cmd == ["ssh", "-p", "12345", "root@ssh5.vast.ai"]


def test_build_tunnel_command_default_port():
    cmd = build_tunnel_command("ssh5.vast.ai", 12345, 11434)
    assert cmd == [
        "ssh", "-p", "12345", "root@ssh5.vast.ai",
        "-L", "11434:127.0.0.1:11434",
        "-N",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
    ]


def test_build_tunnel_command_with_key():
    cmd = build_tunnel_command("h", 22, 11434, key_path="C:/k/id_rsa")
    assert "-i" in cmd and "C:/k/id_rsa" in cmd
    assert "IdentitiesOnly=yes" in cmd


def test_build_ssh_command_with_key():
    cmd = build_ssh_command("h", 22, key_path="C:/k/id_rsa")
    assert cmd == ["ssh", "-p", "22", "-i", "C:/k/id_rsa", "root@h"]


def test_live_metrics_parse_block():
    from app.workers.live_metrics import _parse_block
    block = [
        "12, 1234, 24576, 65",
        "MEM 8192 32768",
        "LOAD 1.5",
        "DISK 21 55",
    ]
    d = _parse_block(block)
    assert d["gpu_util"] == 12.0
    assert d["vram_used_mb"] == 1234.0
    assert d["vram_total_mb"] == 24576.0
    assert d["gpu_temp"] == 65.0
    assert d["ram_used_mb"] == 8192.0
    assert d["ram_total_mb"] == 32768.0
    assert d["load1"] == 1.5
    assert d["disk_used_gb"] == 21.0
    assert d["disk_total_gb"] == 55.0


def test_live_metrics_parse_block_partial():
    """Worker should tolerate missing tools (no nvidia-smi etc.)."""
    from app.workers.live_metrics import _parse_block
    d = _parse_block(["MEM 100 200"])
    assert d == {"ram_used_mb": 100.0, "ram_total_mb": 200.0}


def test_build_terminal_launch_wt():
    launch = build_terminal_launch(["ssh", "-p", "22", "root@h"], prefer="wt")
    assert launch[0] == "wt.exe"
    assert "ssh" in launch


def test_build_terminal_launch_cmd():
    launch = build_terminal_launch(["ssh", "-p", "22", "root@h"], prefer="cmd")
    assert launch[0] == "cmd.exe"
    assert launch[1] == "/k"


def test_build_terminal_launch_powershell():
    launch = build_terminal_launch(["ssh", "-p", "22", "root@h"], prefer="powershell")
    assert launch[0] == "powershell.exe"
