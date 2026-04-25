from app.lab.state.models import RemoteGGUF, SetupStatus
from app.lab.state.store import LabStore
from app.lab.views.studio_view import StudioView
from app.models import TunnelStatus
from app.ui.app_shell import AppShell


def test_app_shell_accepts_connected_tunnel_as_enum_or_string():
    assert AppShell._is_connected_tunnel(TunnelStatus.CONNECTED) is True
    assert AppShell._is_connected_tunnel(TunnelStatus.CONNECTED.value) is True
    assert AppShell._is_connected_tunnel(TunnelStatus.FAILED) is False


def test_studio_syncs_programmatic_instance_selection_into_dropdown(qt_app):
    store = LabStore()
    store.set_setup_status(1, SetupStatus(probed=True))
    store.set_setup_status(2, SetupStatus(probed=True))
    store.set_remote_gguf(2, [RemoteGGUF(path="/workspace/model.gguf", filename="model.gguf")])
    store.set_instance(2)

    view = StudioView(store)
    view.refresh_instances([1, 2])

    assert view.instance_combo.currentData() == 2
    assert store.selected_instance_id == 2
