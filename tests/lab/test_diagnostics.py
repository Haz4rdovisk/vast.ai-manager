from app.lab.services.diagnostics import collect_diagnostics
from app.lab.state.models import (
    HardwareSpec, RuntimeStatus, ModelFile, GPUInfo,
)


def test_diag_flags_missing_runtime():
    items = collect_diagnostics(
        HardwareSpec(ram_total_gb=32), RuntimeStatus(installed=False), [],
    )
    ids = [i.id for i in items]
    assert "runtime_missing" in ids


def test_diag_flags_no_gpu_when_large_ram_fine():
    items = collect_diagnostics(
        HardwareSpec(ram_total_gb=64), RuntimeStatus(installed=True, validated=True), [],
    )
    ids = [i.id for i in items]
    assert "no_gpu" in ids
    # but with 64GB RAM it's only "info", not "err"
    no_gpu = next(i for i in items if i.id == "no_gpu")
    assert no_gpu.level in ("info", "warn")


def test_diag_flags_invalid_models():
    lib = [
        ModelFile(path="/a", name="a", size_bytes=100, valid=True),
        ModelFile(path="/b", name="b", size_bytes=100, valid=False, error="bad"),
    ]
    items = collect_diagnostics(
        HardwareSpec(ram_total_gb=32), RuntimeStatus(installed=True, validated=True), lib,
    )
    assert any(i.id == "invalid_models" for i in items)


def test_diag_empty_when_all_ok():
    hw = HardwareSpec(
        ram_total_gb=64,
        gpus=[GPUInfo("RTX 4090", 24, "555", True)],
        best_backend="cuda",
    )
    rt = RuntimeStatus(installed=True, validated=True, backend="cuda")
    items = collect_diagnostics(hw, rt, [])
    errs = [i for i in items if i.level == "err"]
    assert errs == []
