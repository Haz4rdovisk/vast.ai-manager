from PySide6.QtWidgets import QApplication

from app.lab.state.store import LabStore


def _app():
    return QApplication.instance() or QApplication([])


def test_hardware_view_column_breakpoints_and_placeholder_count(qt_app):
    from app.lab.views.hardware_view import HardwareView

    _app()
    store = LabStore()
    store.get_state(34860213)
    store.get_state(35170813)
    view = HardwareView(store)

    assert view._columns_for_width(740) == 1
    assert view._columns_for_width(900) == 2
    assert view._columns_for_width(1200) == 2
    assert view._columns_for_width(1400) == 3

    view._available_grid_width = lambda: 1200
    view._arrange_cards()

    assert len(view.cards) == 2
    assert len(view.placeholders) >= 2


def test_hardware_view_reuses_layout_during_resize(qt_app):
    from app.lab.views.hardware_view import HardwareView

    _app()
    store = LabStore()
    store.get_state(1)
    store.get_state(2)
    view = HardwareView(store)
    view._available_grid_width = lambda: 900
    view._arrange_cards()
    first_placeholders = list(view.placeholders)
    first_signature = view._layout_signature

    view._arrange_cards()

    assert view._layout_signature == first_signature
    assert view.placeholders == first_placeholders


def test_hardware_card_reflows_internal_metrics(qt_app):
    from app.lab.views.hardware_card import HardwareCard

    _app()
    card = HardwareCard(123)

    card.resize(760, 420)
    card._arrange_metrics()
    assert card._metric_cols == 3

    card.resize(620, 520)
    card._arrange_metrics()
    assert card._metric_cols == 2

    card.resize(440, 520)
    card._arrange_metrics()
    assert card._metric_cols == 2

    card.resize(300, 720)
    card._arrange_metrics()
    assert card._metric_cols == 1


def test_hardware_card_updates_thermometer(qt_app):
    from app.lab.state.models import LabInstanceState, RemoteSystem
    from app.lab.views.hardware_card import HardwareCard

    _app()
    card = HardwareCard(123)
    state = LabInstanceState(
        iid=123,
        system=RemoteSystem(gpu_temp=63, gpu_name="RTX 4090", gpu_count=1),
    )

    card.update_state(state)

    assert card.thermo._temperature == 63
    assert card.status_lbl.text() == "GPU thermal nominal"
