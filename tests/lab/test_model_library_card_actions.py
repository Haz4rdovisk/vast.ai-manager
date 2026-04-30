from PySide6.QtTest import QSignalSpy

from app.lab.state.models import LabInstanceState, RemoteGGUF
from app.lab.state.store import LabStore
from app.lab.views.models_view import ModelsView


def _build_view_for_card(*, running_model: str = "") -> ModelsView:
    store = LabStore()
    st = LabInstanceState(iid=1)
    st.setup.probed = True
    st.setup.llama_server_running = bool(running_model)
    st.setup.llama_server_model = running_model
    st.gguf = [
        RemoteGGUF(
            path="/workspace/model-a.gguf",
            filename="model-a.gguf",
            size_bytes=1024,
            size_display="1.0 KB",
        )
    ]
    store.instance_states[1] = st
    view = ModelsView(store)
    view.show()
    return view


def test_model_library_card_enables_eject_only_for_running_model(qt_app):
    running_view = _build_view_for_card(running_model="/workspace/model-a.gguf")
    running_btn = running_view.findChild(type(running_view.configure_panel._save_btn), "model-card-eject-btn")
    assert running_btn is not None
    assert running_btn.isEnabled() is True

    stopped_view = _build_view_for_card(running_model="/workspace/other-model.gguf")
    stopped_btn = stopped_view.findChild(type(stopped_view.configure_panel._save_btn), "model-card-eject-btn")
    assert stopped_btn is not None
    assert stopped_btn.isEnabled() is False


def test_model_library_card_emits_stop_request_for_selected_instance(qt_app):
    view = _build_view_for_card(running_model="/workspace/model-a.gguf")
    eject_btn = view.findChild(type(view.configure_panel._save_btn), "model-card-eject-btn")
    spy = QSignalSpy(view.stop_requested)

    eject_btn.click()

    assert spy.count() == 1
    assert spy.at(0)[0] == 1


def test_model_library_card_action_buttons_share_consistent_dimensions(qt_app):
    view = _build_view_for_card(running_model="/workspace/model-a.gguf")

    configure_btn = view.findChild(type(view.configure_panel._save_btn), "model-card-configure-btn")
    eject_btn = view.findChild(type(view.configure_panel._save_btn), "model-card-eject-btn")
    launch_btn = view.findChild(type(view.configure_panel._save_btn), "model-card-launch-btn")
    delete_btn = view.findChild(type(view.configure_panel._save_btn), "model-card-delete-btn")

    assert configure_btn is not None
    assert eject_btn is not None
    assert launch_btn is not None
    assert delete_btn is not None

    assert configure_btn.height() == 54
    assert eject_btn.height() == 54
    assert launch_btn.height() == 54
    assert delete_btn.height() == 54
    assert delete_btn.width() == 54
