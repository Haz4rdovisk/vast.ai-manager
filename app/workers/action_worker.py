from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.services.vast_service import VastService


class ActionWorker(QObject):
    finished = Signal(int, str, bool, str)  # instance_id, action, ok, message

    def __init__(self, service: VastService):
        super().__init__()
        self.service = service

    @Slot(int)
    def start(self, instance_id: int):
        try:
            self.service.start_instance(instance_id)
            self.finished.emit(instance_id, "start", True, "Ativação solicitada")
        except Exception as e:
            self.finished.emit(instance_id, "start", False, str(e))

    @Slot(int)
    def stop(self, instance_id: int):
        try:
            self.service.stop_instance(instance_id)
            self.finished.emit(instance_id, "stop", True, "Desativação solicitada")
        except Exception as e:
            self.finished.emit(instance_id, "stop", False, str(e))
