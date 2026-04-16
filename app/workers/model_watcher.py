from __future__ import annotations
import json
import time
import urllib.error
import urllib.request
from PySide6.QtCore import QThread, Signal


def _extract_model_id(body: str) -> str:
    """Parse the OpenAI /v1/models response and return the first model id."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict):
        arr = data.get("data") or []
        if arr and isinstance(arr[0], dict):
            return str(arr[0].get("id") or "")
    return ""


class ModelWatcher(QThread):
    """Polls the local tunneled llama-server /v1/models periodically and emits
    `model_changed(instance_id, model_id_or_empty)` whenever the answer changes.

    Empty string means: no llama-server reachable (port closed, 5xx, etc.).
    """
    model_changed = Signal(int, str)

    def __init__(self, instance_id: int, local_port: int,
                 interval_s: int = 10, parent=None):
        super().__init__(parent)
        self.instance_id = instance_id
        self.local_port = local_port
        self.interval_s = max(2, interval_s)
        self._stop = False
        self._last: str | None = None

    def stop(self):
        self._stop = True

    def run(self):
        url = f"http://127.0.0.1:{self.local_port}/v1/models"
        while not self._stop:
            mid = ""
            try:
                req = urllib.request.Request(
                    url, headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=2) as r:
                    if r.status == 200:
                        body = r.read().decode("utf-8", errors="replace")
                        mid = _extract_model_id(body)
            except (urllib.error.URLError, urllib.error.HTTPError,
                    ConnectionError, OSError):
                mid = ""
            except Exception:
                mid = ""

            if mid != self._last:
                self._last = mid
                self.model_changed.emit(self.instance_id, mid)

            # Sleep in small slices for prompt cancellation.
            for _ in range(self.interval_s * 10):
                if self._stop:
                    return
                time.sleep(0.1)
