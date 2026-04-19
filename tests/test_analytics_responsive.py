from PySide6.QtWidgets import QApplication

from app.models import AppConfig


def _app():
    return QApplication.instance() or QApplication([])


def test_analytics_summary_cards_use_single_row_when_wide(qt_app):
    from app.ui.views.analytics_view import AnalyticsView

    _app()
    view = AnalyticsView(AppConfig())
    view._summary_width = lambda: 1600
    view._summary_cols = None
    view._arrange_summary_cards()

    assert view._summary_column_count(1600) == 4
    for col, card in enumerate(view.summary_cards):
        assert view.summary_grid.itemAtPosition(0, col).widget() is card


def test_analytics_summary_cards_fall_back_to_two_by_two(qt_app):
    from app.ui.views.analytics_view import AnalyticsView

    _app()
    view = AnalyticsView(AppConfig())
    view._summary_width = lambda: 900
    view._summary_cols = None
    view._arrange_summary_cards()

    assert view._summary_column_count(900) == 2
    assert view.summary_grid.itemAtPosition(0, 0).widget() is view.summary_cards[0]
    assert view.summary_grid.itemAtPosition(0, 1).widget() is view.summary_cards[1]
    assert view.summary_grid.itemAtPosition(1, 0).widget() is view.summary_cards[2]
    assert view.summary_grid.itemAtPosition(1, 1).widget() is view.summary_cards[3]
