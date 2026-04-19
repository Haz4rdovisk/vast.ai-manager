from app.lab.services.fit_scorer import InstanceFitScorer, ScoredModel
from app.lab.services.model_catalog import CatalogEntry
from app.lab.state.models import RemoteSystem


def _rtx3090():
    return RemoteSystem(
        cpu_cores=16,
        ram_total_gb=64,
        has_gpu=True,
        gpu_vram_gb=24.0,
        gpu_name="RTX 3090",
    )


def _cpu_only():
    return RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=False)


def test_scores_perfect_fit_on_big_gpu():
    system = _rtx3090()
    entry = CatalogEntry(
        name="Qwen2.5-7B",
        params_b=7.6,
        best_quant="Q4_K_M",
        memory_required_gb=5.8,
        estimated_tps_7b=55,
    )
    scored = InstanceFitScorer().score(entry, system)
    assert isinstance(scored, ScoredModel)
    assert scored.fit_level == "perfect"
    assert scored.run_mode == "gpu"
    assert scored.score >= 80
    assert scored.estimated_tps > 40


def test_scores_marginal_when_close_to_vram_limit():
    system = RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=True, gpu_vram_gb=6.0)
    entry = CatalogEntry(
        name="Llama-3-8B",
        params_b=8.0,
        best_quant="Q4_K_M",
        memory_required_gb=5.8,
        estimated_tps_7b=52,
    )
    scored = InstanceFitScorer().score(entry, system)
    assert scored.fit_level in ("marginal", "good")
    assert scored.utilization_pct > 80


def test_scores_too_tight_when_over_vram():
    system = RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=True, gpu_vram_gb=6.0)
    entry = CatalogEntry(
        name="14B-big",
        params_b=14,
        best_quant="Q4_K_M",
        memory_required_gb=10.2,
        estimated_tps_7b=32,
    )
    scored = InstanceFitScorer().score(entry, system)
    assert scored.fit_level == "too_tight"


def test_scores_cpu_when_no_gpu():
    system = _cpu_only()
    entry = CatalogEntry(
        name="Phi-3.5",
        params_b=3.8,
        best_quant="Q4_K_M",
        memory_required_gb=2.8,
        estimated_tps_7b=85,
    )
    scored = InstanceFitScorer().score(entry, system)
    assert scored.run_mode == "cpu"
    assert scored.fit_level in ("good", "marginal")
