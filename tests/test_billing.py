from datetime import date
from app.billing import burn_rate, autonomy_hours, DailySpendTracker
from app.models import Instance, InstanceState


def _inst(id_, state, dph, duration=None):
    return Instance(
        id=id_, state=state, gpu_name="x", num_gpus=1, gpu_ram_gb=24.0,
        gpu_util=None, gpu_temp=None, vram_usage_gb=None,
        cpu_name=None, cpu_cores=None, cpu_util=None,
        ram_total_gb=None, ram_used_gb=None,
        disk_usage_gb=None, disk_space_gb=None,
        inet_down_mbps=None, inet_up_mbps=None, image=None, dph=dph,
        duration_seconds=duration, ssh_host=None, ssh_port=None, raw={},
    )


def test_burn_rate_sums_running():
    insts = [
        _inst(1, InstanceState.RUNNING, 0.42),
        _inst(2, InstanceState.STOPPED, 0.28),
        _inst(3, InstanceState.RUNNING, 0.30),
    ]
    assert burn_rate(insts) == 0.72


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
