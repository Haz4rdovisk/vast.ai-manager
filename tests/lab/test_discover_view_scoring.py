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
    from app.lab.services.huggingface import HFModel
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)
    
    # Mock the search result
    view.current_models = [
        HFModel(
            id="Qwen/Qwen2.5-7B-Instruct-GGUF",
            author="Qwen",
            name="Qwen2.5-7B-Instruct-GGUF",
            downloads=1000,
            likes=100,
            tags=["7b"]
        )
    ]
    view._render()
    
    texts = _card_texts(view)
    assert any("Qwen2.5-7B" in text for text in texts)
    assert any("#1" in text for text in texts)


def test_discover_shows_per_instance_score_column(qt_app):
    """Each model card shows a per-instance score chip."""
    from app.lab.services.huggingface import HFModel
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
    
    view.current_models = [
        HFModel(
            id="Qwen/Qwen2.5-7B-Instruct-GGUF",
            author="Qwen",
            name="Qwen2.5-7B-Instruct-GGUF",
            downloads=1000,
            likes=100,
            tags=["7b"]
        )
    ]
    view._render()
    
    texts = _card_texts(view)
    assert any("#1" in text for text in texts)
    assert any("#2" in text for text in texts)
