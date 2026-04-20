import time

from PySide6.QtTest import QSignalSpy

from app.lab.services.huggingface import HFModel, HFModelFile
from app.lab.services.job_registry import JobRegistry
from app.lab.state.models import JobDescriptor, RemoteSystem, SetupStatus
from app.lab.state.store import LabStore
from app.lab.views.install_panel_side import InstallPanelSide


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
    assert panel._instance_cards[0].iid == 1
    spy = QSignalSpy(panel.install_requested)
    panel.show_confirm_overlay(1)
    panel._confirm_btn.click()
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
