from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class BulkActionWorker(QObject):
    """Execute a bulk action sequentially against multiple instance ids."""

    progress = Signal(int, int, int, str)
    finished = Signal(str, list, list)

    def __init__(self, vast) -> None:
        super().__init__()
        self.vast = vast

    @Slot(str, list, dict)
    def run(self, action: str, ids: list, opts: dict) -> None:
        ok: list[int] = []
        fail: list[int] = []
        total = len(ids)
        for index, iid in enumerate(ids, start=1):
            try:
                self._dispatch(action, iid, opts)
                ok.append(iid)
                self.progress.emit(index, total, iid, "ok")
            except Exception as exc:
                fail.append(iid)
                self.progress.emit(index, total, iid, str(exc)[:80])
        self.finished.emit(action, ok, fail)

    def _dispatch(self, action: str, iid: int, opts: dict) -> None:
        if action == "start":
            self.vast.start_instance(iid)
        elif action == "stop":
            self.vast.stop_instance(iid)
        elif action == "destroy":
            self.vast.destroy_instance(iid)
        elif action == "label":
            self.vast.set_label(iid, opts["label"])
        else:
            raise ValueError(f"Unknown bulk action: {action}")
