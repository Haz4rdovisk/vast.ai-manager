from app.lab.services.huggingface import HFModel, HFModelFile
from app.lab.state.models import RemoteSystem
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
            tags=["7b"],
            files=[HFModelFile("Qwen2.5-7B-Instruct-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")],
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
            tags=["7b"],
            files=[HFModelFile("Qwen2.5-7B-Instruct-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")],
        )
    ]
    view._render()
    
    texts = _card_texts(view)
    assert any("#1" in text for text in texts)
    assert any("#2" in text for text in texts)


def test_discover_keeps_settings_open_and_auto_selects_first_result(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)
    view._start_detail_fetch = lambda: None
    view.show()
    qt_app.processEvents()

    model = HFModel(
        id="Qwen/Qwen2.5-7B-Instruct-GGUF",
        author="Qwen",
        name="Qwen2.5-7B-Instruct-GGUF",
        downloads=1000,
        likes=100,
        tags=["7b"],
    )
    view._on_search_finished([model], None, "All")
    qt_app.processEvents()

    assert view.side_panel.isVisible() is True
    assert view.close_panel_btn.text() == "Hide Settings"
    assert view.side_panel.current_model is not None
    assert view.side_panel.current_model.id == model.id


def test_discover_queues_detail_fetch_for_zero_size_files_and_holds_score(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)
    view._start_detail_fetch = lambda: None

    model = HFModel(
        id="Qwen/Qwen2.5-7B-Instruct-GGUF",
        author="Qwen",
        name="Qwen2.5-7B-Instruct-GGUF",
        downloads=1000,
        likes=100,
        tags=["7b"],
        files=[HFModelFile("Qwen2.5-7B-Instruct-Q4_K_M.gguf", 0, "Q4_K_M")],
    )

    view._on_search_finished([model], None, "All")
    qt_app.processEvents()

    assert view._detail_queue == [model.id]
    card = view._cards[model.id]
    assert card._summary.text() == "Scoring hardware match..."
    assert card._fit_panel.isVisible() is False


def test_discover_detail_error_stops_infinite_pending_state(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)

    model = HFModel(
        id="org/broken-model",
        author="org",
        name="broken-model-GGUF",
        downloads=100,
        likes=10,
        tags=["embedding"],
        files=[HFModelFile("broken-model-f16.gguf", 0, "F16")],
        details_error="Could not load GGUF file metadata.",
    )
    view.current_models = [model]

    view._render()

    card = view._cards[model.id]
    assert card._summary.text() == "Could not load GGUF file metadata."
    assert card._fit_panel.isVisible() is False
