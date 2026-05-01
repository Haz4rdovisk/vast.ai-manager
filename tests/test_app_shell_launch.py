from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtWebEngineCore import QWebEnginePage

from app.lab.state.models import SetupStatus, ServerParams
from app.lab.state.store import LabStore
from app.models import AppConfig
from app.ui.app_shell import AppShell


def _make_shell(tmp_path, qt_app):
    shell = AppShell(
        config=AppConfig(),
        config_store=None,
        ssh_service=MagicMock(),
        analytics_store=None,
    )
    shell._controller = SimpleNamespace(
        last_instances=[SimpleNamespace(id=7, ssh_host="host", ssh_port=22)],
        log_line=SimpleNamespace(emit=lambda *_args, **_kwargs: None),
    )
    shell.store.set_instance(7)
    shell.store.set_setup_status(7, SetupStatus(probed=True, llamacpp_installed=True, llamacpp_path="/opt/llama.cpp/build/bin/llama-server"))
    return shell


def _drain_qt(qt_app, cycles: int = 2):
    for _ in range(cycles):
        qt_app.processEvents()


def test_launch_server_uses_selected_instance_when_iid_omitted(qt_app, tmp_path):
    shell = _make_shell(tmp_path, qt_app)
    shell._setup_workers = {}

    worker = MagicMock()
    worker.line = MagicMock()
    worker.finished = MagicMock()

    with patch("app.ui.app_shell.StreamingRemoteWorker", return_value=worker) as worker_cls:
        shell._launch_server(ServerParams(model_path="/workspace/model.gguf"))

    worker_cls.assert_called_once()
    args = worker_cls.call_args.args
    assert args[1] == "host"
    assert args[2] == 22
    assert 7 in shell._setup_workers


def test_stop_server_accepts_explicit_instance_id(qt_app, tmp_path):
    shell = _make_shell(tmp_path, qt_app)
    shell.studio.clear_webui = MagicMock()
    shell._run_single_setup = MagicMock()

    shell._stop_server(9)

    shell._run_single_setup.assert_called_once_with("stop_server", 9)
    shell.studio.clear_webui.assert_not_called()


def test_switching_tabs_keeps_live_studio_page_active(qt_app, tmp_path):
    shell = _make_shell(tmp_path, qt_app)
    shell.studio.webui_stack.setCurrentWidget(shell.studio.webui)
    shell.show()
    _drain_qt(qt_app)

    page = shell.studio.webui.page()
    assert page.isVisible() is True
    assert page.lifecycleState() == QWebEnginePage.LifecycleState.Active

    shell._switch("settings")
    _drain_qt(qt_app)

    assert page.isVisible() is True
    assert page.lifecycleState() == QWebEnginePage.LifecycleState.Active
