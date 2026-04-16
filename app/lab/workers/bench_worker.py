from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.benchmark import run_benchmark
from app.lab.state.models import RuntimeStatus


class BenchmarkWorker(QThread):
    done = Signal(object)   # BenchmarkResult
    failed = Signal(str)

    def __init__(self, runtime: RuntimeStatus, model_path: str, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.model_path = model_path

    def run(self):
        try:
            r = run_benchmark(self.runtime, self.model_path)
            self.done.emit(r)
        except Exception as e:
            self.failed.emit(str(e))
