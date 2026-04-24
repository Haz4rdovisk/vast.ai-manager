"""AppController owns all worker lifecycles. Tests pin the public contract
the shell will rely on. VastService/SSHService are mocked; workers aren't
started (we test wiring, not threading)."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
from app.controller import AppController
from app.config import ConfigStore
from app.models import AppConfig, Instance, InstanceState, TunnelStatus, UserInfo


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


def test_today_spend_uses_live_tracker_when_billing_has_no_today(store):
    c = AppController(store)
    c.analytics_store._billing_events = [
        {
            "kind": "charge",
            "ts": (datetime.now() - timedelta(days=1)).isoformat(),
            "amount": 1.0,
        }
    ]
    c.tracker._total = 0.42

    assert c.today_spend() == 0.42


def test_live_overlay_respects_instance_uptime(store):
    c = AppController(store)
    c.config.include_storage_in_burn_rate = True
    c.config.estimated_network_cost_per_hour = 0.05
    c.last_instances = [
        Instance(
            id=1,
            state=InstanceState.RUNNING,
            gpu_name="RTX 3090",
            dph=0.50,
            duration_seconds=1800,
            disk_space_gb=200.0,
            storage_total_cost=7.20,
        ),
        Instance(
            id=2,
            state=InstanceState.STOPPED,
            gpu_name="RTX 3090",
            dph=0.0,
            disk_space_gb=200.0,
            storage_total_cost=14.40,
        ),
    ]
    c.analytics_store.last_charge_end = MagicMock(
        return_value=datetime.now() - timedelta(hours=2)
    )

    overlay = c._live_overlay_since(datetime.now() - timedelta(hours=5))

    expected = (
        (0.50 * 0.5) +                  # GPU only for the instance uptime
        ((7.20 / 720.0) * 2.0) +        # running instance storage across window
        ((14.40 / 720.0) * 2.0) +       # stopped instance storage across window
        (0.05 * 2.0)                    # network estimate across window
    )
    assert abs(overlay - expected) < 0.02


def test_on_refreshed_keeps_last_user_during_fast_instance_emit(store):
    c = AppController(store)
    c._check_tunnels_health = MagicMock()
    c._connect_started_instances_when_ready = MagicMock()
    c._sync_live_workers = MagicMock()
    c._log_analytics_snapshot = MagicMock()
    user = UserInfo(balance=2.0, email="user@example.com")

    c._on_refreshed([Instance(id=1, state=InstanceState.RUNNING, gpu_name="RTX 3090")], user)
    c._on_refreshed([Instance(id=1, state=InstanceState.RUNNING, gpu_name="RTX 3090")], None)

    assert c.last_user == user


def test_reset_analytics_clears_store_and_requests_sync(store):
    c = AppController(store)
    c.last_user = UserInfo(balance=2.0, email="user@example.com")
    c.analytics_store.clear_history = MagicMock()
    c.analytics_store.bind_owner = MagicMock()
    c.request_deep_sync = MagicMock()

    c.reset_analytics()

    c.analytics_store.clear_history.assert_called_once()
    c.analytics_store.bind_owner.assert_called_once_with("email:user@example.com")
    c.request_deep_sync.assert_called_once()


def test_controller_shutdown_stops_everything(store):
    c = AppController(store)
    c.ssh = MagicMock()
    c.shutdown()
    c.ssh.stop_all.assert_called_once()


def test_activate_does_not_prompt_passphrase_before_start(store):
    c = AppController(store)
    c.config.auto_connect_on_activate = True
    c.ssh.ssh_key_path = "id_rsa"
    c.ssh.is_passphrase_required = MagicMock(return_value=True)
    c.ssh.passphrase_cache = None
    seen_start = []
    seen_prompt = []
    c._trigger_start.connect(seen_start.append)
    c.passphrase_needed.connect(lambda: seen_prompt.append(True))

    assert c.activate(77) is True

    assert seen_start == [77]
    assert seen_prompt == []


def test_start_action_defers_auto_connect_until_instance_ready(store):
    c = AppController(store)
    c.config.auto_connect_on_activate = True
    c.ssh.ssh_key_path = ""
    c._sync_live_workers = MagicMock()
    c._log_analytics_snapshot = MagicMock()
    seen_connect = []
    c._trigger_connect.connect(lambda iid, port: seen_connect.append((iid, port)))

    c._on_action_done(77, "start", True, "Ativação solicitada")

    assert seen_connect == []
    assert 77 in c._auto_connect_after_start

    c._on_refreshed(
        [
            Instance(
                id=77,
                state=InstanceState.STARTING,
                gpu_name="RTX 3090",
                raw={"actual_status": "scheduling"},
            )
        ],
        UserInfo(balance=1.0),
    )
    assert seen_connect == []
    assert 77 in c._auto_connect_after_start

    c._on_refreshed(
        [
            Instance(
                id=77,
                state=InstanceState.RUNNING,
                gpu_name="RTX 3090",
                ssh_host="ssh.vast.ai",
                ssh_port=2222,
            )
        ],
        UserInfo(balance=1.0),
    )

    assert seen_connect == [(77, 11434)]
    assert 77 not in c._auto_connect_after_start


def test_bulk_start_defers_auto_connect_until_refresh_ready(store):
    c = AppController(store)
    c.config.auto_connect_on_activate = True
    c.ssh.ssh_key_path = ""
    c._sync_live_workers = MagicMock()
    c._log_analytics_snapshot = MagicMock()
    seen_connect = []
    c._trigger_connect.connect(lambda iid, port: seen_connect.append((iid, port)))

    c._on_bulk_finished("start", [1, 2], [])

    assert seen_connect == []
    assert c._auto_connect_after_start == {1, 2}

    c._on_refreshed(
        [
            Instance(id=1, state=InstanceState.RUNNING, gpu_name="RTX 3090", ssh_host="h", ssh_port=1),
            Instance(id=2, state=InstanceState.STARTING, gpu_name="RTX 3090"),
        ],
        UserInfo(balance=1.0),
    )

    assert seen_connect == [(1, 11434)]
    assert c._auto_connect_after_start == {2}
