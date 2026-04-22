import time

from PySide6.QtTest import QTest
from PySide6.QtTest import QSignalSpy

from app.lab.services.huggingface import HFModel, HFModelFile
from app.lab.services.job_registry import JobRegistry
from app.lab.state.models import JobDescriptor, RemoteGGUF, RemoteSystem, SetupStatus
from app.lab.state.store import LabStore
from app.lab.views.install_panel_side import InstallPanelSide, _remote_has_selected_file


def _panel():
    store = LabStore()
    registry = JobRegistry.in_memory()
    panel = InstallPanelSide(store, registry)
    return panel, store, registry


def _model():
    return HFModel(
        id="a/b",
        author="a",
        name="b-gguf",
        downloads=1,
        likes=1,
        tags=[],
        files=[HFModelFile("b-Q4_K_M.gguf", 4_000_000_000, "Q4_K_M")],
    )


def _ready_store(store):
    store.set_instance(1)
    state = store.get_state(1)
    state.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    state.setup = SetupStatus(llamacpp_installed=True, probed=True)


def test_panel_starts_in_idle_mode(qt_app):
    panel, _, _ = _panel()
    assert panel.mode == "idle"


def test_set_model_switches_to_ready_mode(qt_app):
    panel, _, _ = _panel()
    panel.set_model(_model())
    assert panel.mode == "ready"
    assert panel.current_model.id == "a/b"
    assert panel._quant_combo.count() == 1


def test_ready_mode_renders_instance_card_and_confirm_emits(qt_app):
    panel, store, _ = _panel()
    _ready_store(store)
    panel.set_model(_model())
    assert len(panel._instance_cards) == 1
    assert panel._instance_cards[1].iid == 1
    spy = QSignalSpy(panel.install_requested)
    panel.show_confirm_overlay(1)
    panel._instance_cards[1]._btn_confirm.click()
    assert spy.count() == 1
    assert spy.at(0) == [1, "a/b", "b-Q4_K_M.gguf"]


def test_busy_mode_reflects_registry_updates_and_cancel(qt_app):
    panel, store, registry = _panel()
    _ready_store(store)
    desc = JobDescriptor(
        key="1-a-b-q4_k_m",
        iid=1,
        repo_id="a/b",
        filename="b-Q4_K_M.gguf",
        quant="Q4_K_M",
        size_bytes=1,
        needs_llamacpp=False,
        remote_state_path="/tmp/s",
        remote_log_path="/tmp/l",
        started_at=time.time(),
    )
    registry.start_job(desc)
    panel.set_model(_model())
    assert panel.mode == "busy"
    registry.update(desc.key, stage="download", percent=50)
    assert panel._progress.stage_state("download") == "running"
    assert panel._progress.percent() == 50
    spy = QSignalSpy(panel.cancel_requested)
    panel._cancel_btn.click()
    panel._cancel_confirm_yes.click()
    assert spy.count() == 1
    assert spy.at(0)[0] == desc.key


def test_setup_only_job_uses_same_busy_card_when_started_from_instance_card(qt_app):
    panel, store, registry = _panel()
    _ready_store(store)
    panel.set_model(_model())
    panel.show_confirm_overlay(1, mode="setup")

    desc = JobDescriptor(
        key="1-system-setup",
        iid=1,
        repo_id="Environment",
        filename="llama.cpp (CUDA Build)",
        quant="SETUP",
        size_bytes=0,
        needs_llamacpp=True,
        remote_state_path="/tmp/s",
        remote_log_path="/tmp/l",
        started_at=time.time(),
    )
    registry.start_job(desc)
    registry.update(desc.key, stage="build", percent=64)

    assert panel.mode == "busy"
    assert "llama.cpp" in panel._busy_title.text()
    assert panel._progress.percent() == 64


def test_confirm_deploy_enters_pending_busy_state_immediately(qt_app):
    panel, store, _ = _panel()
    _ready_store(store)
    panel.set_model(_model())

    spy = QSignalSpy(panel.install_requested)
    panel.show_confirm_overlay(1, mode="deploy")
    panel._instance_cards[1]._btn_confirm.click()
    qt_app.processEvents()

    assert spy.count() == 1
    assert panel.mode == "busy"
    active = panel._current_active_job()
    assert active is not None
    assert active.stage == "download"
    assert active.percent == 0
    assert "b-Q4_K_M.gguf" in panel._busy_title.text()


def test_append_log_filters_progress_noise_and_awk_spam(qt_app):
    panel, store, registry = _panel()
    _ready_store(store)
    panel.set_model(_model())

    desc = JobDescriptor(
        key="1-a-b-q4_k_m",
        iid=1,
        repo_id="a/b",
        filename="b-Q4_K_M.gguf",
        quant="Q4_K_M",
        size_bytes=1,
        needs_llamacpp=False,
        remote_state_path="/tmp/s",
        remote_log_path="/tmp/l",
        started_at=time.time(),
    )
    registry.start_job(desc)
    registry.update(desc.key, stage="download", percent=48)
    qt_app.processEvents()

    panel.append_log(desc.key, "DOWNLOAD_PROGRESS|48|480|1000|2.0 MB/s")
    panel.append_log(desc.key, "awk: line 1: syntax error at or near %")
    panel.append_log(desc.key, "Downloading clean.gguf from HuggingFace...")
    qt_app.processEvents()

    master_log = panel._progress.log_text()
    card_log = panel._instance_cards[1]._log_view.toPlainText()
    assert "DOWNLOAD_PROGRESS|" not in master_log
    assert "awk: line 1" not in master_log
    assert "Downloading clean.gguf from HuggingFace..." in master_log
    assert "DOWNLOAD_PROGRESS|" not in card_log
    assert "awk: line 1" not in card_log
    assert "Downloading clean.gguf from HuggingFace..." in card_log


def test_pending_job_expires_if_registry_never_starts(qt_app):
    panel, store, _ = _panel()
    _ready_store(store)
    panel.set_model(_model())

    panel._start_pending_job(1, "b-Q4_K_M.gguf", "download")
    assert panel.mode == "busy"

    QTest.qWait(2700)
    qt_app.processEvents()

    assert panel._current_active_job() is None
    assert panel.mode == "ready"


def test_remote_selected_file_detection_matches_filename_and_path(qt_app):
    panel, store, _ = _panel()
    _ready_store(store)
    state = store.get_state(1)
    state.gguf = [
        RemoteGGUF(
            path="/workspace/models/b-Q4_K_M.gguf",
            filename="b-Q4_K_M.gguf",
            size_bytes=4_000_000_000,
            size_display="3.7 GB",
        )
    ]
    selected_file = _model().files[0]

    assert _remote_has_selected_file(state, selected_file) is True


def test_installed_selected_file_disables_deploy_cta(qt_app):
    panel, store, _ = _panel()
    _ready_store(store)
    state = store.get_state(1)
    state.gguf = [
        RemoteGGUF(
            path="/workspace/models/b-Q4_K_M.gguf",
            filename="b-Q4_K_M.gguf",
            size_bytes=4_000_000_000,
            size_display="3.7 GB",
        )
    ]

    panel.set_model(_model())
    card = panel._instance_cards[1]

    assert card._btn_deploy.text() == "Installed"
    assert card._btn_deploy.isEnabled() is False
    assert card._runtime_chip.text() == "Installed"
    assert "Already on instance." in card._action_hint.text()
