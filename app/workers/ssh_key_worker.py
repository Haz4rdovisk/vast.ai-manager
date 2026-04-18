from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.services.rental_service import RentalService
from app.services.vast_service import VastAuthError, VastNetworkError


class SshKeyWorker(QObject):
    listed  = Signal(list)     # list[SshKey]
    created = Signal(object)   # SshKey
    failed  = Signal(str, str)

    def __init__(self, service: RentalService):
        super().__init__()
        self.service = service

    @Slot()
    def refresh(self):
        try:
            keys = self.service.list_ssh_keys()
        except VastAuthError as e:
            self.failed.emit("auth", str(e)); return
        except VastNetworkError as e:
            self.failed.emit("network", str(e)); return
        except Exception as e:
            self.failed.emit("unknown", str(e)); return
        self.listed.emit(keys)

    @Slot(str)
    def create(self, public_key: str):
        try:
            k = self.service.create_ssh_key(public_key)
        except VastAuthError as e:
            self.failed.emit("auth", str(e)); return
        except VastNetworkError as e:
            self.failed.emit("network", str(e)); return
        except Exception as e:
            self.failed.emit("unknown", str(e)); return
        self.created.emit(k)
