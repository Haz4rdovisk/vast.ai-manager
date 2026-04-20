"""Durable tracker for remote install/download jobs."""
from __future__ import annotations

from dataclasses import asdict, replace

from PySide6.QtCore import QObject, Signal

from app.lab.state.models import JobDescriptor


class JobRegistry(QObject):
    job_started = Signal(str)
    job_updated = Signal(str)
    job_finished = Signal(str, bool)
    job_reattached = Signal(str)

    def __init__(self, persist_path: str | None = None, parent=None):
        super().__init__(parent)
        self._active: dict[int, JobDescriptor] = {}
        self._by_key: dict[str, JobDescriptor] = {}
        self._recent: list[JobDescriptor] = []
        self._persist_path = persist_path

    @classmethod
    def in_memory(cls, parent=None) -> "JobRegistry":
        return cls(persist_path=None, parent=parent)

    def can_start(self, iid: int) -> bool:
        return iid not in self._active

    def active_for(self, iid: int) -> JobDescriptor | None:
        return self._active.get(iid)

    def active_items(self) -> list[tuple[str, JobDescriptor]]:
        return [(desc.key, desc) for desc in self._active.values()]

    def active_values(self) -> list[JobDescriptor]:
        return list(self._active.values())

    def active_keys(self) -> list[str]:
        return [desc.key for desc in self._active.values()]

    def get(self, key: str) -> JobDescriptor | None:
        return self._by_key.get(key)

    def start_job(self, desc: JobDescriptor) -> None:
        if desc.iid in self._active:
            raise RuntimeError(f"Instance {desc.iid} already has an active job")
        self._active[desc.iid] = desc
        self._by_key[desc.key] = desc
        self._save_if_needed()
        self.job_started.emit(desc.key)

    def update(self, key: str, **fields) -> None:
        desc = self._by_key.get(key)
        if desc is None:
            return
        new_desc = replace(desc, **fields)
        self._active[desc.iid] = new_desc
        self._by_key[key] = new_desc
        self._save_if_needed()
        self.job_updated.emit(key)

    def finish(self, key: str, ok: bool, error: str | None = None) -> None:
        desc = self._by_key.get(key)
        if desc is None:
            return
        if ok:
            final_stage = "done"
        elif desc.stage == "cancelled":
            final_stage = "cancelled"
        else:
            final_stage = "failed"
        final = replace(desc, stage=final_stage, error=None if ok else error)
        self._active.pop(desc.iid, None)
        self._by_key.pop(key, None)
        self._recent.append(final)
        self._recent = self._recent[-20:]
        self._save_if_needed()
        self.job_finished.emit(key, ok)

    def drop(self, key: str) -> None:
        desc = self._by_key.pop(key, None)
        if desc is None:
            return
        self._active.pop(desc.iid, None)
        self._save_if_needed()

    def mark_reattached(self, key: str) -> None:
        if key in self._by_key:
            self.job_reattached.emit(key)

    def save(self) -> None:
        if self._persist_path is None:
            return
        import json
        import os
        import pathlib

        path = pathlib.Path(self._persist_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._serialize(), indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))

    def load_from_disk(self) -> None:
        if self._persist_path is None:
            return
        import json
        import pathlib

        path = pathlib.Path(self._persist_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"JobRegistry.load_from_disk: ignoring corrupt file ({exc})")
            return
        self._hydrate(payload)

    def _save_if_needed(self) -> None:
        if self._persist_path is not None:
            self.save()

    def _serialize(self) -> dict:
        return {
            "active_jobs": {str(desc.iid): asdict(desc) for desc in self._active.values()},
            "completed_recent": [asdict(desc) for desc in self._recent],
        }

    def _hydrate(self, payload: dict) -> None:
        self._active.clear()
        self._by_key.clear()
        self._recent.clear()
        for raw in (payload.get("active_jobs") or {}).values():
            desc = JobDescriptor(**raw)
            self._active[desc.iid] = desc
            self._by_key[desc.key] = desc
        for raw in payload.get("completed_recent") or []:
            self._recent.append(JobDescriptor(**raw))
