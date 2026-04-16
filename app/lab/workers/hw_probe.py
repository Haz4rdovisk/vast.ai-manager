"""Hardware probe as a QThread — keeps the UI responsive during psutil/nvidia-smi."""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.hardware import detect_hardware


class HardwareProbeWorker(QThread):
    detected = Signal(object)   # HardwareSpec
    failed = Signal(str)

    def run(self):
        try:
            spec = detect_hardware()
            self.detected.emit(spec)
        except Exception as e:
            self.failed.emit(str(e))
