from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.services.rental_service import RentalService
from app.services.vast_service import VastAuthError, VastNetworkError


class TemplateListWorker(QObject):
    results = Signal(list)   # list[Template]
    failed  = Signal(str, str)

    def __init__(self, service: RentalService):
        super().__init__()
        self.service = service

    @Slot(str)
    def refresh(self, query: str = ""):
        try:
            tpls = self.service.search_templates(query or None)
        except VastAuthError as e:
            self.failed.emit("auth", str(e)); return
        except VastNetworkError as e:
            self.failed.emit("network", str(e)); return
        except Exception as e:
            self.failed.emit("unknown", str(e)); return
        self.results.emit(tpls)
