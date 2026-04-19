from app.lab.state.models import RemoteSystem, ScoredCatalogModel
from app.lab.state.store import LabStore
from app.lab.views.discover_view import DiscoverView


def _card_texts(view) -> list[str]:
    texts: list[str] = []
    for index in range(view.list_lay.count()):
        widget = view.list_lay.itemAt(index).widget()
        if not widget:
            continue
        for label in widget.findChildren(type(view.status_lbl)):
            texts.append(label.text())
    return texts


def test_discover_renders_card_per_model(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)
    store.set_scored_models(
        1,
        [
            ScoredCatalogModel(
                name="Qwen2.5-7B",
                provider="Qwen",
                params_b=7.6,
                best_quant="Q4_K_M",
                use_case="general",
                fit_level="perfect",
                fit_label="Perfect fit",
                run_mode="gpu",
                score=92.0,
                utilization_pct=25.0,
                memory_required_gb=5.8,
                memory_available_gb=24,
                estimated_tps=55.0,
                gguf_sources=["Qwen/Qwen2.5-7B-Instruct-GGUF"],
            ),
        ],
    )
    texts = _card_texts(view)
    assert any("Qwen2.5-7B" in text for text in texts)
    assert any("Perfect fit" in text or "perfect" in text.lower() for text in texts)


def test_discover_shows_per_instance_score_column(qt_app):
    """Each model card shows a per-instance score chip."""
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=True, gpu_vram_gb=24),
    )
    store.set_remote_system(
        2,
        RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=True, gpu_vram_gb=8),
    )
    view = DiscoverView(store)
    model = ScoredCatalogModel(
        name="Qwen2.5-7B",
        provider="Qwen",
        params_b=7.6,
        best_quant="Q4_K_M",
        use_case="general",
        fit_level="perfect",
        fit_label="Perfect fit",
        run_mode="gpu",
        score=92.0,
        utilization_pct=25.0,
        memory_required_gb=5.8,
        memory_available_gb=24,
        estimated_tps=55.0,
        gguf_sources=[],
    )
    store.set_scored_models(1, [model])
    store.set_scored_models(
        2,
        [
            ScoredCatalogModel(
                name="Qwen2.5-7B",
                provider="Qwen",
                params_b=7.6,
                best_quant="Q4_K_M",
                use_case="general",
                fit_level="marginal",
                fit_label="Tight fit",
                run_mode="gpu",
                score=45.0,
                utilization_pct=72.5,
                memory_required_gb=5.8,
                memory_available_gb=8,
                estimated_tps=55.0,
            ),
        ],
    )
    texts = _card_texts(view)
    assert any("#1" in text for text in texts)
    assert any("#2" in text for text in texts)
