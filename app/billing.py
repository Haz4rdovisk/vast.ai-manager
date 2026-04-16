from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable
from app.models import Instance, InstanceState


def burn_rate(instances: Iterable[Instance]) -> float:
    return round(sum(i.dph for i in instances if i.state == InstanceState.RUNNING), 4)


def autonomy_hours(balance: float, burn: float) -> float | None:
    if burn <= 0:
        return None
    return balance / burn


@dataclass
class _Sample:
    last_duration: int
    last_dph: float


@dataclass
class DailySpendTracker:
    today_fn: Callable[[], date] = field(default_factory=lambda: date.today)
    _day: date | None = None
    _total: float = 0.0
    _per_instance: dict[int, _Sample] = field(default_factory=dict)

    def update(self, inst: Instance) -> None:
        today = self.today_fn()
        if self._day is None:
            self._day = today
        if today != self._day:
            self._day = today
            self._total = 0.0
            self._per_instance.clear()
        if inst.duration_seconds is None:
            return
        prev = self._per_instance.get(inst.id)
        if prev is None:
            self._per_instance[inst.id] = _Sample(inst.duration_seconds, inst.dph)
            return
        delta_sec = inst.duration_seconds - prev.last_duration
        if delta_sec > 0:
            self._total += (delta_sec / 3600.0) * prev.last_dph
        self._per_instance[inst.id] = _Sample(inst.duration_seconds, inst.dph)

    def today_spend(self) -> float:
        return round(self._total, 4)
