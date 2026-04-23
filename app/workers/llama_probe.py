from __future__ import annotations
import json
import time
import urllib.error
import urllib.request
from PySide6.QtCore import QThread, Signal


class LlamaReadyProbe(QThread):
    """Polls the local tunneled port for an OpenAI-compatible /v1/models endpoint
    until llama-server reports a model loaded, fails, or we time out.

    Signals:
      - progress(elapsed_seconds, hint): every ~2s while waiting
      - ready(model_id):                  llama-server is up and serving a model
      - failed(reason):                   timed out or unrecoverable error
    """
    progress = Signal(int, str)
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, local_port: int, timeout_s: int = 240, parent=None):
        super().__init__(parent)
        self.local_port = local_port
        self.timeout_s = timeout_s
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        url = f"http://127.0.0.1:{self.local_port}/v1/models"
        start = time.time()
        deadline = start + self.timeout_s
        last_emit = -1
        last_hint = "Waiting for port to open..."

        while time.time() < deadline and not self._stop:
            elapsed = int(time.time() - start)
            if elapsed != last_emit:
                self.progress.emit(elapsed, last_hint)
                last_emit = elapsed
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=2) as r:
                    if r.status == 200:
                        body = r.read().decode("utf-8", errors="replace")
                        model_id = self._extract_model(body)
                        self.ready.emit(model_id or "(no id)")
                        return
                    last_hint = f"HTTP {r.status} - waiting..."
            except urllib.error.HTTPError as e:
                # Server is up but endpoint not ready yet (e.g. 404/503 during warmup)
                last_hint = f"Server returned HTTP {e.code} - warming up..."
            except (urllib.error.URLError, ConnectionError, OSError):
                last_hint = "Port is still closed - model is loading..."
            except Exception as e:
                last_hint = f"Probe: {e}"
            time.sleep(2)

        if self._stop:
            return
        self.failed.emit(
            f"Timed out after {self.timeout_s}s with no response. "
            "Check /tmp/llama-server.log on the remote machine."
        )

    @staticmethod
    def _extract_model(body: str) -> str:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return ""
        if isinstance(data, dict):
            arr = data.get("data") or []
            if arr and isinstance(arr[0], dict):
                return str(arr[0].get("id") or "")
        return ""
