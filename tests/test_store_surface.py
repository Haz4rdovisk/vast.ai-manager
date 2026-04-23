from unittest.mock import MagicMock

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QComboBox

from app.models_rental import Offer, OfferSort, RentResult


def _app():
    return QApplication.instance() or QApplication([])


def _offer(**overrides):
    data = dict(
        id=1,
        ask_contract_id=1,
        machine_id=2,
        host_id=3,
        gpu_name="RTX 4090",
        num_gpus=1,
        gpu_ram_gb=24.0,
        gpu_total_ram_gb=24.0,
        cpu_name="AMD EPYC",
        cpu_cores=16,
        cpu_ram_gb=64.0,
        disk_space_gb=500.0,
        disk_bw_mbps=2000.0,
        inet_down_mbps=1000.0,
        inet_up_mbps=800.0,
        dph_total=0.35,
        min_bid=None,
        storage_cost=0.1,
        reliability=0.99,
        dlperf=22.0,
        dlperf_per_dphtotal=62.0,
        flops_per_dphtotal=110.0,
        cuda_max_good=12.4,
        compute_cap=890,
        verified=True,
        rentable=True,
        rented=False,
        external=False,
        geolocation="US-California, US",
        country="US",
        datacenter="DC-X",
        static_ip=True,
        direct_port_count=20,
        gpu_arch="ada",
        duration_days=14.5,
        hosting_type="datacenter",
        raw={},
    )
    data.update(overrides)
    return Offer(**data)


class FakeStoreController(QObject):
    offers_refreshed = Signal(list, object)
    offers_failed = Signal(str, str)
    templates_refreshed = Signal(list)
    ssh_keys_refreshed = Signal(list)
    rent_done = Signal(object)
    rent_failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.search_offers = MagicMock()
        self.refresh_templates = MagicMock()
        self.refresh_ssh_keys = MagicMock()
        self.rent = MagicMock()
        self.request_refresh = MagicMock()


def test_store_surface_imports():
    import app.ui.views.store_view
    import app.ui.views.store.offer_card
    import app.ui.views.store.offer_details_dialog
    import app.ui.views.store.offer_list
    from app.ui.app_shell import _VIEW_LABELS

    assert app.ui.views.store_view.StoreView
    assert app.ui.views.store.offer_card.OfferCard
    assert app.ui.views.store.offer_details_dialog.OfferDetailsDialog
    assert app.ui.views.store.offer_list.OfferList
    assert _VIEW_LABELS["store"] == "Store"


def test_offer_list_renders_and_relays_rent(qt_app):
    from app.ui.views.store.offer_list import OfferList

    _app()
    offer = _offer()
    view = OfferList()
    captured = []
    view.rent_clicked.connect(captured.append)
    view.set_results([offer])

    assert view.count_lbl.text() == "1 offers"
    assert len(view.cards) == 1
    view.cards[0].rent_clicked.emit(offer)
    assert captured == [offer]


def test_offer_list_renders_large_results_in_batches(qt_app):
    from app.ui.views.store.offer_list import OfferList, _CARD_RENDER_BATCH_SIZE

    _app()
    view = OfferList()
    offers = [_offer(id=i, ask_contract_id=i) for i in range(_CARD_RENDER_BATCH_SIZE + 3)]

    view.set_results(offers)

    assert len(view.cards) == _CARD_RENDER_BATCH_SIZE
    assert view.count_lbl.text() == f"{len(offers)} offers"
    assert view.col.count() == _CARD_RENDER_BATCH_SIZE + 1

    view._render_next_batch()

    assert len(view.cards) == len(offers)
    assert view.count_lbl.text() == f"{len(offers)} offers"


def test_offer_list_handles_numeric_text_fields(qt_app):
    from app.ui.views.store.offer_list import OfferList

    _app()
    view = OfferList()
    view.set_results([_offer(hosting_type=1, gpu_arch=8, country=55)])

    assert view.count_lbl.text() == "1 offers"
    assert len(view.cards) == 1


def test_offer_card_shows_rich_marketplace_fields_and_price_breakdown(qt_app):
    from app.ui.views.store.offer_list import OfferList

    _app()
    view = OfferList()
    offer = _offer(
        gpu_name="RTX 3090",
        num_gpus=1,
        dph_total=0.085,
        storage_cost=0.2,
        disk_space_gb=32.0,
        dlperf=44.2,
        dlperf_per_dphtotal=520.2,
        reliability=0.989,
        raw={
            "total_flops": 35.5,
            "gpu_mem_bw": 804.8,
            "pcie_bw": 6.1,
            "pci_gen": 3.0,
            "allocated_storage": 32.0,
            "inet_up_cost": 0.002667,
            "inet_down_cost": 0.002667,
        },
    )

    view.set_results([offer])

    card = view.cards[0]
    assert card.title_lbl.text() == "1x RTX 3090"
    assert card.price_lbl.text() == "$0.085/hr"
    tooltip = card.price_lbl.toolTip()
    assert "Price Breakdown" in tooltip
    assert "GPU Compute" in tooltip
    assert "Storage (32 GiB)" in tooltip
    assert "$2.667/TB" in tooltip


def test_offer_price_breakdown_uses_requested_storage_not_host_disk(qt_app):
    from app.services.offer_pricing import offer_price_breakdown

    offer = _offer(
        dph_total=0.20,
        storage_cost=0.20,
        disk_space_gb=1000.0,
        raw={"_requested_storage_gib": 20.0},
    )

    breakdown = offer_price_breakdown(offer)

    assert abs(breakdown.storage_hour - (0.20 * 20.0 / 720.0)) < 1e-9
    assert breakdown.total_hour == 0.20


def test_offer_details_dialog_is_read_only_and_shows_price_breakdown(qt_app):
    from app.ui.views.store.offer_details_dialog import OfferDetailsDialog

    _app()
    dialog = OfferDetailsDialog(
        _offer(
            raw={
                "total_flops": 35.5,
                "allocated_storage": 32.0,
                "inet_up_cost": 0.002667,
                "inet_down_cost": 0.002667,
            }
        )
    )

    assert "1x RTX 4090" in dialog.title_lbl.text()
    assert dialog.price_lbl.text() == "$0.350/hr"


def test_filter_sidebar_defaults_do_not_hide_gpu_count(qt_app):
    from app.ui.views.store.filter_sidebar import CollapsibleSection, FilterSidebar

    _app()
    sidebar = FilterSidebar()
    query = sidebar.build_query()

    assert sidebar.minimumWidth() >= 320
    assert query.min_num_gpus is None
    assert query.max_num_gpus is None
    assert query.min_reliability is None
    assert len(sidebar.findChildren(CollapsibleSection)) >= 7

    sidebar.verified.setChecked(False)
    assert sidebar.build_query().verified is None


def test_store_view_uses_marketplace_toolbar_order_and_gpu_count_buttons(qt_app):
    from app.ui.views.store_view import StoreView

    _app()
    controller = FakeStoreController()
    view = StoreView(controller)

    assert view.offers.isAncestorOf(view.filters.type_cb)
    assert view.offers.isAncestorOf(view.filters.gpu_cb)
    assert view.offers.isAncestorOf(view.filters.region_cb)
    assert view.offers.isAncestorOf(view.filters.sort_cb)
    assert view.filters.gpu_cb.currentText() == "GPUs"
    assert view.filters.region_cb.currentText() == "Location"
    assert view.filters.sort_cb.currentText() == "Price (inc.)"
    assert view.filters.build_query().sort == OfferSort.DPH_ASC

    view.offers.gpu_count_buttons["4X"].click()
    query = view.filters.build_query()
    assert query.min_num_gpus == 4
    assert query.max_num_gpus == 4

    view.offers.gpu_count_buttons["9+"].click()
    query = view.filters.build_query()
    assert query.min_num_gpus == 9
    assert query.max_num_gpus is None

    view.offers.gpu_count_buttons["ANY"].click()
    query = view.filters.build_query()
    assert query.min_num_gpus is None
    assert query.max_num_gpus is None


def test_store_view_first_entry_runs_default_search_once(qt_app):
    from app.ui.views.store_view import StoreView

    _app()
    controller = FakeStoreController()
    view = StoreView(controller)

    controller.refresh_templates.assert_called_once_with("")
    controller.refresh_ssh_keys.assert_called_once_with()

    view.enter_view()
    assert controller.search_offers.call_count == 1
    query = controller.search_offers.call_args.args[0]
    assert query.gpu_names == []
    assert query.min_num_gpus is None
    assert query.max_num_gpus is None
    assert query.min_reliability is None

    view.enter_view()
    assert controller.search_offers.call_count == 1

    controller.offers_refreshed.emit([_offer()], view.filters.build_query())
    assert view.offers.count_lbl.text() == "1 offers"


def test_store_view_rent_done_refreshes_instances(qt_app):
    from app.ui.views.store_view import StoreView

    _app()
    controller = FakeStoreController()
    view = StoreView(controller)

    controller.rent_done.emit(RentResult(ok=True, new_contract_id=42))
    controller.request_refresh.assert_called_once()


def test_store_view_details_does_not_start_rent_flow(qt_app, monkeypatch):
    import app.ui.views.store_view as store_view

    _app()
    controller = FakeStoreController()
    view = store_view.StoreView(controller)
    controller.refresh_templates.reset_mock()
    controller.refresh_ssh_keys.reset_mock()

    opened = []

    class FakeDetailsDialog:
        def __init__(self, offer, parent=None):
            opened.append((offer, parent))

        def exec(self):
            return 0

    monkeypatch.setattr(store_view, "OfferDetailsDialog", FakeDetailsDialog)
    view._open_details_dialog(_offer())

    assert opened
    controller.refresh_templates.assert_not_called()
    controller.refresh_ssh_keys.assert_not_called()
    controller.rent.assert_not_called()


def test_rent_dialog_uses_ask_contract_id_for_create_instance(qt_app):
    from app.ui.views.store.rent_dialog import RentDialog

    _app()
    dialog = RentDialog(_offer(id=101, ask_contract_id=202))
    dialog.findChildren(QComboBox)[0].setCurrentIndex(1)
    captured = []
    dialog.confirmed.connect(captured.append)

    dialog._confirm()

    assert captured
    assert captured[0].offer_id == 202
