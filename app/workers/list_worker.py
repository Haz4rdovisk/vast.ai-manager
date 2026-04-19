from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.services.vast_service import VastService, VastAuthError, VastNetworkError


class ListWorker(QObject):
    refreshed = Signal(list, object)  # list[Instance], UserInfo | None
    failed = Signal(str, str)         # kind, message

    def __init__(self, service: VastService):
        super().__init__()
        self.service = service

    @Slot()
    def refresh(self):
        try:
            user = self.service.get_user_info()
        except VastAuthError as e:
            self.failed.emit("auth", str(e))
            return
        except VastNetworkError as e:
            self.failed.emit("network", str(e))
            return
        except Exception as e:
            self.failed.emit("unknown", str(e))
            return

        try:
            insts = self.service.list_instances()
        except VastAuthError as e:
            self.failed.emit("auth", str(e))
            return
        except VastNetworkError as e:
            self.failed.emit("network", str(e))
            return
        except Exception as e:
            self.failed.emit("unknown", str(e))
            return

        if not isinstance(insts, list):
            insts = []
        self.refreshed.emit(insts, user)
