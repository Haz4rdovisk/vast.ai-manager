"""AppController owns all worker lifecycles. Tests pin the public contract
the shell will rely on. VastService/SSHService are mocked; workers aren't
started (we test wiring, not threading)."""
from unittest.mock import MagicMock, patch
import pytest
from app.controller import AppController
from app.config import ConfigStore
from app.models import AppConfig, InstanceState, TunnelStatus


@pytest.fixture
def config():
    return AppConfig(api_key="fake", refresh_interval_seconds=30,
                     default_tunnel_port=11434)


@pytest.fixture
def store(tmp_path, config):
    s = ConfigStore(path=tmp_path / "config.json")
    s.save(config)
    return s


def test_controller_starts_uninitialized(store):
    c = AppController(store)
    assert c.vast is None
    assert c.last_instances == []
    assert c.today_spend() == 0.0


def test_controller_bootstrap_creates_workers(store):
    c = AppController(store)
    with patch("app.controller.VastService") as VS:
        VS.return_value = MagicMock()
        c.bootstrap()
    assert c.vast is not None
    assert c.list_worker is not None
    assert c.action_worker is not None
    assert c.tunnel_starter is not None


def test_controller_signals_exposed(store):
    c = AppController(store)
    for sig in ("instances_refreshed", "refresh_failed", "tunnel_status_changed",
                "action_done", "live_metrics", "model_changed", "log_line"):
        assert hasattr(c, sig), f"missing signal {sig}"


def test_controller_tunnel_state_tracking(store):
    c = AppController(store)
    c._on_tunnel_status(123, TunnelStatus.CONNECTED.value, "ok")
    assert c.tunnel_states[123] == TunnelStatus.CONNECTED


def test_controller_shutdown_stops_everything(store):
    c = AppController(store)
    c.ssh = MagicMock()
    c.shutdown()
    c.ssh.stop_all.assert_called_once()
