from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.models_rental import OfferQuery, Offer
from app.services.rental_service import RentalService
from app.services.vast_service import VastAuthError, VastNetworkError


class OfferSearchWorker(QObject):
    results = Signal(list, object)     # list[Offer], OfferQuery (echo)
    failed  = Signal(str, str)         # kind, message

    def __init__(self, service: RentalService):
        super().__init__()
        self.service = service

    @Slot(object)
    def search(self, query: OfferQuery):
        try:
            offers: list[Offer] = self.service.search_offers(query)
        except VastAuthError as e:
            self.failed.emit("auth", str(e)); return
        except VastNetworkError as e:
            self.failed.emit("network", str(e)); return
        except Exception as e:
            self.failed.emit("unknown", str(e)); return
        self.results.emit(offers, query)
