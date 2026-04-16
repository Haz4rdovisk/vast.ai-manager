from app.lab.services.capacity import estimate_capacity, fit_for_model
from app.lab.state.models import HardwareSpec, GPUInfo


def _hw(ram=32.0, vram=24.0, cuda=True, cores=16):
    gpus = [GPUInfo("RTX 4090", vram, "555", cuda)] if vram else []
    return HardwareSpec(
        os_name="Windows", cpu_name="x", cpu_cores_physical=cores,
        cpu_cores_logical=cores * 2, ram_total_gb=ram, ram_available_gb=ram - 4,
        disk_total_gb=1000.0, disk_free_gb=500.0, gpus=gpus,
        best_backend="cuda" if cuda and vram else "cpu",
    )


def test_capacity_notes_for_big_gpu():
    caps = estimate_capacity(_hw(ram=64, vram=24))
    assert "7B" in " ".join(caps.notes) or "14B" in " ".join(caps.notes)
    assert caps.tier in ("excellent", "strong", "good")


def test_capacity_notes_for_small_gpu():
    caps = estimate_capacity(_hw(ram=16, vram=8))
    assert any("7B" in n or "small" in n.lower() for n in caps.notes)


def test_fit_excellent_when_vram_fits_with_headroom():
    hw = _hw(ram=64, vram=24)
    fit = fit_for_model(hw, approx_vram_gb=14.0, approx_ram_gb=20.0)
    assert fit == "excellent"


def test_fit_tight_when_vram_barely_fits():
    hw = _hw(ram=32, vram=12)
    fit = fit_for_model(hw, approx_vram_gb=11.5, approx_ram_gb=16.0)
    assert fit == "tight"


def test_fit_not_recommended_when_vram_exceeds():
    # VRAM too small AND CPU RAM can't carry the model either.
    # _hw(ram=16, vram=8) -> ram_available_gb == 12. Ask for 20 GB RAM
    # so the CPU fallback also fails.
    hw = _hw(ram=16, vram=8)
    fit = fit_for_model(hw, approx_vram_gb=18.0, approx_ram_gb=20.0)
    assert fit == "not_recommended"


def test_fit_cpu_fallback_when_no_gpu():
    hw = _hw(ram=32, vram=0, cuda=False)
    fit = fit_for_model(hw, approx_vram_gb=14.0, approx_ram_gb=18.0)
    assert fit in ("good", "tight")
