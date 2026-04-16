from app.lab.services.recommender import recommend
from app.lab.state.models import CatalogEntry, HardwareSpec, GPUInfo


def _hw(vram=24.0, ram=32.0):
    gpus = [GPUInfo("RTX 4090", vram, "555", True)] if vram else []
    return HardwareSpec(
        os_name="Windows", cpu_name="x", cpu_cores_physical=16,
        cpu_cores_logical=32, ram_total_gb=ram, ram_available_gb=ram-4,
        disk_total_gb=1000.0, disk_free_gb=500.0, gpus=gpus,
        best_backend="cuda" if vram else "cpu",
    )


def _cat(**kwargs):
    base = dict(
        id="x", family="x", display_name="x", params_b=7.0, quant="Q4_K_M",
        repo_id="x", filename="x.gguf",
        approx_size_gb=4.0, approx_vram_gb=7.0, approx_ram_gb=8.0,
        context_length=8192, use_cases=["chat"], quality_tier=4, notes="",
    )
    base.update(kwargs)
    return CatalogEntry(**base)


def test_recommend_ranks_higher_quality_first():
    cat = [
        _cat(id="a", params_b=7, quality_tier=3, approx_vram_gb=6),
        _cat(id="b", params_b=7, quality_tier=5, approx_vram_gb=6),
        _cat(id="c", params_b=7, quality_tier=4, approx_vram_gb=6),
    ]
    recs = recommend(_hw(), cat)
    assert [r.entry.id for r in recs[:3]] == ["b", "c", "a"]


def test_recommend_filters_by_use_case():
    cat = [
        _cat(id="c1", use_cases=["coding"]),
        _cat(id="c2", use_cases=["chat"]),
    ]
    recs = recommend(_hw(), cat, use_case="coding")
    assert [r.entry.id for r in recs] == ["c1"]


def test_recommend_marks_not_recommended_for_oversized():
    cat = [_cat(id="big", params_b=70, approx_vram_gb=50, approx_ram_gb=64)]
    recs = recommend(_hw(vram=12, ram=32), cat)
    assert recs[0].fit == "not_recommended"


def test_recommend_explains_reasons():
    cat = [_cat(id="a", params_b=7, approx_vram_gb=6)]
    recs = recommend(_hw(vram=24), cat)
    assert any("fits" in r.lower() or "excellent" in r.lower()
               for r in recs[0].reasons)
