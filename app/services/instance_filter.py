from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

from app.models import Instance, InstanceState


def gpu_key(inst: Instance) -> str:
    """Canonical GPU display key: '1x RTX 3090', rendered with multiplication sign."""
    n = max(1, int(inst.num_gpus or 1))
    return f"{n}× {inst.gpu_name}"


@dataclass
class FilterState:
    gpu_types: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    label: str | None = None
    sort: str = "auto"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FilterState":
        if not d:
            return cls()
        return cls(
            gpu_types=list(d.get("gpu_types", []) or []),
            statuses=list(d.get("statuses", []) or []),
            label=d.get("label"),
            sort=d.get("sort", "auto") or "auto",
        )


_STATE_RANK = {
    InstanceState.RUNNING: 0,
    InstanceState.STARTING: 1,
    InstanceState.STOPPING: 2,
    InstanceState.STOPPED: 3,
    InstanceState.UNKNOWN: 4,
}


def _sort(items: list[Instance], key: str) -> list[Instance]:
    if key == "auto":
        return sorted(
            items,
            key=lambda i: (_STATE_RANK.get(i.state, 99), -(i.duration_seconds or 0)),
        )
    if key == "price_asc":
        return sorted(items, key=lambda i: i.dph or 0.0)
    if key == "price_desc":
        return sorted(items, key=lambda i: -(i.dph or 0.0))
    if key == "uptime_asc":
        return sorted(items, key=lambda i: i.duration_seconds or 0)
    if key == "uptime_desc":
        return sorted(items, key=lambda i: -(i.duration_seconds or 0))
    if key == "dlperf":
        return sorted(items, key=lambda i: -(i.dlperf or 0.0))
    if key == "dlperf_per_dollar":
        return sorted(items, key=lambda i: -(i.flops_per_dphtotal or 0.0))
    if key == "reliability":
        return sorted(items, key=lambda i: -(i.reliability or 0.0))
    if key == "status":
        return sorted(items, key=lambda i: _STATE_RANK.get(i.state, 99))
    return list(items)


def apply(instances: Iterable[Instance], state: FilterState) -> list[Instance]:
    out = list(instances)
    if state.gpu_types:
        wanted = set(state.gpu_types)
        out = [i for i in out if gpu_key(i) in wanted]
    if state.statuses:
        wanted_s = set(state.statuses)
        out = [i for i in out if i.state.value in wanted_s]
    if state.label:
        if state.label == "__none__":
            out = [i for i in out if not i.label]
        else:
            out = [i for i in out if i.label == state.label]
    return _sort(out, state.sort)
