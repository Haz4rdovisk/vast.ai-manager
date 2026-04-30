from app.lab.services.huggingface import HFModel, HFModelFile
from app.lab.state.models import RemoteSystem
from app.lab.state.store import LabStore
from app.lab.views.discover_view import (
    CATEGORY_MAP,
    DiscoverView,
    _SearchRequest,
    apply_category_heuristic,
    category_uses_client_heuristic,
)


def _m(name, tags=None):
    return HFModel(
        id=f"author/{name}",
        author="author",
        name=name,
        downloads=0,
        likes=0,
        tags=tags or [],
        files=[],
    )


def test_category_map_has_required_entries():
    assert set(CATEGORY_MAP) == {
        "All",
        "General",
        "Coding",
        "Reasoning",
        "Chat",
        "Multimodal",
        "Embedding",
    }
    assert CATEGORY_MAP["Multimodal"]["pipeline"] == "image-text-to-text"
    assert CATEGORY_MAP["Embedding"]["pipeline"] == "feature-extraction"
    assert CATEGORY_MAP["All"]["pipeline"] is None


def test_heuristic_coding_matches_common_coder_names():
    models = [
        _m("Qwen2.5-Coder-14B-Instruct-GGUF"),
        _m("deepseek-coder-v2-lite-gguf"),
        _m("Meta-Llama-3-8B-Instruct-GGUF"),
        _m("starcoder2-15b-gguf"),
    ]
    names = [model.name for model in apply_category_heuristic("Coding", models)]
    assert "Qwen2.5-Coder-14B-Instruct-GGUF" in names
    assert "deepseek-coder-v2-lite-gguf" in names
    assert "starcoder2-15b-gguf" in names
    assert "Meta-Llama-3-8B-Instruct-GGUF" not in names


def test_heuristic_all_passes_everything_through():
    models = [_m("A"), _m("B")]
    assert apply_category_heuristic("All", models) == models


def test_category_heuristic_flag_matches_discover_categories():
    assert category_uses_client_heuristic("Coding") is True
    assert category_uses_client_heuristic("Reasoning") is True
    assert category_uses_client_heuristic("Chat") is True
    assert category_uses_client_heuristic("All") is False
    assert category_uses_client_heuristic("General") is False


def test_discover_prefetches_more_pages_for_underfilled_heuristic_category(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)

    request = _SearchRequest(term="", category="Coding", sort_mode="trending")
    view._active_request = request
    view._search_generation = 1
    view._page_seen_ids = set()
    view._page_buffer = []

    launches = []
    view._launch_search = lambda req, reset_buffer: launches.append((req, reset_buffer))

    models = [
        _m(f"Qwen2.5-Coder-{idx}-GGUF", tags=["gguf", "text-generation"])
        for idx in range(8)
    ] + [
        _m(f"Generic-{idx}-GGUF", tags=["gguf", "text-generation"])
        for idx in range(32)
    ]

    view._on_search_finished(1, request, models, "NEXTCURSOR")

    assert launches == [(_SearchRequest(term="", category="Coding", sort_mode="trending", cursor="NEXTCURSOR", append=False), False)]
    assert len(view.current_models) == 8


def test_discover_reselects_first_visible_model_after_size_filter(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)

    small = HFModel(
        id="org/small-model",
        author="org",
        name="small-model-3B-GGUF",
        downloads=100,
        likes=10,
        tags=["3b"],
        files=[HFModelFile("small-model-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")],
    )
    big = HFModel(
        id="org/big-model",
        author="org",
        name="big-model-70B-GGUF",
        downloads=200,
        likes=20,
        tags=["70b"],
        files=[HFModelFile("big-model-Q4_K_M.gguf", 40_000_000_000, "Q4_K_M")],
    )
    view.current_models = [small, big]
    view.side_panel.set_model(big)
    view.size_filter.setCurrentIndex(1)

    view._render()

    assert view.side_panel.current_model is not None
    assert view.side_panel.current_model.id == small.id


def test_discover_unknown_size_filter_only_matches_models_without_params(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)

    known = HFModel(
        id="org/known-model",
        author="org",
        name="known-model-7B-GGUF",
        downloads=100,
        likes=10,
        tags=["7b"],
        files=[HFModelFile("known-model-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")],
    )
    unknown = HFModel(
        id="org/unknown-model",
        author="org",
        name="unknown-model-GGUF",
        downloads=100,
        likes=10,
        tags=["embedding"],
        files=[HFModelFile("unknown-model-f16.gguf", 700_000_000, "F16")],
    )
    view.current_models = [known, unknown]
    view.size_filter.setCurrentIndex(6)

    view._render()

    assert list(view._cards) == [unknown.id]


def test_discover_summary_uses_visible_count_not_total_count(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(
        1,
        RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True, gpu_vram_gb=24),
    )
    view = DiscoverView(store)

    visible = HFModel(
        id="org/visible-model",
        author="org",
        name="visible-model-3B-GGUF",
        downloads=100,
        likes=10,
        tags=["3b"],
        files=[HFModelFile("visible-model-Q4_K_M.gguf", 2_000_000_000, "Q4_K_M")],
    )
    hidden = HFModel(
        id="org/hidden-model",
        author="org",
        name="hidden-model-70B-GGUF",
        downloads=100,
        likes=10,
        tags=["70b"],
        files=[HFModelFile("hidden-model-Q4_K_M.gguf", 40_000_000_000, "Q4_K_M")],
    )
    view.current_models = [visible, hidden]
    view.size_filter.setCurrentIndex(1)

    view._render()
    view._refresh_summary()

    assert view.status_lbl.text() == "1 model loaded"
    assert "1 visible" in view._format_result_status(total_count=2, visible_count=1, partial=False)


def test_discover_queues_latest_request_while_previous_search_is_running(qt_app):
    class _RunningWorker:
        def isRunning(self):
            return True

    store = LabStore()
    view = DiscoverView(store)
    view.worker = _RunningWorker()
    view._active_request = _SearchRequest(term="llama", category="All", sort_mode="trending")
    view.search_input.setText("qwen")

    view._search()

    assert view._queued_request == _SearchRequest(term="qwen", category="All", sort_mode="trending", cursor=None, append=False)


def test_discover_uses_trending_as_default_sort(qt_app):
    view = DiscoverView(LabStore())

    assert view.sort_combo.currentText() == "Trending"
    assert view._current_sort_mode() == "trending"


def test_discover_ignores_stale_detail_worker_result(qt_app):
    store = LabStore()
    view = DiscoverView(store)
    old_model = HFModel(
        id="org/stale-model",
        author="org",
        name="stale-model-GGUF",
        downloads=1,
        likes=1,
        tags=["7b"],
        files=[],
    )
    current_model = HFModel(
        id="org/current-model",
        author="org",
        name="current-model-7B-GGUF",
        downloads=1,
        likes=1,
        tags=["7b"],
        files=[],
    )
    view.current_models = [current_model]
    view._detail_session_id = 2
    view._is_fetching_details = True

    view._on_bg_detail_finished(
        1,
        old_model.id,
        old_model,
        [HFModelFile("stale-model-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")],
    )

    assert old_model.files == []
    assert current_model.files == []
