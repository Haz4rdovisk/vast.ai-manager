"""The Instances view renders one InstanceCard per instance emitted by the
controller, handles empty state, and relays card signals to controller methods."""
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication
from app.ui.views.instances_view import InstancesView
from app.models import AppConfig, Instance, InstanceState, UserInfo


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _inst(iid, state=InstanceState.RUNNING):
    return Instance(
        id=iid, label=f"#{iid}", state=state, gpu_name="RTX 3090",
        num_gpus=1, gpu_ram_gb=24, image="img", dph=0.5,
    )


def test_empty_state_shown_initially(qapp):
    ctl = MagicMock(last_instances=[], last_user=None, config=AppConfig(),
                    tunnel_states={})
    v = InstancesView(ctl)
    assert v.empty_lbl.isVisible()


def test_renders_cards_on_refresh(qapp):
    ctl = MagicMock(last_instances=[], last_user=None, config=AppConfig(),
                    tunnel_states={})
    v = InstancesView(ctl)
    v.handle_refresh([_inst(1), _inst(2)], UserInfo(balance=5.0, email=""))
    assert len(v.cards) == 2
    assert not v.empty_lbl.isVisible()


def test_card_activate_calls_controller(qapp):
    ctl = MagicMock(last_instances=[], last_user=None, config=AppConfig(),
                    tunnel_states={})
    v = InstancesView(ctl)
    v.handle_refresh([_inst(1, state=InstanceState.STOPPED)],
                     UserInfo(balance=5.0, email=""))
    v.cards[1].activate_requested.emit(1)
    ctl.activate.assert_called_once_with(1)
