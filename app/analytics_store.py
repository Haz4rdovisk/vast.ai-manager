"""Persistent analytics store — append-only JSON log of cost snapshots.
Provides real spending data computed from balance deltas over time.

Storage: ~/.vastai-app/analytics.json
Retention: 30 days, auto-pruned on load.
Sampling: 1 entry per 5 minutes max.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional


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
        self._last_write: datetime | None = None
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
            # Se for o formato antigo (list)
            elif isinstance(data, list):
                self._entries = data
                self._last_recharge_val = 0.0
                self._last_recharge_ts = 0.0
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
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "entries": self._entries,
                "last_recharge_val": self._last_recharge_val,
                "last_recharge_ts": self._last_recharge_ts
            }
            self._path.write_text(
                json.dumps(payload, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError:
            pass

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

    def import_history(self, invoices: list[dict], charges: list[dict], current_balance: float):
        """Backfill history by reverse-calculating balance from both top-ups and usage."""
        # Standardize and Combine
        raw_items = []
        for inv in invoices:
            ts = inv.get("timestamp") or inv.get("when")
            if not ts: continue
            
            # Detect top-up
            amount_cents = inv.get("amount_cents")
            amount_raw = inv.get("amount")
            if amount_cents is not None:
                amt = abs(float(amount_cents)) / 100.0
                is_topup = (amount_cents < 0) or inv.get("is_credit", False)
            else:
                try: amt = float(amount_raw if amount_raw is not None else 0)
                except: amt = 0.0
                type_str = str(inv.get("type", "")).lower()
                is_topup = type_str in ["deposit", "payment", "credit"] or (type_str != "charge" and amt > 0)
            
            raw_items.append({"ts": ts, "amt": amt, "is_topup": is_topup})

        for chg in charges:
            ts = chg.get("timestamp") or chg.get("when")
            amt = float(chg.get("amount") or 0)
            rate = float(chg.get("rate") or 0)
            if ts and amt > 0:
                raw_items.append({"ts": ts, "amt": amt, "rate": rate, "is_topup": False})

        if not raw_items:
            return

        # Sort newest first
        raw_items.sort(key=lambda x: x["ts"], reverse=True)
        
        running_balance = current_balance
        historic_entries = []
        
        for item in raw_items:
            ts, amt, rate, is_topup = item["ts"], item["amt"], item.get("rate", 0.0), item["is_topup"]
            dt = datetime.fromtimestamp(ts)
            iso = dt.isoformat()
            
            # Capture state AFTER (going backwards)
            historic_entries.append(asdict(CostSnapshot(
                ts=iso, balance=running_balance,
                burn_total=rate, burn_gpu=rate, burn_storage=0.0, burn_network=0.0, instances=[]
            )))

            # Detect recharge for fuel tank metadata
            if is_topup and ts > self._last_recharge_ts:
                self._last_recharge_ts = ts
                self._last_recharge_val = amt

            # Apply reverse math
            if is_topup: running_balance -= amt
            else: running_balance += amt

            # Capture state BEFORE (the "step")
            historic_entries.append(asdict(CostSnapshot(
                ts=(dt - timedelta(seconds=1)).isoformat(),
                balance=running_balance,
                burn_total=0.0, burn_gpu=0.0, burn_storage=0.0, burn_network=0.0, instances=[]
            )))

        # Merge unique points
        unique = {p["ts"]: p for p in (historic_entries + self._entries)}
        sorted_keys = sorted(unique.keys())
        self._entries = [unique[k] for k in sorted_keys]
        self._save()
        self.log_line.emit(f"✓ Timeline reconstruída: {len(self._entries)} pontos")

    # ── Queries ─────────────────────────────────────────────────────────

    def balance_timeline(self, hours: int = 24) -> list[tuple[str, float]]:
        """Return (timestamp, balance) pairs for the last N hours."""
        if not self._entries:
            return []
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        return [
            (e["ts"], e["balance"])
            for e in self._entries
            if e.get("ts", "") >= cutoff
        ]

    def burn_rate_timeline(self, hours: int = 24) -> list[tuple[str, float]]:
        """Return (timestamp, burn_rate) pairs for the last N hours."""
        if not self._entries:
            return []
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        return [
            (e["ts"], e.get("burn_total", 0.0))
            for e in self._entries
            if e.get("ts", "") >= cutoff
        ]

    def period_spend(self, days: int = 1) -> float:
        """Return total consumption (balance drops only) within the last N days."""
        if not self._entries:
            return 0.0
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        period = [e for e in self._entries if e.get("ts", "") >= cutoff]
        
        spend = 0.0
        for i in range(1, len(period)):
            p, c = period[i-1]["balance"], period[i]["balance"]
            if c < p: # Pure consumption
                spend += (p - c)
        return round(spend, 4)

    def today_spend(self) -> float:
        return self.period_spend(1)

    def week_spend(self) -> float:
        return self.period_spend(7)

    def month_spend(self) -> float:
        return self.period_spend(30)

    def daily_spend_history(self, days: int = 7) -> list[tuple[str, float]]:
        """Return a list of (date_str, spend_usd) pairs aggregated by calendar day."""
        if not self._entries:
            return []
            
        cutoff = (datetime.now() - timedelta(days=days)).date()
        
        # 1. Group snapshots by date
        from collections import defaultdict
        by_day = defaultdict(list)
        for e in self._entries:
            dt = datetime.fromisoformat(e["ts"]).date()
            if dt >= cutoff:
                by_day[dt].append(e)
                
        # 2. For each day, calculate spend as the sum of balance drops
        # (This correctly ignore deposits/top-ups)
        results = []
        sorted_dates = sorted(by_day.keys())
        for d in sorted_dates:
            entries = by_day[d]
            day_spend = 0.0
            for i in range(1, len(entries)):
                prev_bal = entries[i-1]["balance"]
                curr_bal = entries[i]["balance"]
                if curr_bal < prev_bal:
                    day_spend += (prev_bal - curr_bal)
            results.append((d.strftime("%d %b"), round(day_spend, 3)))
            
        return results

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def latest_balance(self) -> float | None:
        if self._entries:
            return self._entries[-1].get("balance")
        return None
