from app.models import Instance, InstanceState, TunnelStatus, UserInfo
from app.ui.views.instances.instances_view import InstancesView
from unittest.mock import MagicMock, ANY
from app.models import AppConfig
from app.services.port_allocator import PortAllocator


def _ctl(config=None):
    ctl = MagicMock(
        last_instances=[],
        last_user=None,
        config=config or AppConfig(),
        tunnel_states={},
    )
    ctl.port_allocator = PortAllocator(11434, {}, lambda _m: None)
    ctl.update_start_requested_ids = MagicMock()
    return ctl


def _inst(iid, state=InstanceState.RUNNING, raw=None):
    return Instance(
        id=iid, state=state, gpu_name="RTX 3090", num_gpus=1,
        gpu_ram_gb=24, image="img", dph=0.5, raw=raw or {},
    )


def test_full_outbid_flow(qt_app):
    """Instance goes from RUNNING -> OUTBID and the UI reflects it correctly."""
    ctl = _ctl()
    view = InstancesView(ctl)

    # 1. Instance is running
    view.handle_refresh(
        [_inst(1, state=InstanceState.RUNNING, raw={"actual_status": "running"})],
        UserInfo(balance=5.0, email=""),
    )
    assert view._cards[1].header.status_chip.label.text() == "RUNNING"
    assert view._cards[1].actions.primary.text() == "Connect"
    assert view._cards[1].actions.primary.isEnabled() is True

    # 2. Instance gets outbid
    view.handle_refresh(
        [_inst(1, state=InstanceState.OUTBID, raw={"actual_status": "exited", "intended_status": "running", "_is_outbid": True})],
        UserInfo(balance=5.0, email=""),
    )
    assert view._cards[1].header.status_chip.label.text() == "OUTBID"
    assert view._cards[1].actions.primary.text() == "Unavailable"
    assert view._cards[1].actions.primary.isEnabled() is False
    assert "outbid" in view._cards[1].actions.primary.toolTip().lower()
