from app.ui.views.analytics_view import _chart_axis_bounds


def test_money_axis_uses_zero_floor_for_positive_values():
    ymin, ymax = _chart_axis_bounds([5.16, 5.12, 5.08], ymin_limit=0.0)

    assert ymin == 0.0
    assert ymax > 5.16


def test_money_axis_applies_to_all_line_ranges():
    sample_values_by_range = {
        "1H": [5.16, 5.14],
        "3H": [0.50, 5.16, 5.16],
        "6H": [5.25, 5.16],
        "12H": [5.80, 5.16],
        "24H": [6.20, 5.16],
        "SINCE RECHARGE": [0.20, 5.16],
    }

    for values in sample_values_by_range.values():
        ymin, _ = _chart_axis_bounds(values, ymin_limit=0.0)
        assert ymin == 0.0


def test_cycle_axis_keeps_recharge_as_top_limit():
    ymin, ymax = _chart_axis_bounds([0.20, 5.16], ymin_limit=0.0, ymax_limit=10.0)

    assert ymin == 0.0
    assert ymax == 10.0


def test_money_axis_clamps_reconstructed_negative_balances():
    ymin, ymax = _chart_axis_bounds([-4.70, 0.20, 5.16], ymin_limit=0.0)

    assert ymin == 0.0
    assert ymax > 5.16
