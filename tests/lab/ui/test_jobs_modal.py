import time

from PySide6.QtWidgets import QLabel

from app.lab.services.job_registry import JobRegistry
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
