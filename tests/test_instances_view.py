from unittest.mock import MagicMock

from app.models import AppConfig, Instance, InstanceState, UserInfo
from app.services.port_allocator import PortAllocator
from app.ui.views.instances.instances_view import InstancesView


def _inst(iid, state=InstanceState.RUNNING, label=None):
    return Instance(
        id=iid,
        state=state,
        gpu_name="RTX 3090",
        num_gpus=1,
        gpu_ram_gb=24,
        image="img",
        dph=0.5,
        label=label,
    )


def _controller():
    ctl = MagicMock(last_instances=[], last_user=None, config=AppConfig(), tunnel_states={})
    ctl.port_allocator = PortAllocator(11434, {}, lambda _m: None)
    return ctl


def test_renders_cards_on_refresh(qt_app):
    ctl = _controller()
    view = InstancesView(ctl)
    view.handle_refresh([_inst(1), _inst(2)], UserInfo(balance=5.0, email=""))
    assert len(view._cards) == 2


def test_filter_hides_cards(qt_app):
    ctl = _controller()
    view = InstancesView(ctl)
    view.handle_refresh(
        [_inst(1, state=InstanceState.RUNNING), _inst(2, state=InstanceState.STOPPED)],
        UserInfo(balance=5.0, email=""),
    )
    view.filter_bar.status_combo.setCurrentIndex(
        view.filter_bar.status_combo.findData("running")
    )
    assert set(view._cards) == {1}


def test_card_activate_relay(qt_app):
    ctl = _controller()
    view = InstancesView(ctl)
    view.handle_refresh([_inst(1, state=InstanceState.STOPPED)], UserInfo(balance=5.0, email=""))
    seen = []
    view.activate_requested.connect(seen.append)
    view._cards[1].activate_requested.emit(1)
    assert seen == [1]
    assert view._cards[1].actions.primary.text() == "scheduling..."
    assert "GPU is currently in use" in view._cards[1].actions.primary.toolTip()


def test_bulk_start_marks_visible_cards_as_scheduling(qt_app, monkeypatch):
    import app.ui.views.instances.instances_view as module

    class FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return self.DialogCode.Accepted

        def collect_opts(self):
            return {"auto_connect": True}

    monkeypatch.setattr(module, "ConfirmBulkDialog", FakeDialog)
    ctl = _controller()
    view = InstancesView(ctl)
    view.handle_refresh(
        [_inst(1, state=InstanceState.STOPPED), _inst(2, state=InstanceState.STOPPED)],
        UserInfo(balance=5.0, email=""),
    )
    seen = []
    view.bulk_requested.connect(lambda action, ids, opts: seen.append((action, ids, opts)))

    view._bulk_from_visible("start")

    assert seen == [("start", [1, 2], {"auto_connect": True})]
    assert view._cards[1].actions.primary.text() == "scheduling..."
    assert view._cards[2].actions.primary.text() == "scheduling..."
