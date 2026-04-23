from datetime import datetime, timedelta

from app.analytics_store import AnalyticsStore


def test_import_history_rebuilds_balance_and_summary(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")

    summary = store.import_history(
        invoices=[
            {
                "start": 1000,
                "end": 1001,
                "type": "credit",
                "source": "stripe",
                "amount": -20,
            }
        ],
        charges=[
            {
                "start": 1200,
                "end": 4800,
                "type": "instance",
                "source": "instance-123",
                "amount": 4.0,
                "items": [
                    {"type": "gpu", "description": "GPU usage", "amount": 3.0},
                    {"type": "storage", "description": "Disk storage", "amount": 0.5},
                    {"type": "bandwidth", "description": "Upload/download", "amount": 0.5},
                ],
            }
        ],
        current_balance=16.0,
        sync_meta={"days": 30},
    )

    assert store.entry_count == 4
    assert store.latest_balance == 16.0
    assert summary["charges"] == 4.0
    assert summary["credits"] == 20.0
    assert summary["categories"]["gpu"] == 3.0
    assert summary["categories"]["storage"] == 0.5
    assert summary["categories"]["network"] == 0.5
    assert summary["top_sources"][0]["source"] == "instance-123"


def test_import_history_accepts_iso_timestamps(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    summary = store.import_history(
        invoices=[
            {
                "when": "2026-04-17T12:00:00",
                "type": "payment",
                "amount": "10.00",
            }
        ],
        charges=[],
        current_balance=10.0,
    )

    assert store.entry_count == 2
    assert summary["invoice_count"] == 1
    assert summary["credits"] == 10.0


def test_import_history_keeps_simultaneous_multi_instance_batches(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    now = datetime.now()
    ts = (now - timedelta(hours=1)).timestamp()

    summary = store.import_history(
        invoices=[],
        charges=[
            {
                "start": ts - 3600,
                "end": ts,
                "type": "instance",
                "source": "instance-1",
                "amount": 1.0,
            },
            {
                "start": ts - 7200,
                "end": ts,
                "type": "instance",
                "source": "instance-2",
                "amount": 2.0,
            },
        ],
        current_balance=5.0,
    )

    assert store.entry_count == 2
    assert store._entries[0]["balance"] == 8.0
    assert store._entries[-1]["balance"] == 5.0
    assert summary["charges"] == 3.0
    assert [item["source"] for item in summary["top_sources"][:2]] == ["instance-2", "instance-1"]


def test_bind_owner_resets_legacy_unowned_history(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    store._entries = [{"ts": datetime.now().isoformat(), "balance": 9.0}]
    store._billing_events = [{"kind": "charge", "ts": datetime.now().isoformat(), "amount": 1.0}]

    changed = store.bind_owner("email:test@example.com", reset_unowned=True)

    assert changed is True
    assert store.owner_key == "email:test@example.com"
    assert store.entry_count == 0
    assert store.has_billing_events is False


def test_period_spend_uses_anchor_before_cutoff(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    now = datetime.now()
    store._entries = [
        {"ts": (now - timedelta(hours=25)).isoformat(), "balance": 20.0},
        {"ts": (now - timedelta(hours=23)).isoformat(), "balance": 18.0},
        {"ts": (now - timedelta(hours=1)).isoformat(), "balance": 17.5},
    ]

    assert store.period_spend(1) == 2.5


def test_daily_spend_history_returns_fixed_days_with_zeroes(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    store._entries = [
        {"ts": (yesterday - timedelta(minutes=1)).isoformat(), "balance": 10.0},
        {"ts": yesterday.isoformat(), "balance": 8.5},
        {"ts": now.isoformat(), "balance": 8.5},
    ]

    out = store.daily_spend_history(3)

    assert len(out) == 3
    assert out[-2][1] == 1.5
    assert out[-1][1] == 0.0


def test_spend_buckets_splits_last_24h(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    now = datetime.now()
    store._entries = [
        {"ts": (now - timedelta(hours=25)).isoformat(), "balance": 10.0},
        {"ts": (now - timedelta(hours=20)).isoformat(), "balance": 9.0},
        {"ts": (now - timedelta(hours=2)).isoformat(), "balance": 8.25},
    ]

    buckets = store.spend_buckets(24, bucket_count=4)

    assert len(buckets) == 4
    assert sum(value for _, value in buckets) == 1.75


def test_calendar_tiles_use_billing_charges_not_balance_drops(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    now = datetime.now()
    store.import_history(
        invoices=[],
        charges=[
            {
                "start": (now - timedelta(hours=2)).timestamp(),
                "end": (now - timedelta(hours=1)).timestamp(),
                "type": "instance",
                "source": "instance-today",
                "amount": 1.25,
            },
            {
                "start": (now - timedelta(hours=5)).timestamp(),
                "end": (now - timedelta(hours=4)).timestamp(),
                "type": "instance",
                "source": "instance-week",
                "amount": 2.50,
            },
        ],
        current_balance=5.0,
    )

    assert store.today_spend() == 3.75
    assert store.week_spend() == 3.75
    assert store.month_spend() == 3.75
    assert store.has_billing_events is True


def test_daily_and_bucket_charts_use_billing_charges_when_available(tmp_path):
    store = AnalyticsStore(path=tmp_path / "analytics.json")
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    store.import_history(
        invoices=[],
        charges=[
            {
                "start": (now - timedelta(hours=3)).timestamp(),
                "end": (now - timedelta(hours=2)).timestamp(),
                "type": "instance",
                "amount": 1.0,
            },
            {
                "start": (yesterday - timedelta(hours=1)).timestamp(),
                "end": yesterday.timestamp(),
                "type": "instance",
                "amount": 2.0,
            },
        ],
        current_balance=5.0,
    )

    daily = store.daily_spend_history(2)
    buckets = store.spend_buckets(24, bucket_count=4)

    assert daily[-1][1] == 1.0
    assert daily[-2][1] == 2.0
    assert round(sum(value for _, value in buckets), 3) == 1.0
