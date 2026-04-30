import time

from PySide6.QtWidgets import QLabel

from app.lab.services.job_registry import JobRegistry
from app.lab.state.store import LabStore
from app.lab.state.models import JobDescriptor
from app.ui.views.instances.jobs_modal import JobsModal


def _job(iid: int, suffix: str, stage: str = "download", percent: int = 0) -> JobDescriptor:
    key = f"{iid}-repo-{suffix}"
    return JobDescriptor(
        key=key,
        iid=iid,
        repo_id="repo/model",
        filename=f"model-{suffix}.gguf",
        quant="Q4_K_M",
        size_bytes=123,
        needs_llamacpp=False,
        remote_state_path=f"/tmp/{key}.json",
        remote_log_path=f"/tmp/{key}.log",
        started_at=time.time(),
        stage=stage,
        percent=percent,
    )


def test_jobs_modal_lists_active_and_recent_jobs(qt_app):
    registry = JobRegistry.in_memory()
    active = _job(1, "active", percent=48)
    recent = _job(2, "recent", stage="done", percent=100)
    registry.start_job(active)
    registry.update(active.key, stage="download", percent=48)
    registry._recent.append(recent)

    modal = JobsModal(registry)
    modal._is_loading = False
    modal.show()
    qt_app.processEvents()
    modal._refresh()
    qt_app.processEvents()

    all_labels = "\n".join(label.text() for label in modal.findChildren(QLabel))
    assert "model-active.gguf" in all_labels
    assert "model-recent.gguf" in all_labels
    assert "#1" in all_labels
    assert "#2" in all_labels
    assert "48%" in all_labels
    assert "DONE" in all_labels


def test_jobs_modal_wraps_long_job_names_in_cards(qt_app):
    registry = JobRegistry.in_memory()
    active = JobDescriptor(
        key="1-repo-long",
        iid=35838665,
        repo_id="repo/model",
        filename="Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf",
        quant="Q4_K_M",
        size_bytes=123,
        needs_llamacpp=False,
        remote_state_path="/tmp/long.json",
        remote_log_path="/tmp/long.log",
        started_at=time.time(),
        stage="build",
        percent=51,
    )
    registry.start_job(active)
    registry.update(active.key, stage="build", percent=51)

    modal = JobsModal(registry)
    modal._is_loading = False
    modal.show()
    qt_app.processEvents()
    modal._refresh()
    qt_app.processEvents()

    name_label = next(
        label for label in modal.findChildren(QLabel)
        if label.text() == "Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
    )

    assert name_label.wordWrap() is True


def test_jobs_modal_shows_lock_without_probed_connection_or_active_jobs(qt_app):
    registry = JobRegistry.in_memory()
    store = LabStore()
    store.get_state(35838665)

    modal = JobsModal(registry, store=store)
    modal._is_loading = False
    modal.show()
    qt_app.processEvents()
    modal._refresh()
    qt_app.processEvents()

    assert modal.layout_stack.currentWidget() is modal.lock_screen
    all_labels = "\n".join(label.text() for label in modal.findChildren(QLabel))
    assert "Global Operations" in all_labels
    assert modal.lock_screen.goto_btn.text() == "Go to Instances"


def test_jobs_modal_shows_content_for_active_jobs_without_probed_connection(qt_app):
    registry = JobRegistry.in_memory()
    store = LabStore()
    store.get_state(35838665)
    active = _job(35838665, "active", stage="build", percent=64)
    registry.start_job(active)
    registry.update(active.key, stage="build", percent=64)

    modal = JobsModal(registry, store=store)
    modal._is_loading = False
    modal.show()
    qt_app.processEvents()
    modal._refresh()
    qt_app.processEvents()

    assert modal.layout_stack.currentWidget() is modal.content_widget
    all_labels = "\n".join(label.text() for label in modal.findChildren(QLabel))
    assert "model-active.gguf" in all_labels
    assert "64%" in all_labels
