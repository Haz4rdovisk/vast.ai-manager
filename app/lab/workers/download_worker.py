from __future__ import annotations
import os
from PySide6.QtCore import QThread, Signal
from app.lab.services.downloader import build_hf_url, download


class DownloadWorker(QThread):
    progress = Signal(int, int, float)   # downloaded, total, speed
    finished_ok = Signal(str)            # final path
    failed = Signal(str)

    def __init__(self, entry_id: str, repo_id: str, filename: str,
                 dest_dir: str, hf_token: str | None = None, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id
        self.repo_id = repo_id
        self.filename = filename
        self.dest_dir = dest_dir
        self.hf_token = hf_token
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        if not os.path.isdir(self.dest_dir):
            try:
                os.makedirs(self.dest_dir, exist_ok=True)
            except OSError as e:
                self.failed.emit(f"Cannot create {self.dest_dir}: {e}")
                return
        dest = os.path.join(self.dest_dir, self.filename)
        url = build_hf_url(self.repo_id, self.filename)
        try:
            download(
                url, dest, hf_token=self.hf_token,
                progress_cb=lambda d, t, s: self.progress.emit(d, t, s),
                cancel_cb=lambda: self._cancel,
            )
        except Exception as e:
            self.failed.emit(str(e))
            return
        if self._cancel:
            self.failed.emit("Cancelled.")
            return
        self.finished_ok.emit(dest)
