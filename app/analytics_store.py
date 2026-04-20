"""Persistent analytics store — append-only JSON log of cost snapshots.
Provides real spending data computed from balance deltas over time.

Storage: ~/.vastai-app/analytics.json
Retention: 30 days, auto-pruned on load.
Sampling: 1 entry per 5 minutes max.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


_LOG_PATH = Path.home() / ".vastai-app" / "analytics.json"
_MIN_INTERVAL = timedelta(minutes=5)
_RETENTION_DAYS = 30


@dataclass
class CostSnapshot:
    ts: str                          # ISO 8601
    balance: float
    burn_total: float                # total $/h
    burn_gpu: float
    burn_storage: float
    burn_network: float
    instances: list[dict] = field(default_factory=list)
    # each: {"id": int, "gpu": str, "dph": float, "state": str, "storage_h": float}


class AnalyticsStore:
    """Append-only log with in-memory cache for fast queries."""

    def __init__(self, path: Path = _LOG_PATH):
        self._path = path
        self._entries: list[dict] = []
        self._last_recharge_val = 0.0
        self._last_recharge_ts: float = 0.0
        self._billing_summary: dict = {}
        self._billing_events: list[dict] = []
        self._last_write: datetime | None = None
        self._save_lock = threading.Lock()
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        if not self._path.exists():
            self._entries = []
            return
        
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            
            # Suporte para migração: se for o formato novo (dict)
            if isinstance(data, dict):
                self._entries = data.get("entries", [])
                self._last_recharge_val = data.get("last_recharge_val", 0.0)
                self._last_recharge_ts = data.get("last_recharge_ts", 0.0)
                self._billing_summary = data.get("billing_summary", {})
                self._billing_events = data.get("billing_events", [])
            # Se for o formato antigo (list)
            elif isinstance(data, list):
                self._entries = data
                self._last_recharge_val = 0.0
                self._last_recharge_ts = 0.0
                self._billing_summary = {}
                self._billing_events = []
            else:
                self._entries = []
                
        except (json.JSONDecodeError, OSError):
            self._entries = []

        # Prune old entries
        cutoff = (datetime.now() - timedelta(days=_RETENTION_DAYS)).isoformat()
        self._entries = [e for e in self._entries if e.get("ts", "") >= cutoff]
        self._save()

        # Set last write time
        if self._entries:
            try:
                self._last_write = datetime.fromisoformat(self._entries[-1]["ts"])
            except (ValueError, KeyError):
                self._last_write = None

    def _save(self):
        """Thread-safe background persistence."""
        # Deep copy data for safe serialization outside the lock
        with self._save_lock:
            payload = {
                "entries": list(self._entries),
                "last_recharge_val": self._last_recharge_val,
                "last_recharge_ts": self._last_recharge_ts,
                "billing_summary": dict(self._billing_summary),
                "billing_events": list(self._billing_events),
            }

        def worker():
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self._path.with_suffix(".tmp")
                tmp_path.write_text(
                    json.dumps(payload, separators=(",", ":")),
                    encoding="utf-8",
                )
                tmp_path.replace(self._path)
            except OSError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    # ── Logging ─────────────────────────────────────────────────────────

    def log_snapshot(self, snapshot: CostSnapshot):
        """Append a snapshot. Deduplicates to max 1 per 5 minutes (or 1m for first 5 pts)."""
        now = datetime.now()
        
        # Fast Start: Se temos poucos pontos, gravamos rapidamente (10s) 
        # para o gráfico aparecer logo. Depois seguimos o padrão de 5 minutos.
        effective_min = timedelta(seconds=10) if len(self._entries) < 30 else _MIN_INTERVAL

        if self._last_write and (now - self._last_write) < effective_min:
            # Se já temos pelo menos 5 pontos, podemos apenas atualizar o último 
            # para manter o tempo entre os pontos "puro", mas para o início rápido,
            # queremos acumular pontos novos.
            if len(self._entries) >= 5:
                if self._entries:
                    self._entries[-1] = asdict(snapshot)
                    self._save()
                return
            else:
                # No início rápido, se passou menos de 10s, ignoramos.
                return

        self._entries.append(asdict(snapshot))
        self._last_write = now
        self._save()

    def import_history(
        self,
        invoices: list[dict],
        charges: list[dict],
        current_balance: float,
        sync_meta: dict | None = None,
    ) -> dict:
        """Backfill balance history from Vast invoices and charge records.

        Vast billing gives us two different streams: invoices/top-ups and
        itemized charges. We walk them backwards from the current balance so
        the local dashboard can draw a real balance timeline even before many
        live snapshots have accumulated.
        """
        events: list[dict] = []
        summary = _empty_summary(sync_meta)

        min_ts = None
        max_ts = None

        for inv in invoices:
            ts = _timestamp(inv, ("end", "start", "timestamp", "when", "paid_on"))
            credit = _invoice_credit_amount(inv)
            if ts is None or credit <= 0:
                continue
            
            if min_ts is None or ts < min_ts: min_ts = ts
            if max_ts is None or ts > max_ts: max_ts = ts

            events.append({
                "ts": ts,
                "amount": credit,
                "kind": "credit",
                "rate": 0.0,
            })
            summary["credits"] += credit
            summary["invoice_count"] += 1
            if ts > self._last_recharge_ts:
                self._last_recharge_ts = ts
                self._last_recharge_val = credit

        for chg in charges:
            ts = _timestamp(chg, ("end", "start", "day", "timestamp", "when"))
            amount = _positive_amount(chg.get("amount"))
            if ts is None or amount <= 0:
                continue
            
            if min_ts is None or ts < min_ts: min_ts = ts
            if max_ts is None or ts > max_ts: max_ts = ts

            cats = _charge_categories(chg)
            if not any(cats.values()):
                cats[_charge_category(chg)] += amount

            start_ts = _timestamp(chg, ("start",))
            duration_h = ((ts - start_ts) / 3600.0) if start_ts and ts > start_ts else 0.0
            rate = (amount / duration_h) if duration_h > 0 else _positive_amount(chg.get("rate"))
            source = str(chg.get("source") or chg.get("instance_id") or chg.get("description") or "unknown")

            events.append({
                "ts": ts,
                "amount": amount,
                "kind": "charge",
                "rate": rate,
                "categories": cats,
                "source": source,
            })
            summary["charges"] += amount
            summary["charge_count"] += 1
            for key, value in cats.items():
                summary["categories"][key] = round(summary["categories"].get(key, 0.0) + value, 4)
            summary["sources"][source] = round(summary["sources"].get(source, 0.0) + amount, 4)

        summary["coverage_start"] = min_ts
        summary["coverage_end"] = max_ts

        def _persist_event(item):
            ts_end = float(item["ts"])
            amount = round(float(item["amount"]), 4)
            rate = max(0.0, float(item.get("rate") or 0.0))
            kind = item["kind"]
            # Credits are instantaneous (no span); charges span [ts - amount/rate, ts].
            if kind == "charge" and rate > 0 and amount > 0:
                duration_h = amount / rate
                ts_start = ts_end - duration_h * 3600.0
            else:
                ts_start = ts_end
            return {
                "ts": datetime.fromtimestamp(ts_end).isoformat(timespec="seconds"),
                "ts_start": datetime.fromtimestamp(ts_start).isoformat(timespec="seconds"),
                "amount": amount,
                "rate": round(rate, 6),
                "kind": kind,
                "source": item.get("source", "unknown"),
                "categories": item.get("categories", {}),
            }

        self._billing_events = [
            _persist_event(item) for item in events
            if item.get("kind") in ("charge", "credit")
        ]

        if not events:
            self._billing_summary = _finalize_summary(summary)
            self._save()
            return self._billing_summary

        events.sort(key=lambda x: x["ts"], reverse=True)

        running_balance = float(current_balance)
        historic_entries: list[dict] = []
        for item in events:
            ts = float(item["ts"])
            dt = datetime.fromtimestamp(ts)
            amount = float(item["amount"])
            rate = max(0.0, float(item.get("rate") or 0.0))
            cats = item.get("categories") or {}

            historic_entries.append(asdict(CostSnapshot(
                ts=dt.isoformat(timespec="seconds"),
                balance=round(running_balance, 4),
                burn_total=round(rate, 4),
                burn_gpu=round(cats.get("gpu", rate if item["kind"] == "charge" else 0.0), 4),
                burn_storage=round(cats.get("storage", 0.0), 4),
                burn_network=round(cats.get("network", 0.0), 4),
                instances=[],
            )))

            if item["kind"] == "credit":
                running_balance -= amount
            else:
                running_balance += amount

            historic_entries.append(asdict(CostSnapshot(
                ts=(dt - timedelta(seconds=1)).isoformat(timespec="seconds"),
                balance=round(running_balance, 4),
                burn_total=0.0,
                burn_gpu=0.0,
                burn_storage=0.0,
                burn_network=0.0,
                instances=[],
            )))

        unique = {p["ts"]: p for p in (historic_entries + self._entries)}
        self._entries = [unique[k] for k in sorted(unique.keys())]
        self._billing_summary = _finalize_summary(summary)
        self._save()
        return self._billing_summary

    # ── Queries ─────────────────────────────────────────────────────────

    def smoothed_balance_timeline(self, hours: int = 24, current_balance: float = 0.0,
                                  live_dph: float = 0.0, live_since: datetime | None = None) -> list[tuple[str, float]]:
        """Reconstruct a smooth balance timeline by walking backward from current_balance.
        Instead of using the 'cliff' snapshots from the log, it uses _spend_in_window
        which redistributes lump charges across their time span.
        """
        now = datetime.now()
        start = now - timedelta(hours=hours)
        
        # Sampling: ~144 points for 24h (every 10 minutes)
        # Cap at 288 points max to avoid performance issues
        points_count = min(288, max(24, int(hours * 6)))
        step_s = (now - start).total_seconds() / points_count
        
        # We need credits too for reconstruction
        credits = [ev for ev in self._billing_events if ev.get("kind") == "credit"]
        
        out = []
        for i in range(points_count + 1):
            t = start + timedelta(seconds=step_s * i)
            if t > now: t = now
            
            # balance(t) = balance(now) + spend_in_[t, now] - credits_in_[t, now]
            # _spend_in_window handles the distribution of lumps.
            spend = self._spend_in_window(t, now, fallback_days=max(1, hours // 24 + 1))
            
            # Live overlay part for spending between last charge and now
            # Note: _spend_in_window only looks at billing events (past).
            # We add live extrapolation for the gap between last charge and current time.
            live_spend = 0.0
            if live_dph > 0 and live_since is not None:
                l_start = max(t, live_since)
                l_end = now
                if l_end > l_start:
                    live_spend = (live_dph / 3600.0) * (l_end - l_start).total_seconds()
            
            # Credits (top-ups) between t and now
            topups = 0.0
            for c in credits:
                c_dt = _parse_ts(c.get("ts"))
                if c_dt and t <= c_dt <= now:
                    topups += float(c.get("amount") or 0.0)
            
            val = current_balance + spend + live_spend - topups
            out.append((t.isoformat(timespec="seconds"), round(val, 4)))
            
        return out

    def balance_timeline(self, hours: int = 24) -> list[tuple[str, float]]:
        """Return (timestamp, balance) pairs for the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            (e["ts"], e["balance"])
            for e in self._entries_since(cutoff, include_anchor=True)
            if "balance" in e
        ]

    def burn_rate_timeline(self, hours: int = 24) -> list[tuple[str, float]]:
        """Return (timestamp, burn_rate) pairs for the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            (e["ts"], e.get("burn_total", 0.0))
            for e in self._entries_since(cutoff, include_anchor=True)
        ]

    def period_spend(self, days: int = 1) -> float:
        """Return total consumption (balance drops only) within the last N days.
        Caps the anchor age to avoid using snapshots from weeks ago for a 24h metric.
        """
        cutoff = datetime.now() - timedelta(days=days)
        # Cap anchor age at 2x the period window
        max_age = float(days * 2 * 86400)
        period = self._entries_since(cutoff, include_anchor=True, max_anchor_age_s=max_age)
        spend = 0.0
        for i in range(1, len(period)):
            p, c = period[i-1]["balance"], period[i]["balance"]
            if c < p: # Pure consumption
                spend += (p - c)
        return round(spend, 4)

    def today_spend(self) -> float:
        now = datetime.now()
        start = datetime.combine(now.date(), datetime.min.time())
        return self._spend_in_window(start, now, fallback_days=1)

    def week_spend(self) -> float:
        now = datetime.now()
        week_start = now.date() - timedelta(days=now.weekday())
        start = datetime.combine(week_start, datetime.min.time())
        return self._spend_in_window(start, now, fallback_days=7)

    def month_spend(self) -> float:
        now = datetime.now()
        start = datetime(now.year, now.month, 1)
        return self._spend_in_window(start, now, fallback_days=30)

    def last_charge_end(self) -> datetime | None:
        """Latest end timestamp among charge events (for live-overlay bounds)."""
        latest = None
        for ev in self._billing_events:
            if ev.get("kind") != "charge":
                continue
            dt = _parse_ts(ev.get("ts"))
            if dt is not None and (latest is None or dt > latest):
                latest = dt
        return latest

    def daily_spend_history(self, days: int = 7) -> list[tuple[str, float]]:
        """Return a list of (date_str, spend_usd) pairs aggregated by calendar day."""
        days = max(1, int(days))
        today = datetime.now().date()
        start_day = today - timedelta(days=days - 1)
        buckets = {
            start_day + timedelta(days=i): 0.0
            for i in range(days)
        }
        if self._billing_events:
            window_start = datetime.combine(start_day, datetime.min.time())
            window_end = datetime.combine(
                today + timedelta(days=1), datetime.min.time()
            )
            for event in self._billing_events:
                if event.get("kind") != "charge":
                    continue
                c_start, c_end, _rate = self._charge_span(event)
                if c_start is None or c_end is None:
                    continue
                amount = float(event.get("amount") or 0.0)
                if amount <= 0:
                    continue
                if c_end <= c_start:
                    if window_start <= c_end < window_end:
                        day = c_end.date()
                        if day in buckets:
                            buckets[day] += amount
                    continue
                ovl_start = max(c_start, window_start)
                ovl_end = min(c_end, window_end)
                if ovl_end <= ovl_start:
                    continue
                span_s = (c_end - c_start).total_seconds()
                rate_per_s = amount / span_s
                cursor = ovl_start
                while cursor < ovl_end:
                    day = cursor.date()
                    next_midnight = datetime.combine(
                        day + timedelta(days=1), datetime.min.time()
                    )
                    slice_end = min(next_midnight, ovl_end)
                    if day in buckets:
                        buckets[day] += (slice_end - cursor).total_seconds() * rate_per_s
                    cursor = slice_end
            return [(day.strftime("%d %b"), round(value, 3)) for day, value in buckets.items()]

        entries = self._entries_since(
            datetime.combine(start_day, datetime.min.time()),
            include_anchor=True,
        )
        for prev, curr in zip(entries, entries[1:]):
            drop = prev.get("balance", 0.0) - curr.get("balance", 0.0)
            if drop <= 0:
                continue
            curr_dt = _parse_ts(curr.get("ts"))
            if curr_dt is None:
                continue
            day = curr_dt.date()
            if day in buckets:
                buckets[day] += drop
        return [(day.strftime("%d %b"), round(value, 3)) for day, value in buckets.items()]

    def spend_buckets(self, hours: int = 24, bucket_count: int = 8,
                      live_dph: float = 0.0,
                      live_since: datetime | None = None
                      ) -> list[tuple[str, float]]:
        """Return balance-drop spend in evenly sized buckets for short ranges.
        If ``live_dph > 0`` and ``live_since`` is given, extrapolate spend at
        that rate across ``[live_since, now]`` and fold it into the buckets so
        the chart ticks live between charge lumps."""
        hours = max(1, int(hours))
        bucket_count = max(1, int(bucket_count))
        end = datetime.now()
        start = end - timedelta(hours=hours)
        bucket_seconds = (end - start).total_seconds() / bucket_count
        values = [0.0 for _ in range(bucket_count)]

        if self._billing_events:
            # Redistribute each charge uniformly across its [c_start, c_end] span,
            # so a single lump posted at 18:42 covering 35h spreads across the
            # overlapping buckets instead of piling into one bar.
            for event in self._billing_events:
                if event.get("kind") != "charge":
                    continue
                c_start, c_end, _rate = self._charge_span(event)
                if c_start is None or c_end is None:
                    continue
                amount = float(event.get("amount") or 0.0)
                if amount <= 0:
                    continue
                if c_end <= c_start:
                    # Point charge — drop into its bucket if inside window.
                    if start <= c_end <= end:
                        idx = int((c_end - start).total_seconds() // bucket_seconds)
                        idx = max(0, min(bucket_count - 1, idx))
                        values[idx] += amount
                    continue
                ovl_start = max(c_start, start)
                ovl_end = min(c_end, end)
                if ovl_end <= ovl_start:
                    continue
                span_s = (c_end - c_start).total_seconds()
                rate_per_s = amount / span_s
                # Walk the overlap in per-bucket slices.
                cursor = ovl_start
                while cursor < ovl_end:
                    idx = int((cursor - start).total_seconds() // bucket_seconds)
                    idx = max(0, min(bucket_count - 1, idx))
                    bucket_end = start + timedelta(seconds=bucket_seconds * (idx + 1))
                    slice_end = min(bucket_end, ovl_end)
                    values[idx] += (slice_end - cursor).total_seconds() * rate_per_s
                    cursor = slice_end

            # Live overlay: extrapolate from the last charge forward at dph.
            if live_dph > 0 and live_since is not None:
                live_end = end
                live_start = max(live_since, start)
                if live_end > live_start:
                    rate_per_s = live_dph / 3600.0
                    cursor = live_start
                    while cursor < live_end:
                        idx = int((cursor - start).total_seconds() // bucket_seconds)
                        idx = max(0, min(bucket_count - 1, idx))
                        bucket_end = start + timedelta(seconds=bucket_seconds * (idx + 1))
                        slice_end = min(bucket_end, live_end)
                        values[idx] += (slice_end - cursor).total_seconds() * rate_per_s
                        cursor = slice_end

            labels = []
            for i, value in enumerate(values):
                bucket_start = start + timedelta(seconds=bucket_seconds * i)
                labels.append((bucket_start.strftime("%H:%M"), round(value, 3)))
            return labels

        entries = self._entries_since(start, include_anchor=True)
        for prev, curr in zip(entries, entries[1:]):
            drop = prev.get("balance", 0.0) - curr.get("balance", 0.0)
            if drop <= 0:
                continue
            curr_dt = _parse_ts(curr.get("ts"))
            if curr_dt is None or curr_dt < start:
                continue
            idx = int((curr_dt - start).total_seconds() // bucket_seconds)
            idx = max(0, min(bucket_count - 1, idx))
            values[idx] += drop

        labels = []
        for i, value in enumerate(values):
            bucket_start = start + timedelta(seconds=bucket_seconds * i)
            labels.append((bucket_start.strftime("%H:%M"), round(value, 3)))
        return labels

    def _entries_since(self, cutoff: datetime, include_anchor: bool = False,
                       max_anchor_age_s: float | None = None) -> list[dict]:
        parsed = []
        for entry in self._entries:
            dt = _parse_ts(entry.get("ts"))
            if dt is not None:
                parsed.append((dt, entry))
        parsed.sort(key=lambda item: item[0])
        out = [entry for dt, entry in parsed if dt >= cutoff]
        if include_anchor:
            anchor = next((entry for dt, entry in reversed(parsed) if dt < cutoff), None)
            if anchor is not None:
                if max_anchor_age_s is not None:
                    anchor_dt = _parse_ts(anchor.get("ts"))
                    if anchor_dt and (cutoff - anchor_dt).total_seconds() > max_anchor_age_s:
                        return out
                out.insert(0, anchor)
        return out

    def _charge_span(self, event: dict) -> tuple[datetime | None, datetime | None, float]:
        """Return (start, end, rate) for a charge event. Falls back to a
        point-in-time span at `ts` when rate/start are missing (old data)."""
        end = _parse_ts(event.get("ts"))
        start = _parse_ts(event.get("ts_start"))
        rate = float(event.get("rate") or 0.0)
        if start is None and end is not None and rate > 0:
            amount = float(event.get("amount") or 0.0)
            if amount > 0:
                start = end - timedelta(hours=amount / rate)
        if start is None:
            start = end
        return start, end, rate

    def _spend_in_window(self, start: datetime, end: datetime,
                         fallback_days: int) -> float:
        """Sum charge amounts, redistributing each charge uniformly across
        [charge.start, charge.end]. Handles the 'Vast posts one lump covering
        many hours' case: a charge spanning yesterday→today only contributes
        its today portion to today_spend."""
        if not self._billing_events:
            return self.period_spend(fallback_days)
        total = 0.0
        for event in self._billing_events:
            if event.get("kind") != "charge":
                continue
            c_start, c_end, _rate = self._charge_span(event)
            if c_start is None or c_end is None or c_end <= c_start:
                # Point event — count it if ts falls in window
                if c_end is not None and start <= c_end <= end:
                    total += float(event.get("amount") or 0.0)
                continue
            overlap_start = max(c_start, start)
            overlap_end = min(c_end, end)
            if overlap_end <= overlap_start:
                continue
            span_s = (c_end - c_start).total_seconds()
            ovl_s = (overlap_end - overlap_start).total_seconds()
            amount = float(event.get("amount") or 0.0)
            total += amount * (ovl_s / span_s)
        return round(total, 4)

    def _charge_events_since(self, start: datetime) -> list[dict]:
        out = []
        for event in self._billing_events:
            if event.get("kind") != "charge":
                continue
            dt = _parse_ts(event.get("ts"))
            if dt is not None and dt >= start:
                out.append(event)
        return out

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def latest_balance(self) -> float | None:
        if self._entries:
            return self._entries[-1].get("balance")
        return None

    @property
    def billing_summary(self) -> dict:
        return dict(self._billing_summary)

    @property
    def has_billing_events(self) -> bool:
        return bool(self._billing_events)


def _empty_summary(sync_meta: dict | None = None) -> dict:
    return {
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "range_days": int((sync_meta or {}).get("days") or 30),
        "charge_count": 0,
        "invoice_count": 0,
        "charges": 0.0,
        "credits": 0.0,
        "categories": {"gpu": 0.0, "storage": 0.0, "network": 0.0, "other": 0.0},
        "sources": {},
        "coverage_start": None,
        "coverage_end": None,
    }


def _finalize_summary(summary: dict) -> dict:
    sources = summary.pop("sources", {})
    top_sources = sorted(
        ({"source": source, "amount": amount} for source, amount in sources.items()),
        key=lambda item: item["amount"],
        reverse=True,
    )[:5]
    summary["top_sources"] = top_sources
    summary["charges"] = round(summary["charges"], 4)
    summary["credits"] = round(summary["credits"], 4)
    summary["net"] = round(summary["charges"] - summary["credits"], 4)
    summary["categories"] = {
        key: round(float(value), 4)
        for key, value in summary.get("categories", {}).items()
    }
    
    # Format range dates if they exist
    if summary.get("coverage_start"):
        dt = _parse_ts(summary["coverage_start"])
        if dt: summary["coverage_start_label"] = dt.strftime("%b %d")
    if summary.get("coverage_end"):
        dt = _parse_ts(summary["coverage_end"])
        if dt: summary["coverage_end_label"] = dt.strftime("%b %d")
        
    return summary


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _positive_amount(v: Any) -> float:
    amount = _to_float(v)
    if amount is None:
        return 0.0
    return abs(amount)


def _timestamp(row: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        raw = row.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return float(raw)
        text = str(raw).strip()
        if not text:
            continue
        if text.replace(".", "", 1).isdigit():
            return float(text)
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
    return None


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw))
    text = str(raw).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return datetime.fromtimestamp(float(text))
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _invoice_credit_amount(row: dict) -> float:
    amount_cents = _to_float(row.get("amount_cents"))
    if amount_cents is not None:
        amount = abs(amount_cents) / 100.0
        if amount_cents < 0 or row.get("is_credit"):
            return amount

    amount = _to_float(row.get("amount"))
    if amount is None:
        return 0.0
    type_text = " ".join(
        str(row.get(k, "")).lower()
        for k in ("type", "source", "description")
    )
    is_credit = (
        amount < 0
        or row.get("is_credit")
        or any(token in type_text for token in (
            "credit", "deposit", "payment", "stripe", "coinbase",
            "bitpay", "crypto.com", "paypal", "wise", "transfer",
        ))
    )
    return abs(amount) if is_credit else 0.0


def _charge_categories(row: dict) -> dict[str, float]:
    out = {"gpu": 0.0, "storage": 0.0, "network": 0.0, "other": 0.0}

    def visit(item: dict):
        children = item.get("items")
        if isinstance(children, list) and children:
            for child in children:
                if isinstance(child, dict):
                    visit(child)
            return
        amount = _positive_amount(item.get("amount"))
        if amount <= 0:
            return
        out[_charge_category(item)] += amount

    visit(row)
    return {k: round(v, 4) for k, v in out.items()}


def _charge_category(row: dict) -> str:
    text = " ".join(
        str(row.get(k, "")).lower()
        for k in ("type", "source", "description")
    )
    if any(token in text for token in ("storage", "disk", "volume")):
        return "storage"
    if any(token in text for token in ("bandwidth", "upload", "download", "network", "inet")):
        return "network"
    if any(token in text for token in ("gpu", "instance", "compute", "rental")):
        return "gpu"
    return "other"
