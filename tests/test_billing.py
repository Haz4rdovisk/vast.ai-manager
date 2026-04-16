from datetime import date
from app.billing import (
    AutonomyLevel,
    BurnRateTracker,
    BurnRateTrend,
    DailySpendTracker,
    autonomy_hours,
    burn_rate,
    format_autonomy,
    project_balance,
    total_burn_rate,
)
from app.models import Instance, InstanceState


def _inst(id_, state, dph, duration=None, storage_total_cost=None, disk_space_gb=None):
    return Instance(
        id=id_, state=state, gpu_name="x", num_gpus=1, gpu_ram_gb=24.0,
        gpu_util=None, gpu_temp=None, vram_usage_gb=None,
        cpu_name=None, cpu_cores=None, cpu_util=None,
        ram_total_gb=None, ram_used_gb=None,
        disk_usage_gb=None, disk_space_gb=disk_space_gb,
        inet_down_mbps=None, inet_up_mbps=None, image=None, dph=dph,
        duration_seconds=duration, ssh_host=None, ssh_port=None, raw={},
        storage_total_cost=storage_total_cost,
    )


def test_burn_rate_sums_running():
    insts = [
        _inst(1, InstanceState.RUNNING, 0.42),
        _inst(2, InstanceState.STOPPED, 0.28),
        _inst(3, InstanceState.RUNNING, 0.30),
    ]
    assert burn_rate(insts) == 0.72


def test_burn_rate_includes_starting():
    insts = [
        _inst(1, InstanceState.RUNNING, 0.42),
        _inst(2, InstanceState.STARTING, 0.28),
        _inst(3, InstanceState.STOPPED, 0.30),
    ]
    assert burn_rate(insts) == 0.70


def test_format_autonomy_minutes():
    assert format_autonomy(0.5) == "~30min"
    assert format_autonomy(0.25) == "~15min"
    assert format_autonomy(0.98) == "~59min"


def test_format_autonomy_hours():
    assert format_autonomy(1.0) == "~1h"
    assert format_autonomy(5.5) == "~6h"
    assert format_autonomy(23.9) == "~24h"


def test_format_autonomy_days():
    # Exact days < 7
    assert format_autonomy(24.0) == "~1d"
    assert format_autonomy(48.0) == "~2d"
    assert format_autonomy(72.0) == "~3d"  # 3 days exactly
    
    # Days with hours remainder
    assert format_autonomy(30.0) == "~1d 6h"   # 1 day + 6 hours
    assert format_autonomy(47.0) == "~1d 23h"  # 1 day + 23 hours (47/24 = 1.958...)
    assert format_autonomy(50.0) == "~2d 2h"   # 2 days + 2 hours
    
    # Weeks >= 7 days
    assert format_autonomy(168.0) == "~1w"     # exactly 1 week (7 days)
    assert format_autonomy(192.0) == "~1w 1d"  # 1 week + 1 day (8 days total = 192h)
    assert format_autonomy(336.0) == "~2w"     # exactly 2 weeks (14 days)
    assert format_autonomy(360.0) == "~2w 1d"  # 2 weeks + 1 day (360/24 = 15 days)


def test_format_autonomy_none():
    assert format_autonomy(None) == "∞"
    assert format_autonomy(float('inf')) == "∞"


def test_autonomy_level_critical():
    assert AutonomyLevel.from_hours(0.5) == AutonomyLevel.CRITICAL
    assert AutonomyLevel.from_hours(0.99) == AutonomyLevel.CRITICAL
    assert AutonomyLevel.from_hours(None) == AutonomyLevel.CRITICAL


def test_autonomy_level_low():
    assert AutonomyLevel.from_hours(1.0) == AutonomyLevel.LOW
    assert AutonomyLevel.from_hours(3.5) == AutonomyLevel.LOW
    assert AutonomyLevel.from_hours(5.99) == AutonomyLevel.LOW


def test_autonomy_level_medium():
    assert AutonomyLevel.from_hours(6.0) == AutonomyLevel.MEDIUM
    assert AutonomyLevel.from_hours(12.0) == AutonomyLevel.MEDIUM
    assert AutonomyLevel.from_hours(23.99) == AutonomyLevel.MEDIUM


def test_autonomy_level_good():
    assert AutonomyLevel.from_hours(24.0) == AutonomyLevel.GOOD
    assert AutonomyLevel.from_hours(100.0) == AutonomyLevel.GOOD


def test_autonomy_hours_zero_burn():
    assert autonomy_hours(10.0, 0.0) is None


def test_autonomy_hours_normal():
    assert autonomy_hours(10.0, 2.0) == 5.0


def test_daily_tracker_accumulates_delta():
    tracker = DailySpendTracker(today_fn=lambda: date(2026, 4, 14))
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=3600))
    assert tracker.today_spend() == 0.0  # first sample sets baseline
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=7200))
    assert abs(tracker.today_spend() - 1.0) < 1e-6  # +1h × $1


def test_daily_tracker_resets_on_new_day():
    current = [date(2026, 4, 14)]
    tracker = DailySpendTracker(today_fn=lambda: current[0])
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=3600))
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=7200))
    assert tracker.today_spend() > 0
    current[0] = date(2026, 4, 15)
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=10800))
    assert tracker.today_spend() == 0.0


# ---------------------------------------------------------------- #
# Phase 2: total_burn_rate
# ---------------------------------------------------------------- #

def test_total_burn_rate_matches_gpu_when_no_storage():
    insts = [
        _inst(1, InstanceState.RUNNING, 0.42),
        _inst(2, InstanceState.STOPPED, 0.28),
    ]
    assert total_burn_rate(insts) == 0.42


def test_total_burn_rate_includes_storage_prorated_monthly():
    # $7.20/month storage → $0.01/h (720h/month).
    insts = [
        _inst(1, InstanceState.RUNNING, 0.50,
              storage_total_cost=7.20, disk_space_gb=200.0),
    ]
    total = total_burn_rate(insts, include_storage=True)
    # 0.50 GPU + 0.01 storage
    assert abs(total - 0.51) < 1e-6


def test_total_burn_rate_skips_storage_under_free_quota():
    insts = [
        _inst(1, InstanceState.RUNNING, 0.50,
              storage_total_cost=7.20, disk_space_gb=40.0),  # below 50GB free
    ]
    assert total_burn_rate(insts, include_storage=True) == 0.50


def test_total_burn_rate_storage_for_stopped_instance():
    # Stopped instances still pay for storage on Vast.
    insts = [
        _inst(1, InstanceState.STOPPED, 0.50,
              storage_total_cost=14.40, disk_space_gb=500.0),
    ]
    # $14.40/month ≈ $0.02/h, GPU contributes 0 (stopped).
    assert abs(total_burn_rate(insts) - 0.02) < 1e-6


def test_total_burn_rate_include_storage_flag_off():
    insts = [
        _inst(1, InstanceState.RUNNING, 0.50,
              storage_total_cost=7.20, disk_space_gb=200.0),
    ]
    assert total_burn_rate(insts, include_storage=False) == 0.50


def test_total_burn_rate_network_cost():
    insts = [_inst(1, InstanceState.RUNNING, 0.30)]
    assert abs(total_burn_rate(insts,
                               estimated_network_cost_per_hour=0.05) - 0.35) < 1e-6


# ---------------------------------------------------------------- #
# Phase 2: BurnRateTracker
# ---------------------------------------------------------------- #

def test_burn_tracker_average_simple():
    t = BurnRateTracker(window_size=5)
    assert t.update(1.0) == 1.0
    assert t.update(3.0) == 2.0
    assert t.update(5.0) == 3.0


def test_burn_tracker_window_limits_history():
    t = BurnRateTracker(window_size=3)
    for v in [1.0, 2.0, 3.0, 10.0]:
        t.update(v)
    # Only last 3 are kept: (2+3+10)/3 = 5.0
    assert t.average() == 5.0


def test_burn_tracker_trend_stable_under_threshold():
    t = BurnRateTracker(window_size=10, trend_threshold=0.05)
    for v in [1.00, 1.00, 1.01, 1.01, 1.00, 1.01, 1.00, 1.00]:
        t.update(v)
    assert t.get_trend() is BurnRateTrend.STABLE


def test_burn_tracker_trend_increasing():
    t = BurnRateTracker(window_size=10, trend_threshold=0.05)
    for v in [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0]:
        t.update(v)
    assert t.get_trend() is BurnRateTrend.INCREASING


def test_burn_tracker_trend_decreasing():
    t = BurnRateTracker(window_size=10, trend_threshold=0.05)
    for v in [2.0, 2.0, 2.0, 2.0, 1.0, 1.0, 1.0, 1.0]:
        t.update(v)
    assert t.get_trend() is BurnRateTrend.DECREASING


def test_burn_tracker_trend_needs_min_samples():
    t = BurnRateTracker(window_size=10)
    t.update(1.0)
    t.update(5.0)
    assert t.get_trend() is BurnRateTrend.STABLE  # only 2 samples


def test_burn_tracker_reset():
    t = BurnRateTracker(window_size=5)
    t.update(1.0)
    t.update(2.0)
    t.reset()
    assert t.average() == 0.0


def test_burn_tracker_arrow_symbols():
    assert BurnRateTrend.INCREASING.arrow == "↑"
    assert BurnRateTrend.DECREASING.arrow == "↓"
    assert BurnRateTrend.STABLE.arrow == "→"


# ---------------------------------------------------------------- #
# Phase 2: project_balance
# ---------------------------------------------------------------- #

def test_project_balance_linear():
    out = project_balance(balance=10.0, burn=1.0, hours_ahead=5)
    assert out["balance"] == 5.0
    assert out["autonomy_hours"] == 5.0
    assert out["burn_used"] == 1.0


def test_project_balance_goes_negative():
    out = project_balance(balance=2.0, burn=1.0, hours_ahead=5)
    assert out["balance"] == -3.0
    # Balance was clamped to 0 before dividing, so no hours remain.
    assert out["autonomy_hours"] == 0.0


def test_project_balance_zero_burn():
    out = project_balance(balance=10.0, burn=0.0, hours_ahead=24)
    assert out["balance"] == 10.0
    assert out["autonomy_hours"] is None


def test_project_balance_increasing_trend_shrinks_runway():
    plain = project_balance(100.0, 1.0, 24)
    boosted = project_balance(100.0, 1.0, 24,
                              include_trend_factor=True,
                              trend=BurnRateTrend.INCREASING,
                              trend_multiplier=0.10)
    # With +10% burn, 24h consumes more → balance strictly lower.
    assert boosted["balance"] < plain["balance"]
    assert abs(boosted["burn_used"] - 1.10) < 1e-6


def test_project_balance_decreasing_trend_extends_runway():
    plain = project_balance(100.0, 1.0, 24)
    eased = project_balance(100.0, 1.0, 24,
                            include_trend_factor=True,
                            trend=BurnRateTrend.DECREASING,
                            trend_multiplier=0.10)
    assert eased["balance"] > plain["balance"]
    assert abs(eased["burn_used"] - 0.90) < 1e-6
