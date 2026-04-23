"""Top-level Store page: filters, offer results, and rent flow."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app import theme as t
from app.controller import AppController
from app.models_rental import Offer, OfferQuery, RentResult, SshKey, Template
from app.ui.toast import Toast
from app.ui.components.page_header import PageHeader
from app.ui.views.store.filter_sidebar import FilterSidebar
from app.ui.views.store.offer_details_dialog import OfferDetailsDialog
from app.ui.views.store.offer_list import OfferList
from app.ui.views.store.rent_dialog import RentDialog


class StoreView(QWidget):
    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._templates: list[Template] = []
        self._ssh_keys: list[SshKey] = []
        self._pending_dialog: RentDialog | None = None
        self._auto_search_enabled = False
        self._search_in_flight = False
        self._initial_search_done = False
        self._last_query: OfferQuery | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        root.addWidget(PageHeader(
            "Store",
            "Search Vast.ai GPU offers, compare hosts, and rent into your account.",
        ))

        body = QHBoxLayout()
        body.setSpacing(t.SPACE_5)
        self.filters = FilterSidebar()
        self.offers = OfferList()
        self.offers.set_market_filters(
            self.filters.type_cb,
            self.filters.gpu_cb,
            self.filters.region_cb,
            self.filters.sort_cb,
        )
        self.offers.gpu_count_selected.connect(self.filters.set_gpu_count_filter)
        self.filters.gpu_count_changed.connect(self.offers.set_gpu_count_choice)
        body.addWidget(self.filters)
        body.addWidget(self.offers, 1)
        root.addLayout(body, 1)

        self.filters.search_clicked.connect(self.search)
        self.filters.query_changed.connect(self._on_query_changed)
        self.offers.market_filters_reset_requested.connect(self.filters.reset)
        self.offers.rent_clicked.connect(self._open_rent_dialog)
        self.offers.details_clicked.connect(self._open_details_dialog)

        controller.offers_refreshed.connect(self._on_offers)
        controller.offers_failed.connect(self._on_store_error)
        controller.templates_refreshed.connect(self._on_templates)
        controller.ssh_keys_refreshed.connect(self._on_ssh_keys)
        controller.rent_done.connect(self._on_rent_done)
        controller.rent_failed.connect(self._on_rent_failed)

        controller.refresh_templates("")
        controller.refresh_ssh_keys()

    def enter_view(self) -> None:
        if self._initial_search_done:
            return
        self._initial_search_done = True
        self.search()

    def search(self) -> None:
        query = self.filters.build_query()
        self._last_query = query
        self._auto_search_enabled = True
        self._search_in_flight = True
        self.offers.set_loading()
        self.controller.search_offers(query)

    def _on_query_changed(self, query: OfferQuery) -> None:
        if not self._auto_search_enabled:
            return
        self._last_query = query
        self._search_in_flight = True
        self.offers.set_loading()
        self.controller.search_offers(query)

    def _on_offers(self, offers: list[Offer], _query: object) -> None:
        self._search_in_flight = False
        self.offers.set_results(offers)

    def _on_store_error(self, kind: str, message: str) -> None:
        text = f"[{kind}] {message}"
        if self._search_in_flight:
            self._search_in_flight = False
            self.offers.set_error(text)
        else:
            Toast(self, text[:220], "error", 4500)

    def _on_templates(self, templates: list[Template]) -> None:
        self._templates = templates
        if self._pending_dialog is not None:
            self._pending_dialog.set_templates(templates)

    def _on_ssh_keys(self, keys: list[SshKey]) -> None:
        self._ssh_keys = keys
        if self._pending_dialog is not None:
            pub = self.controller.ssh.get_public_key()
            self._pending_dialog.set_ssh_keys(keys, local_pub_key=pub)

    def _open_rent_dialog(self, offer: Offer) -> None:
        dialog = RentDialog(offer, self)
        self._pending_dialog = dialog
        dialog.set_templates(self._templates)
        pub = self.controller.ssh.get_public_key()
        dialog.set_ssh_keys(self._ssh_keys, local_pub_key=pub)
        dialog.confirmed.connect(self.controller.rent)
        dialog.finished.connect(lambda *_: setattr(self, "_pending_dialog", None))
        self.controller.refresh_templates("")
        self.controller.refresh_ssh_keys()
        dialog.exec()

    def _open_details_dialog(self, offer: Offer) -> None:
        OfferDetailsDialog(offer, self).exec()

    def _on_rent_done(self, result: RentResult) -> None:
        if result.ok:
            contract = result.new_contract_id or "pending"
            Toast(self, f"Rental created: contract #{contract}", "success", 4500)
            self.controller.request_refresh()
        else:
            Toast(self, f"Rent failed: {result.message[:220]}", "error", 5500)

    def _on_rent_failed(self, kind: str, message: str) -> None:
        Toast(self, f"Rent error [{kind}]: {message[:220]}", "error", 5500)
