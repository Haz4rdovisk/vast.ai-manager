from datetime import datetime, timedelta

from PySide6.QtWidgets import QWidget

from app.models import AppConfig, Instance, InstanceState, UserInfo
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


def test_analytics_view_live_projection_uses_total_fleet_burn(qt_app):
    from app.ui.views.analytics_view import AnalyticsView

    class FakeStore:
        def __init__(self):
            self._last_recharge_val = 0.0
            self._last_recharge_ts = 0.0
            self.billing_summary = {}
            self.last_live_dph = None

        def last_charge_end(self):
            return datetime.now() - timedelta(hours=1)

        def smoothed_balance_timeline(self, hours, balance, live_dph=0.0, live_since=None):
            self.last_live_dph = live_dph
            now = datetime.now()
            return [
                ((now - timedelta(minutes=10)).isoformat(timespec="seconds"), balance + 0.5),
                (now.isoformat(timespec="seconds"), balance),
            ]

        def burn_rate_timeline(self, hours):
            now = datetime.now()
            return [
                ((now - timedelta(minutes=10)).isoformat(timespec="seconds"), 0.0),
                (now.isoformat(timespec="seconds"), 0.0),
            ]

        def spend_buckets(self, hours, bucket_count=8, live_dph=0.0, live_since=None):
            return [(f"{i:02d}:00", 0.0) for i in range(bucket_count)]

        def daily_spend_history(self, days):
            return [(f"Day {i+1}", 0.0) for i in range(days)]

        def week_spend(self):
            return 0.0

        def month_spend(self):
            return 0.0

    store = FakeStore()
    cfg = AppConfig(
        include_storage_in_burn_rate=True,
        estimated_network_cost_per_hour=0.05,
    )
    parent = QWidget()
    view = AnalyticsView(cfg, analytics_store=store, parent=parent)
    view._mode = "FINANCE"
    view.sync(
        [
            Instance(
                id=1,
                state=InstanceState.RUNNING,
                gpu_name="RTX 3090",
                dph=0.50,
                disk_space_gb=200.0,
                storage_total_cost=7.20,
            ),
            Instance(
                id=2,
                state=InstanceState.STOPPED,
                gpu_name="RTX 3090",
                dph=0.0,
                disk_space_gb=200.0,
                storage_total_cost=14.40,
            ),
        ],
        UserInfo(balance=10.0),
        today_spend=0.0,
        week_spend=0.0,
        month_spend=0.0,
    )

    expected_hourly = 0.50 + (7.20 / 720.0) + (14.40 / 720.0) + 0.05
    assert abs(store.last_live_dph - expected_hourly) < 1e-6


def test_analytics_view_keeps_last_balance_when_user_is_temporarily_missing(qt_app):
    from app.ui.views.analytics_view import AnalyticsView

    class FakeStore:
        def __init__(self):
            self._last_recharge_val = 0.0
            self._last_recharge_ts = 0.0
            self.billing_summary = {}

        def last_charge_end(self):
            return datetime.now() - timedelta(hours=1)

        def smoothed_balance_timeline(self, hours, balance, live_dph=0.0, live_since=None):
            now = datetime.now()
            return [
                ((now - timedelta(minutes=10)).isoformat(timespec="seconds"), balance + 0.1),
                (now.isoformat(timespec="seconds"), balance),
            ]

        def burn_rate_timeline(self, hours):
            now = datetime.now()
            return [
                ((now - timedelta(minutes=10)).isoformat(timespec="seconds"), 0.0),
                (now.isoformat(timespec="seconds"), 0.0),
            ]

        def spend_buckets(self, hours, bucket_count=8, live_dph=0.0, live_since=None):
            return [(f"{i:02d}:00", 0.0) for i in range(bucket_count)]

        def daily_spend_history(self, days):
            return [(f"Day {i+1}", 0.0) for i in range(days)]

        def week_spend(self):
            return 0.0

        def month_spend(self):
            return 0.0

    parent = QWidget()
    view = AnalyticsView(AppConfig(), analytics_store=FakeStore(), parent=parent)
    instances = [Instance(id=1, state=InstanceState.RUNNING, gpu_name="RTX 3090", dph=0.5)]

    view.sync(instances, UserInfo(balance=3.25, email="user@example.com"), today_spend=0.0, week_spend=0.0, month_spend=0.0)
    view.sync(instances, None, today_spend=0.0, week_spend=0.0, month_spend=0.0)

    assert view._last_user is not None
    assert view._last_user.balance == 3.25
