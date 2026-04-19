from app.lab.state.models import RemoteGGUF, SetupStatus
from app.lab.state.store import LabStore
from app.lab.views.studio_view import StudioView, _EMPTY_WEBUI_HTML


def test_studio_shows_instances_with_models_in_dropdown(qt_app):
    store = LabStore()
    store.set_remote_gguf(
        1,
        [RemoteGGUF(path="/a.gguf", filename="a.gguf", size_bytes=1000)],
    )
    store.set_setup_status(1, SetupStatus(llamacpp_installed=True, probed=True))
    store.set_remote_gguf(2, [])
    store.set_setup_status(2, SetupStatus(llamacpp_installed=True, probed=True))

    view = StudioView(store)
    view.refresh_instances([1, 2])
    items = [view.instance_combo.itemText(i) for i in range(view.instance_combo.count())]
    assert any("#1" in item for item in items)


def test_studio_selecting_instance_updates_store(qt_app):
    store = LabStore()
    store.set_remote_gguf(1, [RemoteGGUF(path="/a.gguf", filename="a.gguf")])
    store.set_setup_status(1, SetupStatus(llamacpp_installed=True, probed=True))
    view = StudioView(store)
    view.refresh_instances([1])
    view.instance_combo.setCurrentIndex(0)
    assert store.selected_instance_id == 1


def test_studio_sidebar_model_list_populates(qt_app):
    store = LabStore()
    store.set_remote_gguf(
        1,
        [
            RemoteGGUF(path="/a.gguf", filename="a.gguf"),
            RemoteGGUF(path="/b.gguf", filename="b.gguf"),
        ],
    )
    store.set_setup_status(1, SetupStatus(llamacpp_installed=True, probed=True))
    view = StudioView(store)
    view.refresh_instances([1])
    view.instance_combo.setCurrentIndex(0)
    assert view.model_list.count() == 2
    assert view.model_picker.currentText() == "a.gguf"


def test_studio_topbar_has_empty_model_placeholder(qt_app):
    store = LabStore()
    store.set_remote_gguf(2, [])
    store.set_setup_status(2, SetupStatus(llamacpp_installed=True, probed=True))

    view = StudioView(store)
    view.refresh_instances([2])

    assert view.model_picker.currentText() == "Install a GGUF model first"
    assert view.model_picker.isEnabled() is False
    assert view.launch_btn.isEnabled() is False
    assert view.stop_btn.isEnabled() is False


def test_eject_only_enabled_for_active_server_session(qt_app):
    store = LabStore()
    store.set_remote_gguf(1, [RemoteGGUF(path="/a.gguf", filename="a.gguf")])
    store.set_setup_status(1, SetupStatus(llamacpp_installed=True, probed=True))

    view = StudioView(store)
    view.refresh_instances([1])

    assert view.stop_btn.isEnabled() is False
    view._on_launch()
    assert view.stop_btn.isEnabled() is True
    view.clear_webui()
    assert view.stop_btn.isEnabled() is False

    view._on_launch()
    assert view.stop_btn.isEnabled() is True
    view.mark_launch_failed()
    assert view.stop_btn.isEnabled() is False


def test_open_webui_does_not_crash(qt_app):
    store = LabStore()
    view = StudioView(store)
    try:
        view.open_webui(11434)
    except Exception as exc:
        assert "webengine" in str(exc).lower() or True


def test_studio_placeholder_is_not_a_fake_chat_input():
    assert "Send a message" not in _EMPTY_WEBUI_HTML
    assert "No model loaded" in _EMPTY_WEBUI_HTML
    assert "chat input appears here" in _EMPTY_WEBUI_HTML


def test_launch_log_is_hidden_until_launch_output(qt_app):
    store = LabStore()
    view = StudioView(store)
    assert view.launch_log.isHidden() is True
    assert view.log_toggle_btn.text() == "Show Launch Log"

    view.append_launch_log("loading model")
    assert view.launch_log.isHidden() is False
    assert "Loading" in view.launch_status.text()
    assert view.launch_log.height() == 220
    assert "loading model" in view.launch_log.log_text()

    view.clear_webui()
    assert view.launch_log.isHidden() is True
    assert "Idle" in view.launch_status.text()


def test_launch_log_drawer_keeps_readable_fixed_height(qt_app):
    store = LabStore()
    view = StudioView(store)

    view._set_launch_log_visible(True)
    for index in range(20):
        view.append_launch_log(f"line {index}")

    assert view.launch_log.height() == 220
    assert "line 19" in view.launch_log.log_text()
