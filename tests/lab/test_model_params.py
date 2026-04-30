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
    assert p.ubatch_size == 512
    assert p.temperature == 0.80
    assert p.top_k == 40
    assert p.top_p == 0.95
    assert p.min_p == 0.05
    assert p.max_tokens == -1


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
        threads_batch=16,
        batch_size=1024,
        ubatch_size=256,
        flash_attention=True,
        kv_cache_type="q8_0",
        mlock=True,
        mmap=False,
        continuous_batching=False,
        context_shift=True,
        temperature=0.7,
        dynatemp_range=0.5,
        dynatemp_exp=1.2,
        top_k=64,
        top_p=0.9,
        min_p=0.08,
        xtc_probability=0.2,
        xtc_threshold=0.15,
        typical_p=0.97,
        max_tokens=2048,
        samplers="top_k,top_p,min_p,temperature",
        backend_sampling=True,
    )
    cmd = build_launch_command(p)
    assert "-c 8192" in cmd
    assert "-ngl 40" in cmd
    assert "-t 8" in cmd
    assert "-tb 16" in cmd
    assert "-b 1024" in cmd
    assert "-ub 256" in cmd
    assert "-fa on" in cmd
    assert "-ctk q8_0" in cmd
    assert "--mlock" in cmd
    assert "--no-mmap" in cmd
    assert "--no-cont-batching" in cmd
    assert "--context-shift" in cmd
    assert "--temp 0.70" in cmd
    assert "--dynatemp-range 0.50" in cmd
    assert "--dynatemp-exp 1.20" in cmd
    assert "--top-k 64" in cmd
    assert "--top-p 0.90" in cmd
    assert "--min-p 0.08" in cmd
    assert "--xtc-probability 0.20" in cmd
    assert "--xtc-threshold 0.15" in cmd
    assert "--typical-p 0.97" in cmd
    assert "--n-predict 2048" in cmd
    assert '--samplers "top_k;top_p;min_p;temperature"' in cmd
    assert "--backend-sampling" in cmd


def test_build_command_auto_threads():
    p = ServerParams(model_path="/m.gguf", threads=0)
    cmd = build_launch_command(p)
    assert "-t " not in cmd  # threads=0 means auto, no -t flag
    assert "-tb " not in cmd  # threads_batch=0 means auto, no -tb flag


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
        batch_size=1024, ubatch_size=256, threads=8,
        flash_attention=True, kv_cache_type="q8_0", temperature=0.7,
    )
    s = params_summary(p)
    assert "ctx=8192" in s
    assert "ngl=40" in s
    assert "ubatch=256" in s
    assert "temp=0.70" in s
    assert "FA" in s
