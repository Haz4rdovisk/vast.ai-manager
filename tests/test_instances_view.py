from unittest.mock import ANY, MagicMock

from app.models import AppConfig, Instance, InstanceState, UserInfo
from app.services.port_allocator import PortAllocator
from app.ui.views.instances.instances_view import InstancesView


def _inst(iid, state=InstanceState.RUNNING, label=None, raw=None):
    return Instance(
        id=iid,
        state=state,
        gpu_name="RTX 3090",
        num_gpus=1,
        gpu_ram_gb=24,
        image="img",
        dph=0.5,
        label=label,
        raw=raw or {},
    )


def _controller(config=None):
    ctl = MagicMock(
        last_instances=[],
        last_user=None,
        config=config or AppConfig(),
        tunnel_states={},
    )
    ctl.port_allocator = PortAllocator(11434, {}, lambda _m: None)
    ctl.update_start_requested_ids = MagicMock()
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


def test_scheduling_survives_stopped_refresh_after_start(qt_app):
    ctl = _controller()
    view = InstancesView(ctl)
    view.handle_refresh([_inst(1, state=InstanceState.STOPPED)], UserInfo(balance=5.0, email=""))

    view._cards[1].activate_requested.emit(1)
    view.handle_refresh([_inst(1, state=InstanceState.STOPPED)], UserInfo(balance=5.0, email=""))

    assert view._cards[1].actions.primary.text() == "scheduling..."
    assert 1 in view._start_requested_ids
    ctl.update_start_requested_ids.assert_called_with([1], ANY)


def test_running_refresh_clears_sticky_scheduling(qt_app):
    ctl = _controller()
    view = InstancesView(ctl)
    view.handle_refresh([_inst(1, state=InstanceState.STOPPED)], UserInfo(balance=5.0, email=""))

    view._cards[1].activate_requested.emit(1)
    view.handle_refresh([_inst(1, state=InstanceState.RUNNING)], UserInfo(balance=5.0, email=""))

    assert view._cards[1].actions.primary.text() == "Connect"
    assert 1 not in view._start_requested_ids
    ctl.update_start_requested_ids.assert_called_with([], {})


def test_failed_start_action_clears_sticky_scheduling(qt_app):
    ctl = _controller()
    view = InstancesView(ctl)
    view.handle_refresh([_inst(1, state=InstanceState.STOPPED)], UserInfo(balance=5.0, email=""))

    view._cards[1].activate_requested.emit(1)
    view._on_action_done(1, "start", False, "no capacity")
    view.handle_refresh([_inst(1, state=InstanceState.STOPPED)], UserInfo(balance=5.0, email=""))

    assert view._cards[1].actions.primary.text() == "Activate"
    assert 1 not in view._start_requested_ids
    ctl.update_start_requested_ids.assert_called_with([], {})


def test_persisted_start_request_restores_scheduling_on_open(qt_app):
    ctl = _controller(AppConfig(start_requested_ids=[1]))
    view = InstancesView(ctl)

    view.handle_refresh([_inst(1, state=InstanceState.STOPPED)], UserInfo(balance=5.0, email=""))

    assert view._cards[1].actions.primary.text() == "scheduling..."
    assert 1 in view._start_requested_ids
    ctl.update_start_requested_ids.assert_not_called()


def test_persisted_start_request_clears_when_running_on_open(qt_app):
    ctl = _controller(AppConfig(start_requested_ids=[1]))
    view = InstancesView(ctl)

    view.handle_refresh([_inst(1, state=InstanceState.RUNNING)], UserInfo(balance=5.0, email=""))

    assert view._cards[1].actions.primary.text() == "Connect"
    assert 1 not in view._start_requested_ids
    ctl.update_start_requested_ids.assert_called_with([], {})


def test_server_scheduling_state_wins_without_local_start_request(qt_app):
    ctl = _controller()
    view = InstancesView(ctl)

    view.handle_refresh(
        [
            _inst(
                1,
                state=InstanceState.STARTING,
                raw={"actual_status": "exited", "intended_status": "running"},
            )
        ],
        UserInfo(balance=5.0, email=""),
    )

    assert view._cards[1].actions.primary.text() == "scheduling..."
    assert 1 not in view._start_requested_ids
    ctl.update_start_requested_ids.assert_not_called()


def test_persisted_start_request_stays_scheduling_even_if_server_reports_stopped(qt_app):
    ctl = _controller(AppConfig(start_requested_ids=[1], start_requested_at={1: 1.0}))
    view = InstancesView(ctl)

    view.handle_refresh(
        [
            _inst(
                1,
                state=InstanceState.STOPPED,
                raw={"actual_status": "exited", "intended_status": "stopped"},
            )
        ],
        UserInfo(balance=5.0, email=""),
    )

    assert view._cards[1].actions.primary.text() == "scheduling..."
    assert 1 in view._start_requested_ids
    ctl.update_start_requested_ids.assert_not_called()
