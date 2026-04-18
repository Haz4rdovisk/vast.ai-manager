from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.models_rental import RentRequest, RentResult
from app.services.rental_service import RentalService
from app.services.vast_service import VastAuthError, VastNetworkError


class RentCreateWorker(QObject):
    done   = Signal(object)        # RentResult
    failed = Signal(str, str)

    def __init__(self, service: RentalService):
        super().__init__()
        self.service = service

    @Slot(object)
    def rent(self, req: RentRequest):
        try:
            res: RentResult = self.service.rent(req)
        except VastAuthError as e:
            self.failed.emit("auth", str(e)); return
        except VastNetworkError as e:
            self.failed.emit("network", str(e)); return
        except Exception as e:
            self.failed.emit("unknown", str(e)); return
        self.done.emit(res)
