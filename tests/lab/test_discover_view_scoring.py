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
    assert view.close_panel_btn.isVisible() is True
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


def test_discover_best_fit_sort_uses_rank_and_stays_stable_with_cache(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)
    view.sort_combo.setCurrentIndex(2)

    higher_score_lower_rank = HFModel(
        id="org/tiny-q2-model",
        author="org",
        name="tiny-q2-model-3B-GGUF",
        downloads=100,
        likes=10,
        tags=["3b"],
        files=[HFModelFile("tiny-q2-model-Q2_K.gguf", 1_300_000_000, "Q2_K")],
    )
    lower_score_higher_rank = HFModel(
        id="org/better-q8-model",
        author="org",
        name="better-q8-model-7B-GGUF",
        downloads=50,
        likes=5,
        tags=["7b"],
        files=[HFModelFile("better-q8-model-Q8_0.gguf", 8_300_000_000, "Q8_0")],
    )

    view.current_models = [higher_score_lower_rank, lower_score_higher_rank]
    view._render()

    assert view._displayed_model_ids[0] == lower_score_higher_rank.id
    assert set(view._score_cache) == {
        higher_score_lower_rank.id,
        lower_score_higher_rank.id,
    }

    view.current_models = [lower_score_higher_rank, higher_score_lower_rank]
    view._render()

    assert view._displayed_model_ids[0] == lower_score_higher_rank.id


def test_discover_stale_detail_callback_clears_loading_flag(qt_app):
    store = LabStore()
    view = DiscoverView(store)
    model = HFModel(
        id="org/stale-loading-model",
        author="org",
        name="stale-loading-model-GGUF",
        downloads=1,
        likes=1,
        tags=["7b"],
        files=[],
        details_loading=True,
    )
    view.current_models = [model]
    view._detail_session_id = 2

    restarted = []
    view._start_detail_fetch = lambda: restarted.append(True)

    view._on_bg_detail_finished(
        1,
        model.id,
        model,
        [HFModelFile("stale-loading-model-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")],
    )

    assert model.details_loading is False
    assert restarted == [True]


def test_discover_search_uses_spinner_loading_indicator(qt_app):
    store = LabStore()
    view = DiscoverView(store)

    assert view.search_spinner.isHidden() is True

    view._set_search_loading(True)
    assert view.search_spinner.isHidden() is False

    view._set_search_loading(False)
    assert view.search_spinner.isHidden() is True
