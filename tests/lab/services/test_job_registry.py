import json
import time

from PySide6.QtTest import QSignalSpy

from app.lab.services.job_registry import JobRegistry
from app.lab.state.models import JobDescriptor


def _mk(iid: int, key_suffix: str = "a") -> JobDescriptor:
    key = f"{iid}-x-{key_suffix}"
    return JobDescriptor(
        key=key,
        iid=iid,
        repo_id="x/y",
        filename="f.gguf",
        quant="Q4_K_M",
        size_bytes=1000,
        needs_llamacpp=False,
        remote_state_path=f"/tmp/{key}.json",
        remote_log_path=f"/tmp/{key}.log",
        started_at=time.time(),
    )


def test_start_job_locks_instance_and_emits_signal(qt_app):
    registry = JobRegistry.in_memory()
    desc = _mk(42)
    spy = QSignalSpy(registry.job_started)
    registry.start_job(desc)
    assert spy.count() == 1
    assert spy.at(0)[0] == desc.key
    assert registry.can_start(42) is False
    assert registry.active_for(42).key == desc.key


def test_update_and_finish_release_lock(qt_app):
    registry = JobRegistry.in_memory()
    desc = _mk(7)
    registry.start_job(desc)
    update_spy = QSignalSpy(registry.job_updated)
    registry.update(desc.key, stage="download", percent=43)
    assert update_spy.count() == 1
    assert registry.active_for(7).stage == "download"
    assert registry.active_for(7).percent == 43

    finish_spy = QSignalSpy(registry.job_finished)
    registry.finish(desc.key, ok=True)
    assert finish_spy.count() == 1
    assert registry.can_start(7) is True


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "jobs.json"
    first = JobRegistry(persist_path=str(path))
    desc = _mk(99, "zz")
    first.start_job(desc)
    assert "99" in json.loads(path.read_text())["active_jobs"]

    second = JobRegistry(persist_path=str(path))
    second.load_from_disk()
    assert second.can_start(99) is False
    assert second.active_for(99).key == desc.key


def test_load_from_disk_handles_corrupt_file(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("{{{ not json")
    registry = JobRegistry(persist_path=str(path))
    registry.load_from_disk()
    assert registry.active_items() == []
