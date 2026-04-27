from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

from app.lab.state.store import LabStore
from app.lab.state.models import RemoteGGUF, LabInstanceState, SetupStatus, ServerParams
from app.lab.views.models_view import ModelsView, InstanceSelector, ConfigurePanel


def _make_store_with_models() -> LabStore:
    store = LabStore()
    # Instance 1 — probed, 2 models
    st1 = LabInstanceState(iid=1)
    st1.setup.probed = True
    st1.gguf = [
        RemoteGGUF(path="/workspace/model-a.gguf", filename="model-a.gguf", size_bytes=1024, size_display="1.0 KB"),
        RemoteGGUF(path="/workspace/model-b.gguf", filename="model-b.gguf", size_bytes=2048, size_display="2.0 KB"),
    ]
    store.instance_states[1] = st1
    # Instance 2 — probed, 1 duplicate + 1 unique
    st2 = LabInstanceState(iid=2)
    st2.setup.probed = True
    st2.gguf = [
        RemoteGGUF(path="/workspace/model-a.gguf", filename="model-a.gguf", size_bytes=1024, size_display="1.0 KB"),
        RemoteGGUF(path="/workspace/model-c.gguf", filename="model-c.gguf", size_bytes=512, size_display="512 B"),
    ]
    store.instance_states[2] = st2
    return store


def test_models_view_builds_global_index(qt_app):
    store = _make_store_with_models()
    view = ModelsView(store)
    view.show()

    index = view._build_model_index()
    assert len(index) == 3  # model-a, model-b, model-c
    assert len(index["model-a.gguf"]) == 2
    assert len(index["model-b.gguf"]) == 1
    assert len(index["model-c.gguf"]) == 1


def test_models_view_emits_launch_with_iid(qt_app):
    store = _make_store_with_models()
    view = ModelsView(store)
    spy = QSignalSpy(view.launch_requested)
    view.show()

    view.launch_requested.emit(ServerParams(model_path="/workspace/model-a.gguf"), 1)
    assert spy.count() == 1
    params, iid = spy.at(0)
    assert iid == 1


def test_models_view_emits_delete_with_iid(qt_app):
    store = _make_store_with_models()
    view = ModelsView(store)
    spy = QSignalSpy(view.delete_requested)
    view.show()

    view.delete_requested.emit("/workspace/model-a.gguf", 2)
    assert spy.count() == 1
    path, iid = spy.at(0)
    assert path == "/workspace/model-a.gguf"
    assert iid == 2


def test_instance_selector_populates_and_selects(qt_app):
    selector = InstanceSelector()
    instances = [
        (1, RemoteGGUF(path="/w/a.gguf", filename="a.gguf", size_bytes=1, size_display="1 B")),
        (2, RemoteGGUF(path="/w/a.gguf", filename="a.gguf", size_bytes=1, size_display="1 B")),
    ]
    selector.refresh(instances, {1, 2})
    assert selector.count() == 2
    assert selector.itemData(0) == 1
    assert selector.itemData(1) == 2


def test_configure_panel_sets_model(qt_app):
    store = _make_store_with_models()
    panel = ConfigurePanel(store)
    panel.show()

    instances = [
        (1, RemoteGGUF(path="/w/a.gguf", filename="a.gguf", size_bytes=1, size_display="1 B")),
    ]
    panel.set_model("a.gguf", "/w/a.gguf", instances, {1}, default_iid=1)
    assert panel._current_path == "/w/a.gguf"
    assert panel._current_iid == 1
    assert panel._form is not None


def test_models_view_empty_state_when_no_instances(qt_app):
    store = LabStore()
    view = ModelsView(store)
    view.show()

    assert len(view._model_index) == 0
    assert len(view._connected_iids) == 0
