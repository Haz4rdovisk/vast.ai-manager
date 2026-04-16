"""Tests for model parameter builder."""
from app.lab.services.model_params import (
    build_launch_command, build_launch_script, params_summary, default_params,
)
from app.lab.state.models import ServerParams


def test_default_params():
    p = default_params()
    assert p.context_length == 4096
    assert p.gpu_layers == 99
    assert p.batch_size == 512


def test_build_command_contains_model():
    p = ServerParams(model_path="/workspace/model.gguf")
    cmd = build_launch_command(p)
    assert "/workspace/model.gguf" in cmd
    assert "-ngl 99" in cmd
    assert "-c 4096" in cmd


def test_build_command_with_custom_params():
    p = ServerParams(
        model_path="/m.gguf",
        context_length=8192,
        gpu_layers=40,
        threads=8,
        batch_size=1024,
        flash_attention=True,
        kv_cache_type="q8_0",
    )
    cmd = build_launch_command(p)
    assert "-c 8192" in cmd
    assert "-ngl 40" in cmd
    assert "-t 8" in cmd
    assert "-b 1024" in cmd
    assert "-fa on" in cmd
    assert "-ctk q8_0" in cmd


def test_build_command_auto_threads():
    p = ServerParams(model_path="/m.gguf", threads=0)
    cmd = build_launch_command(p)
    assert "-t " not in cmd  # threads=0 means auto, no -t flag


def test_build_command_with_extra_args():
    p = ServerParams(model_path="/m.gguf", extra_args="--mlock --verbose")
    cmd = build_launch_command(p)
    assert "--mlock --verbose" in cmd


def test_build_script_includes_nohup():
    p = ServerParams(model_path="/m.gguf")
    script = build_launch_script(p)
    assert "nohup" in script
    assert "pkill" in script
    assert "LAUNCH_PID" in script


def test_params_summary():
    p = ServerParams(
        context_length=8192, gpu_layers=40,
        batch_size=1024, threads=8,
        flash_attention=True, kv_cache_type="q8_0",
    )
    s = params_summary(p)
    assert "ctx=8192" in s
    assert "ngl=40" in s
    assert "FA" in s
