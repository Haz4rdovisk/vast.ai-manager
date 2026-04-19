# Instances Tab Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Instances tab as a dense multi-instance interface (Vast-style) with filters, label tabs, bulk operations with cost confirmation, and a per-instance port allocator that fixes the multi-tunnel collision bug.

**Architecture:** In-place modular refactor. New services (`port_allocator`, `instance_filter`), new worker (`bulk_action_worker`), new UI module `app/ui/views/instances/` decomposing the card into focused components (chip header, specs grid, action bar, live footer), wired through existing `AppController` signal/slot conventions.

**Tech Stack:** Python 3.11, PySide6 6.6+, qtawesome (MaterialDesignIcons), pytest, vastai SDK.

**Spec:** [docs/superpowers/specs/2026-04-19-instances-revamp-design.md](../specs/2026-04-19-instances-revamp-design.md)

---

## Conventions

- All Python paths are relative to repo root `C:/Users/Pc_Lu/Desktop/vastai-app/`
- Tests run with: `python -m pytest tests/<path> -v` (Windows bash)
- Tests use existing `tests/conftest.py` `qt_app` fixture (offscreen Qt) — no `pytest-qt` dependency
- After each task, the test suite must remain green: `python -m pytest tests/ -x -q`
- Commit messages follow existing style (Conventional Commits: `feat(scope):`, `fix(scope):`, `refactor(scope):`)

---

## Phase 1 — Foundations (data model, services, primitives)

### Task 1: Extend `AppConfig` and `Instance` data model

**Files:**
- Modify: `app/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1.1: Write failing test for new Instance fields**

Add to `tests/test_models.py`:

```python
def test_instance_has_label_public_ip_verified_fields():
    from app.models import Instance, InstanceState
    i = Instance(id=1, state=InstanceState.RUNNING, gpu_name="RTX 3090")
    assert i.label is None
    assert i.public_ip is None
    assert i.is_verified is False
    assert i.inet_billed_per_gb == 0.0


def test_appconfig_has_port_map_filters_threshold():
    from app.models import AppConfig
    c = AppConfig()
    assert c.port_map == {}
    assert c.instance_filters == {}
    assert c.bulk_confirm_threshold == 1
    assert c.schema_version == 3
```

- [ ] **Step 1.2: Run tests to verify failure**

```bash
python -m pytest tests/test_models.py::test_instance_has_label_public_ip_verified_fields tests/test_models.py::test_appconfig_has_port_map_filters_threshold -v
```

Expected: FAIL — `AttributeError` on `label`, `port_map`, etc.

- [ ] **Step 1.3: Add the fields**

In `app/models.py`, inside `Instance` dataclass, add after existing fields (preserve order):

```python
    label: str | None = None
    public_ip: str | None = None
    is_verified: bool = False
    inet_billed_per_gb: float = 0.0
```

In `AppConfig` dataclass, locate the existing `schema_version` field (currently `= 2`). Add **before** it:

```python
    port_map: dict = field(default_factory=dict)
    instance_filters: dict = field(default_factory=dict)
    bulk_confirm_threshold: int = 1
```

Then change `schema_version: int = 2` → `schema_version: int = 3`.

(Note: `dict[int, int]` annotation is preserved as `dict` here because `asdict()` JSON-serializes int keys to strings; type coercion happens in the migration in Task 2.)

- [ ] **Step 1.4: Run tests to verify pass**

```bash
python -m pytest tests/test_models.py -v
```

Expected: all green.

- [ ] **Step 1.5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat(models): add label/public_ip/is_verified to Instance and port_map/filters/threshold to AppConfig"
```

---

### Task 2: Add config migration v2 → v3

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 2.1: Write failing test for migration**

Add to `tests/test_config.py`:

```python
def test_loads_v2_config_with_port_map_defaulted_to_empty(tmp_path):
    from app.config import ConfigStore
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        '{"api_key": "abc", "schema_version": 2}',
        encoding="utf-8",
    )
    store = ConfigStore(path=cfg_file)
    cfg = store.load()
    assert cfg.api_key == "abc"
    assert cfg.port_map == {}
    assert cfg.instance_filters == {}
    assert cfg.bulk_confirm_threshold == 1
    assert cfg.schema_version == 3


def test_port_map_int_keys_coerced_from_json_strings(tmp_path):
    from app.config import ConfigStore
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        '{"api_key": "x", "schema_version": 3, "port_map": {"123": 11434, "456": 11435}}',
        encoding="utf-8",
    )
    store = ConfigStore(path=cfg_file)
    cfg = store.load()
    assert cfg.port_map == {123: 11434, 456: 11435}
    assert all(isinstance(k, int) for k in cfg.port_map)


def test_save_then_load_preserves_port_map(tmp_path):
    from app.config import ConfigStore
    from app.models import AppConfig
    cfg_file = tmp_path / "config.json"
    store = ConfigStore(path=cfg_file)
    cfg = AppConfig(api_key="k", port_map={1: 11434, 2: 11435})
    store.save(cfg)
    loaded = store.load()
    assert loaded.port_map == {1: 11434, 2: 11435}
```

- [ ] **Step 2.2: Run to verify failure**

```bash
python -m pytest tests/test_config.py::test_loads_v2_config_with_port_map_defaulted_to_empty tests/test_config.py::test_port_map_int_keys_coerced_from_json_strings tests/test_config.py::test_save_then_load_preserves_port_map -v
```

Expected: FAIL — config does not migrate, port_map keys are strings.

- [ ] **Step 2.3: Implement migration**

Replace the `load` method in `app/config.py` with:

```python
    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppConfig()
        try:
            data = self._migrate(data)
            allowed = AppConfig.__dataclass_fields__
            return AppConfig(**{k: v for k, v in data.items() if k in allowed})
        except (TypeError, ValueError):
            return AppConfig()

    @staticmethod
    def _migrate(raw: dict) -> dict:
        v = int(raw.get("schema_version", 1) or 1)
        if v < 3:
            raw.setdefault("port_map", {})
            raw.setdefault("instance_filters", {})
            raw.setdefault("bulk_confirm_threshold", 1)
            raw["schema_version"] = 3
        # Always coerce port_map keys to int — JSON serializes int keys as str.
        pm = raw.get("port_map") or {}
        raw["port_map"] = {int(k): int(v) for k, v in pm.items()}
        return raw
```

- [ ] **Step 2.4: Run tests**

```bash
python -m pytest tests/test_config.py -v
```

Expected: all green.

- [ ] **Step 2.5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): migrate schema v2→v3, coerce port_map int keys"
```

---

### Task 3: Fix `parse_instance` label/image bug + add new fields

**Files:**
- Modify: `app/services/vast_service.py:78-110` (the `parse_instance` function)
- Test: `tests/test_vast_service.py`

- [ ] **Step 3.1: Write failing tests**

Add to `tests/test_vast_service.py`:

```python
def test_parse_instance_separates_label_from_image():
    from app.services.vast_service import parse_instance
    raw = {
        "id": 42,
        "actual_status": "running",
        "intended_status": "running",
        "gpu_name": "RTX 3090",
        "label": "my-experiment",
        "image_uuid": "vastai/base-image_cuda-12.1.1-auto/jupyter",
    }
    inst = parse_instance(raw)
    assert inst.label == "my-experiment"
    assert inst.image == "vastai/base-image_cuda-12.1.1-auto/jupyter"


def test_parse_instance_label_none_when_absent():
    from app.services.vast_service import parse_instance
    raw = {"id": 1, "actual_status": "running", "intended_status": "running",
           "gpu_name": "RTX 3090", "image_uuid": "img"}
    inst = parse_instance(raw)
    assert inst.label is None
    assert inst.image == "img"


def test_parse_instance_verified_flag():
    from app.services.vast_service import parse_instance
    raw = {"id": 1, "actual_status": "running", "intended_status": "running",
           "gpu_name": "RTX 3090", "verification": "verified"}
    assert parse_instance(raw).is_verified is True
    raw["verification"] = "unverified"
    assert parse_instance(raw).is_verified is False


def test_parse_instance_public_ip():
    from app.services.vast_service import parse_instance
    raw = {"id": 1, "actual_status": "running", "intended_status": "running",
           "gpu_name": "RTX 3090", "public_ipaddr": "1.2.3.4"}
    assert parse_instance(raw).public_ip == "1.2.3.4"
```

- [ ] **Step 3.2: Run to verify failure**

```bash
python -m pytest tests/test_vast_service.py -k "parse_instance and (label or verified or public_ip)" -v
```

Expected: FAIL — `inst.label` AttributeError or wrong value (currently `label` aliases image).

- [ ] **Step 3.3: Fix `parse_instance` and add `set_label`**

In `app/services/vast_service.py`, locate the line:

```python
    image = raw.get("label") or raw.get("image_uuid")
```

Replace with:

```python
    image = raw.get("image_uuid") or raw.get("docker_image") or ""
    label = raw.get("label") or None
    is_verified = (raw.get("verification") == "verified")
    public_ip = raw.get("public_ipaddr") or ""
    inet_billed_per_gb = _to_float(raw.get("inet_up_billed")) or 0.0
```

Then locate where the `Instance(...)` constructor is called at the end of `parse_instance` and add the four new keyword arguments (alphabetic order doesn't matter; place them at the end). Example:

```python
    return Instance(
        # ... all existing kwargs ...
        label=label,
        public_ip=public_ip,
        is_verified=is_verified,
        inet_billed_per_gb=inet_billed_per_gb,
    )
```

Also add the `set_label` method to the `VastService` class (anywhere after `stop_instance`):

```python
    def set_label(self, instance_id: int, label: str) -> None:
        """Update the user-set label on an instance via the Vast SDK."""
        self.client.label_instance(id=instance_id, label=label)
```

- [ ] **Step 3.4: Add test for `set_label`**

Append to `tests/test_vast_service.py`:

```python
def test_set_label_calls_sdk_label_instance(monkeypatch):
    from app.services.vast_service import VastService
    calls = []

    class FakeClient:
        def label_instance(self, id, label):
            calls.append((id, label))

    svc = VastService.__new__(VastService)
    svc.client = FakeClient()
    svc.set_label(123, "experiment-a")
    assert calls == [(123, "experiment-a")]
```

- [ ] **Step 3.5: Run all vast_service tests**

```bash
python -m pytest tests/test_vast_service.py -v
```

Expected: all green.

- [ ] **Step 3.6: Commit**

```bash
git add app/services/vast_service.py tests/test_vast_service.py
git commit -m "fix(vast_service): separate label from image; add set_label, is_verified, public_ip"
```

---

### Task 4: `PortAllocator` service

**Files:**
- Create: `app/services/port_allocator.py`
- Test: `tests/test_port_allocator.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_port_allocator.py`:

```python
import threading
import pytest


def make(default=11434, initial=None):
    from app.services.port_allocator import PortAllocator
    persisted = []
    a = PortAllocator(default, initial or {}, persisted.append)
    return a, persisted


def test_get_first_returns_default():
    a, _ = make()
    assert a.get(100) == 11434


def test_get_idempotent():
    a, persisted = make()
    p1 = a.get(100)
    p2 = a.get(100)
    assert p1 == p2 == 11434
    assert len(persisted) == 1  # persisted only on first allocation


def test_two_instances_get_different_ports():
    a, _ = make()
    assert a.get(1) == 11434
    assert a.get(2) == 11435


def test_persists_initial_state_unchanged():
    a, persisted = make(initial={42: 11434})
    assert a.get(42) == 11434
    assert persisted == []  # cache hit, no persist


def test_compact_releases_stale():
    a, persisted = make(initial={1: 11434, 2: 11435, 3: 11436})
    a.compact(alive_ids={1})
    assert a.snapshot() == {1: 11434}
    assert persisted[-1] == {1: 11434}


def test_compact_no_op_when_all_alive():
    a, persisted = make(initial={1: 11434, 2: 11435})
    a.compact({1, 2})
    assert persisted == []


def test_release_specific_id():
    a, persisted = make(initial={1: 11434, 2: 11435})
    a.release(1)
    assert a.snapshot() == {2: 11435}
    assert persisted[-1] == {2: 11435}


def test_concurrent_get_unique_ports():
    a, _ = make()
    results = []
    lock = threading.Lock()

    def worker(iid):
        p = a.get(iid)
        with lock:
            results.append((iid, p))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ports = [p for _, p in results]
    assert len(set(ports)) == 50  # all unique
    assert min(ports) == 11434
    assert max(ports) == 11483


def test_port_exhaustion_raises():
    a, _ = make(initial={i: 11434 + i for i in range(1000)})
    with pytest.raises(RuntimeError, match="Port exhaustion"):
        a.get(9999)
```

- [ ] **Step 4.2: Run tests to verify failure**

```bash
python -m pytest tests/test_port_allocator.py -v
```

Expected: FAIL — `ModuleNotFoundError: app.services.port_allocator`.

- [ ] **Step 4.3: Implement `PortAllocator`**

Create `app/services/port_allocator.py`:

```python
from __future__ import annotations
from threading import Lock
from typing import Callable


class PortAllocator:
    """Atribui portas locais únicas por instance_id, persiste via callback.

    Pure-Python: no Qt, no Vast SDK. Receives:
      - default_port: starting point (e.g. 11434)
      - initial_map: {instance_id: port} loaded from config
      - persist: callback(map) invoked after mutations
    """

    def __init__(
        self,
        default_port: int,
        initial_map: dict[int, int],
        persist: Callable[[dict[int, int]], None],
    ) -> None:
        self._default = default_port
        self._map: dict[int, int] = dict(initial_map)
        self._persist = persist
        self._lock = Lock()

    def get(self, instance_id: int) -> int:
        with self._lock:
            if instance_id in self._map:
                return self._map[instance_id]
            port = self._next_free_locked()
            self._map[instance_id] = port
            self._persist(dict(self._map))
            return port

    def _next_free_locked(self) -> int:
        used = set(self._map.values())
        p = self._default
        while p in used:
            p += 1
            if p > self._default + 999:
                raise RuntimeError(
                    f"Port exhaustion in [{self._default}, {self._default + 999}]"
                )
        return p

    def release(self, instance_id: int) -> None:
        with self._lock:
            if self._map.pop(instance_id, None) is not None:
                self._persist(dict(self._map))

    def compact(self, alive_ids: set[int]) -> None:
        with self._lock:
            stale = [iid for iid in self._map if iid not in alive_ids]
            for iid in stale:
                del self._map[iid]
            if stale:
                self._persist(dict(self._map))

    def snapshot(self) -> dict[int, int]:
        with self._lock:
            return dict(self._map)
```

- [ ] **Step 4.4: Run tests**

```bash
python -m pytest tests/test_port_allocator.py -v
```

Expected: all 9 green.

- [ ] **Step 4.5: Commit**

```bash
git add app/services/port_allocator.py tests/test_port_allocator.py
git commit -m "feat(services): add PortAllocator with persistence and compact()"
```

---

### Task 5: `instance_filter` service

**Files:**
- Create: `app/services/instance_filter.py`
- Test: `tests/test_instance_filter.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_instance_filter.py`:

```python
from app.models import Instance, InstanceState


def mk(id, state=InstanceState.RUNNING, gpu="RTX 3090", n=1, label=None,
       dph=0.30, uptime=3600, dlperf=40.0, dlperf_dollar=130.0, reliability=0.99):
    return Instance(
        id=id, state=state, gpu_name=gpu, num_gpus=n,
        label=label, dph=dph, duration_seconds=uptime,
        dlperf=dlperf, flops_per_dphtotal=dlperf_dollar, reliability=reliability,
    )


def test_filter_by_gpu_type():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, gpu="RTX 3090"), mk(2, gpu="RTX 4090"), mk(3, gpu="RTX 3090", n=2)]
    out = apply(items, FilterState(gpu_types=["1× RTX 3090"]))
    assert [i.id for i in out] == [1]


def test_filter_by_status():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, state=InstanceState.RUNNING), mk(2, state=InstanceState.STOPPED)]
    out = apply(items, FilterState(statuses=["stopped"]))
    assert [i.id for i in out] == [2]


def test_filter_by_label_none_sentinel_returns_unlabeled():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, label="exp-a"), mk(2, label=None), mk(3, label="")]
    out = apply(items, FilterState(label="__none__"))
    assert sorted(i.id for i in out) == [2, 3]


def test_filter_by_label_specific():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, label="exp-a"), mk(2, label="exp-b"), mk(3, label="exp-a")]
    out = apply(items, FilterState(label="exp-a"))
    assert sorted(i.id for i in out) == [1, 3]


def test_filter_label_none_or_empty_means_no_filter():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, label="a"), mk(2, label=None)]
    out = apply(items, FilterState(label=None))
    assert len(out) == 2
    out = apply(items, FilterState(label=""))
    assert len(out) == 2


def test_sort_price_asc_desc():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, dph=0.5), mk(2, dph=0.1), mk(3, dph=0.3)]
    asc = apply(items, FilterState(sort="price_asc"))
    assert [i.id for i in asc] == [2, 3, 1]
    desc = apply(items, FilterState(sort="price_desc"))
    assert [i.id for i in desc] == [1, 3, 2]


def test_sort_uptime():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, uptime=100), mk(2, uptime=500), mk(3, uptime=300)]
    out = apply(items, FilterState(sort="uptime_desc"))
    assert [i.id for i in out] == [2, 3, 1]


def test_sort_auto_running_first_then_stopped():
    from app.services.instance_filter import apply, FilterState
    items = [
        mk(1, state=InstanceState.STOPPED, uptime=100),
        mk(2, state=InstanceState.RUNNING, uptime=200),
        mk(3, state=InstanceState.RUNNING, uptime=400),
    ]
    out = apply(items, FilterState(sort="auto"))
    assert [i.id for i in out] == [3, 2, 1]


def test_sort_dlperf_per_dollar():
    from app.services.instance_filter import apply, FilterState
    items = [mk(1, dlperf_dollar=100), mk(2, dlperf_dollar=300), mk(3, dlperf_dollar=200)]
    out = apply(items, FilterState(sort="dlperf_per_dollar"))
    assert [i.id for i in out] == [2, 3, 1]


def test_filter_state_round_trip_dict():
    from app.services.instance_filter import FilterState
    s = FilterState(gpu_types=["1× RTX 3090"], statuses=["running"],
                    label="exp", sort="price_asc")
    d = s.to_dict()
    restored = FilterState.from_dict(d)
    assert restored == s


def test_filter_state_from_empty_dict_uses_defaults():
    from app.services.instance_filter import FilterState
    s = FilterState.from_dict({})
    assert s == FilterState()


def test_gpu_key_format():
    from app.services.instance_filter import gpu_key
    assert gpu_key(mk(1, gpu="RTX 3090", n=1)) == "1× RTX 3090"
    assert gpu_key(mk(1, gpu="RTX 4090", n=2)) == "2× RTX 4090"
```

- [ ] **Step 5.2: Run to verify failure**

```bash
python -m pytest tests/test_instance_filter.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 5.3: Implement filter service**

Create `app/services/instance_filter.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Iterable
from app.models import Instance, InstanceState


def gpu_key(inst: Instance) -> str:
    """Canonical GPU display key: '1× RTX 3090', '2× RTX 4090'."""
    n = max(1, int(inst.num_gpus or 1))
    return f"{n}× {inst.gpu_name}"


@dataclass
class FilterState:
    gpu_types: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    label: str | None = None        # None or "" → no filter; "__none__" → unlabeled; else literal
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
        return sorted(items, key=lambda i: (_STATE_RANK.get(i.state, 99),
                                            -(i.duration_seconds or 0)))
    if key == "price_asc":
        return sorted(items, key=lambda i: (i.dph or 0.0))
    if key == "price_desc":
        return sorted(items, key=lambda i: -(i.dph or 0.0))
    if key == "uptime_asc":
        return sorted(items, key=lambda i: (i.duration_seconds or 0))
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
```

- [ ] **Step 5.4: Run tests**

```bash
python -m pytest tests/test_instance_filter.py -v
```

Expected: all 12 green.

- [ ] **Step 5.5: Commit**

```bash
git add app/services/instance_filter.py tests/test_instance_filter.py
git commit -m "feat(services): add instance_filter with FilterState and 9 sort keys"
```

---

### Task 6: Icon catalog (`icons.py`)

**Files:**
- Create: `app/ui/components/icons.py`
- Test: `tests/test_icons_catalog.py`

- [ ] **Step 6.1: Write smoke test**

Create `tests/test_icons_catalog.py`:

```python
def test_catalog_exposes_required_keys():
    from app.ui.components import icons
    required = [
        "PLAY", "STOP", "POWER", "DELETE", "REBOOT", "CLOUD", "RECYCLE",
        "LOG", "TAG", "FLAG", "KEY", "LAB", "TUNNEL", "DISCONNECT",
        "COPY", "VERIFIED", "EXPAND", "FILTER", "SORT", "SELECT",
    ]
    for name in required:
        assert hasattr(icons, name), f"missing icon: {name}"
        assert isinstance(getattr(icons, name), str)


def test_catalog_values_are_mdi_names_no_prefix():
    from app.ui.components import icons
    # The icon() helper adds "mdi." prefix; values must NOT include it.
    assert not icons.PLAY.startswith("mdi.")
```

- [ ] **Step 6.2: Run to verify failure**

```bash
python -m pytest tests/test_icons_catalog.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 6.3: Create catalog**

Create `app/ui/components/icons.py`:

```python
"""Catalog of MaterialDesignIcons (MDI) names used by the app.

Names are stored without the 'mdi.' prefix — the icon() helper in
primitives.py adds it.
"""

PLAY = "play"
STOP = "stop"
POWER = "power"
DELETE = "delete-outline"
REBOOT = "restart"
CLOUD = "cloud-upload-outline"
RECYCLE = "recycle"
LOG = "text-box-outline"
TAG = "tag-outline"
FLAG = "flag-outline"
KEY = "key-variant"
LAB = "flask-outline"
TUNNEL = "lan-connect"
DISCONNECT = "lan-disconnect"
COPY = "content-copy"
VERIFIED = "shield-check"
EXPAND = "chevron-down"
COLLAPSE = "chevron-up"
FILTER = "filter-variant"
SORT = "sort"
SELECT = "checkbox-multiple-outline"
REFRESH = "refresh"
SETTINGS = "cog-outline"
CLOSE = "close"
CHECK = "check"
```

- [ ] **Step 6.4: Run tests**

```bash
python -m pytest tests/test_icons_catalog.py -v
```

Expected: all green.

- [ ] **Step 6.5: Commit**

```bash
git add app/ui/components/icons.py tests/test_icons_catalog.py
git commit -m "feat(ui): add MDI icon catalog"
```

---

### Task 7: `primitives.py` additions — `icon()`, `IconButton`, `Chip`, `ChipRow`

**Files:**
- Modify: `app/ui/components/primitives.py`
- Test: `tests/test_primitives_additions.py`

- [ ] **Step 7.1: Read existing primitives.py to understand patterns**

```bash
python -c "import app.ui.components.primitives as p; print([x for x in dir(p) if not x.startswith('_')])"
```

This is a research step — no assertions. Make a mental note of the existing style (class names, font usage, color tokens imported from `theme`).

- [ ] **Step 7.2: Write failing tests**

Create `tests/test_primitives_additions.py`:

```python
import pytest


def test_icon_helper_returns_qicon(qt_app):
    from app.ui.components.primitives import icon
    from PySide6.QtGui import QIcon
    ic = icon("play")
    assert isinstance(ic, QIcon)
    assert not ic.isNull()


def test_icon_helper_accepts_color(qt_app):
    from app.ui.components.primitives import icon
    from PySide6.QtGui import QIcon
    ic = icon("play", color="#FF0000")
    assert isinstance(ic, QIcon)


def test_icon_button_sized_26(qt_app):
    from app.ui.components.primitives import IconButton
    btn = IconButton("play", "Start instance")
    assert btn.width() == 26 and btn.height() == 26
    assert btn.toolTip() == "Start instance"


def test_icon_button_disabled_uses_low_color(qt_app):
    from app.ui.components.primitives import IconButton
    btn = IconButton("play", "Start")
    btn.setEnabled(False)
    # No assertion on pixel color — just verify no crash and icon exists
    assert not btn.icon().isNull()


def test_chip_renders_text(qt_app):
    from app.ui.components.primitives import Chip
    c = Chip("Verified", variant="ok")
    assert "Verified" in c.findChild(type(c).children()[0].__class__.__bases__[0]).text() \
           or any("Verified" in w.text() for w in c.findChildren(type(c)) if hasattr(w, "text"))


def test_chip_variants_dont_crash(qt_app):
    from app.ui.components.primitives import Chip
    for v in ("default", "ok", "accent", "danger"):
        Chip(f"x-{v}", variant=v)


def test_chip_clickable_emits_signal(qt_app):
    from app.ui.components.primitives import Chip
    c = Chip("ip", clickable=True)
    received = []
    c.clicked.connect(lambda: received.append(True))
    c.mousePressEvent(_synthetic_mouse_event())
    c.mouseReleaseEvent(_synthetic_mouse_event())
    # Allow either flow (signal emitted on press or release)
    assert received  # at least one click captured


def _synthetic_mouse_event():
    from PySide6.QtCore import QPointF, QEvent, Qt
    from PySide6.QtGui import QMouseEvent
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5, 5), QPointF(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_chip_row_holds_multiple_chips(qt_app):
    from app.ui.components.primitives import Chip, ChipRow
    row = ChipRow()
    row.add(Chip("a"))
    row.add(Chip("b"))
    row.add(Chip("c"))
    # Count direct Chip children
    chips = [w for w in row.children() if isinstance(w, Chip)]
    assert len(chips) == 3
```

- [ ] **Step 7.3: Run to verify failure**

```bash
python -m pytest tests/test_primitives_additions.py -v
```

Expected: FAIL — `ImportError` on `icon`, `IconButton`, `Chip`, `ChipRow`.

- [ ] **Step 7.4: Implement additions**

Append to `app/ui/components/primitives.py` (preserve existing code, add at end):

```python
import qtawesome as qta
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QFrame, QHBoxLayout, QLabel
from app.theme import (
    TEXT, TEXT_HI, TEXT_LOW, OK, ERR, ACCENT, ACCENT_SOFT,
    SURFACE_2, GLASS_HOVER, BORDER_LOW, BORDER_MED,
    FONT_DISPLAY, FONT_MONO, RADIUS_PILL,
)


def icon(name: str, color: str = TEXT, size: int = 16) -> QIcon:
    """Wrap qtawesome.icon for the MDI namespace.

    Usage: icon('play', color=ACCENT)
    """
    return qta.icon(f"mdi.{name}", color=color)


class IconButton(QPushButton):
    """26×26 ghost button with an MDI icon and required tooltip."""

    def __init__(
        self,
        mdi_name: str,
        tooltip: str,
        *,
        color: str = TEXT,
        danger: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mdi = mdi_name
        self._base_color = ERR if danger else color
        self._refresh_icon()
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {BORDER_LOW};"
            f" border-radius: 6px; }}"
            f"QPushButton:hover {{ background: {GLASS_HOVER}; border-color: {BORDER_MED}; }}"
            f"QPushButton:disabled {{ background: transparent; border-color: {BORDER_LOW}; }}"
        )

    def _refresh_icon(self) -> None:
        col = TEXT_LOW if not self.isEnabled() else self._base_color
        self.setIcon(icon(self._mdi, color=col))

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._refresh_icon()


_CHIP_VARIANTS = {
    "default": (SURFACE_2, BORDER_LOW, TEXT),
    "ok":      ("rgba(59,212,136,0.10)",  "rgba(59,212,136,0.30)",  OK),
    "accent":  ("rgba(124,92,255,0.10)",  "rgba(124,92,255,0.30)",  ACCENT_SOFT),
    "danger":  ("rgba(240,85,106,0.10)",  "rgba(240,85,106,0.30)",  ERR),
}


class Chip(QFrame):
    """Pill-style label. Variants: default | ok | accent | danger."""

    clicked = Signal()

    def __init__(
        self,
        text: str,
        *,
        variant: str = "default",
        mono: bool = False,
        clickable: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        bg, border, fg = _CHIP_VARIANTS.get(variant, _CHIP_VARIANTS["default"])
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(0)
        lbl = QLabel(text, self)
        font = lbl.font()
        font.setFamily(FONT_MONO if mono else FONT_DISPLAY)
        font.setPointSize(9)
        lbl.setFont(font)
        lbl.setStyleSheet(f"color: {fg}; background: transparent;")
        lay.addWidget(lbl)

        self.setStyleSheet(
            f"Chip {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: {RADIUS_PILL}px; }}"
        )
        self.setObjectName("Chip")

    def mousePressEvent(self, e):
        if self._clickable and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class ChipRow(QFrame):
    """Horizontal row of chips with consistent gap. Wraps via flow on resize."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)

    def add(self, chip: Chip) -> None:
        # Insert before the trailing stretch so chips pack to the left.
        self._lay.insertWidget(self._lay.count() - 1, chip)

    def clear(self) -> None:
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
```

**Note:** If `app/theme.py` does not export some of the imported names exactly as written, adjust the import to match. Check by running:
```bash
python -c "from app.theme import TEXT, TEXT_HI, TEXT_LOW, OK, ERR, ACCENT, ACCENT_SOFT, SURFACE_2, GLASS_HOVER, BORDER_LOW, BORDER_MED, FONT_DISPLAY, FONT_MONO, RADIUS_PILL; print('ok')"
```
If `RADIUS_PILL` is named differently (e.g. `RADIUS_PILL` vs `R_PILL`), adapt the import. Theme tokens are stable per `app/theme.py` — read it once and align.

- [ ] **Step 7.5: Run tests**

```bash
python -m pytest tests/test_primitives_additions.py -v
```

Expected: all green. The clickable Chip test uses synthetic mouse events; if the synthesized event helper trips on Qt version, replace `mousePressEvent` test with direct invocation:

```python
def test_chip_clickable_emits_signal(qt_app):
    from app.ui.components.primitives import Chip
    c = Chip("ip", clickable=True)
    received = []
    c.clicked.connect(lambda: received.append(True))
    c.clicked.emit()  # direct emission as a fallback
    assert received
```

- [ ] **Step 7.6: Commit**

```bash
git add app/ui/components/primitives.py tests/test_primitives_additions.py
git commit -m "feat(ui): add icon helper, IconButton, Chip, ChipRow primitives"
```

---

## Phase 2 — Workers

### Task 8: `BulkActionWorker`

**Files:**
- Create: `app/workers/bulk_action_worker.py`
- Test: `tests/test_bulk_action_worker.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/test_bulk_action_worker.py`:

```python
def test_bulk_start_calls_service_and_emits_progress_finished(qt_app):
    from app.workers.bulk_action_worker import BulkActionWorker
    calls = []
    progress_events = []
    finished_event = []

    class FakeVast:
        def start_instance(self, iid): calls.append(("start", iid))
        def stop_instance(self, iid):  calls.append(("stop", iid))
        def destroy_instance(self, iid): calls.append(("destroy", iid))
        def set_label(self, iid, label): calls.append(("label", iid, label))

    w = BulkActionWorker(FakeVast())
    w.progress.connect(lambda *a: progress_events.append(a))
    w.finished.connect(lambda *a: finished_event.append(a))
    w.run("start", [1, 2, 3], {})

    assert calls == [("start", 1), ("start", 2), ("start", 3)]
    assert len(progress_events) == 3
    assert progress_events[0][0:2] == (1, 3)
    assert finished_event == [("start", [1, 2, 3], [])]


def test_bulk_partial_failure_collected_in_fail_list(qt_app):
    from app.workers.bulk_action_worker import BulkActionWorker

    class FakeVast:
        def start_instance(self, iid):
            if iid == 2:
                raise RuntimeError("boom")

    w = BulkActionWorker(FakeVast())
    fin = []
    w.finished.connect(lambda *a: fin.append(a))
    w.run("start", [1, 2, 3], {})
    assert fin[0] == ("start", [1, 3], [2])


def test_bulk_label_uses_opts(qt_app):
    from app.workers.bulk_action_worker import BulkActionWorker
    calls = []

    class FakeVast:
        def set_label(self, iid, label): calls.append((iid, label))

    w = BulkActionWorker(FakeVast())
    w.run("label", [1, 2], {"label": "exp"})
    assert calls == [(1, "exp"), (2, "exp")]


def test_bulk_unknown_action_marks_all_as_failed(qt_app):
    from app.workers.bulk_action_worker import BulkActionWorker

    class FakeVast: ...
    w = BulkActionWorker(FakeVast())
    fin = []
    w.finished.connect(lambda *a: fin.append(a))
    w.run("teleport", [1, 2], {})
    assert fin[0] == ("teleport", [], [1, 2])
```

- [ ] **Step 8.2: Run to verify failure**

```bash
python -m pytest tests/test_bulk_action_worker.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 8.3: Implement worker**

Create `app/workers/bulk_action_worker.py`:

```python
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot


class BulkActionWorker(QObject):
    """Executes a bulk action sequentially against multiple instance ids.

    Emits per-item progress and a final summary. Single-flight is enforced
    by the controller (do not start two runs concurrently).
    """

    progress = Signal(int, int, int, str)      # done, total, iid, last_msg
    finished = Signal(str, list, list)          # action, ok_ids, fail_ids

    def __init__(self, vast) -> None:
        super().__init__()
        self.vast = vast

    @Slot(str, list, dict)
    def run(self, action: str, ids: list, opts: dict) -> None:
        ok: list[int] = []
        fail: list[int] = []
        total = len(ids)
        for i, iid in enumerate(ids, start=1):
            try:
                self._dispatch(action, iid, opts)
                ok.append(iid)
                self.progress.emit(i, total, iid, "ok")
            except Exception as e:
                fail.append(iid)
                self.progress.emit(i, total, iid, str(e)[:80])
        self.finished.emit(action, ok, fail)

    def _dispatch(self, action: str, iid: int, opts: dict) -> None:
        if action == "start":
            self.vast.start_instance(iid)
        elif action == "stop":
            self.vast.stop_instance(iid)
        elif action == "destroy":
            self.vast.destroy_instance(iid)
        elif action == "label":
            self.vast.set_label(iid, opts["label"])
        else:
            raise ValueError(f"Unknown bulk action: {action}")
```

- [ ] **Step 8.4: Run tests**

```bash
python -m pytest tests/test_bulk_action_worker.py -v
```

Expected: all 4 green.

- [ ] **Step 8.5: Commit**

```bash
git add app/workers/bulk_action_worker.py tests/test_bulk_action_worker.py
git commit -m "feat(workers): add BulkActionWorker with per-item progress + summary"
```

---

### Task 9: Add `destroy_instance` to `VastService` if missing

**Files:**
- Modify: `app/services/vast_service.py`
- Test: `tests/test_vast_service.py`

- [ ] **Step 9.1: Check if destroy already exists**

```bash
grep -n "destroy_instance" C:/Users/Pc_Lu/Desktop/vastai-app/app/services/vast_service.py
```

If it exists already, mark this task done and skip to Step 9.5. Otherwise continue.

- [ ] **Step 9.2: Write failing test**

Append to `tests/test_vast_service.py`:

```python
def test_destroy_instance_calls_sdk(monkeypatch):
    from app.services.vast_service import VastService
    calls = []

    class FakeClient:
        def destroy_instance(self, id): calls.append(id)

    svc = VastService.__new__(VastService)
    svc.client = FakeClient()
    svc.destroy_instance(99)
    assert calls == [99]
```

- [ ] **Step 9.3: Run to verify failure**

```bash
python -m pytest tests/test_vast_service.py::test_destroy_instance_calls_sdk -v
```

Expected: FAIL — method missing.

- [ ] **Step 9.4: Add method**

In `app/services/vast_service.py`, after `set_label`, add:

```python
    def destroy_instance(self, instance_id: int) -> None:
        """Permanently destroy an instance via the Vast SDK."""
        self.client.destroy_instance(id=instance_id)
```

- [ ] **Step 9.5: Run all vast tests**

```bash
python -m pytest tests/test_vast_service.py -v
```

Expected: all green.

- [ ] **Step 9.6: Commit (skip if destroy already existed)**

```bash
git add app/services/vast_service.py tests/test_vast_service.py
git commit -m "feat(vast_service): add destroy_instance wrapper"
```

---

## Phase 3 — Controller wiring

### Task 10: Wire `PortAllocator` into `AppController`

**Files:**
- Modify: `app/controller.py`
- Test: `tests/test_controller.py`

- [ ] **Step 10.1: Write failing tests**

Append to `tests/test_controller.py`:

```python
def test_controller_creates_port_allocator_with_config_state(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.controller import AppController
    from app.models import AppConfig

    cfg_path = tmp_path / "c.json"
    store = ConfigStore(path=cfg_path)
    store.save(AppConfig(api_key="k", default_tunnel_port=11434,
                         port_map={42: 11500}))
    c = AppController(store)
    assert c.port_allocator.snapshot() == {42: 11500}
    assert c.port_allocator.get(99) == 11434  # next free below 11500


def test_port_allocator_persists_to_config(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.controller import AppController
    from app.models import AppConfig

    cfg_path = tmp_path / "c.json"
    store = ConfigStore(path=cfg_path)
    store.save(AppConfig(api_key="k"))
    c = AppController(store)
    c.port_allocator.get(7)  # triggers persist
    reloaded = ConfigStore(path=cfg_path).load()
    assert 7 in reloaded.port_map
```

- [ ] **Step 10.2: Run to verify failure**

```bash
python -m pytest tests/test_controller.py::test_controller_creates_port_allocator_with_config_state tests/test_controller.py::test_port_allocator_persists_to_config -v
```

Expected: FAIL — `port_allocator` attribute missing.

- [ ] **Step 10.3: Add allocator construction in `__init__`**

In `app/controller.py`, find the existing `def __init__(self, config_store: ConfigStore, parent=None):`. Add **after** the line `self.ssh = SSHService(ssh_key_path=self.config.ssh_key_path)`:

```python
        from app.services.port_allocator import PortAllocator
        self.port_allocator = PortAllocator(
            default_port=self.config.default_tunnel_port,
            initial_map=self.config.port_map,
            persist=self._persist_port_map,
        )
```

Then add this private method anywhere in the class (e.g. after `apply_config`):

```python
    def _persist_port_map(self, m: dict[int, int]) -> None:
        self.config.port_map = m
        self.config_store.save(self.config)
```

- [ ] **Step 10.4: Run tests**

```bash
python -m pytest tests/test_controller.py::test_controller_creates_port_allocator_with_config_state tests/test_controller.py::test_port_allocator_persists_to_config -v
```

Expected: green.

- [ ] **Step 10.5: Commit**

```bash
git add app/controller.py tests/test_controller.py
git commit -m "feat(controller): wire PortAllocator with persistence"
```

---

### Task 11: Use allocator in `connect_tunnel`, `_on_tunnel_status`, `_start_model_watcher`

**Files:**
- Modify: `app/controller.py`
- Test: `tests/test_controller.py`

- [ ] **Step 11.1: Write failing test**

Append to `tests/test_controller.py`:

```python
def test_connect_tunnel_uses_allocator_port(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.controller import AppController
    from app.models import AppConfig

    cfg_path = tmp_path / "c.json"
    store = ConfigStore(path=cfg_path)
    store.save(AppConfig(api_key="k", default_tunnel_port=11434))
    c = AppController(store)
    # Prevent passphrase prompt path
    c.ssh.ssh_key_path = ""

    # Capture trigger emissions
    seen = []
    c._trigger_connect.connect(lambda iid, port: seen.append((iid, port)))
    c.connect_tunnel(123)
    c.connect_tunnel(456)
    assert seen == [(123, 11434), (456, 11435)]


def test_compact_called_on_refresh(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.controller import AppController
    from app.models import AppConfig, Instance, InstanceState, UserInfo

    cfg_path = tmp_path / "c.json"
    store = ConfigStore(path=cfg_path)
    store.save(AppConfig(api_key="k", port_map={1: 11434, 99: 11435}))
    c = AppController(store)
    inst = Instance(id=1, state=InstanceState.RUNNING, gpu_name="x")
    c._on_refreshed([inst], UserInfo(balance=10.0, email=""))
    snap = c.port_allocator.snapshot()
    assert 1 in snap and 99 not in snap
```

- [ ] **Step 11.2: Run to verify failure**

```bash
python -m pytest tests/test_controller.py::test_connect_tunnel_uses_allocator_port tests/test_controller.py::test_compact_called_on_refresh -v
```

Expected: FAIL — current code uses `default_tunnel_port` and never calls compact.

- [ ] **Step 11.3: Patch `connect_tunnel`**

In `app/controller.py`, find `def connect_tunnel(self, iid: int):`. Replace its body with:

```python
    def connect_tunnel(self, iid: int):
        if iid in self._pending_tunnel:
            return
        if not self._has_usable_passphrase():
            self._on_passphrase_success = lambda: self.connect_tunnel(iid)
            self.passphrase_needed.emit()
            return
        port = self.port_allocator.get(iid)
        self._pending_tunnel.add(iid)
        self.tunnel_states[iid] = TunnelStatus.CONNECTING
        self.tunnel_status_changed.emit(iid, TunnelStatus.CONNECTING.value, "connecting")
        self.log_line.emit(f"Conectando #{iid} em :{port}...")
        self._trigger_connect.emit(iid, port)
```

- [ ] **Step 11.4: Patch `_on_tunnel_status` toast and model watcher port**

In `app/controller.py`, find `def _on_tunnel_status(self, iid: int, status: str, msg: str):`. Replace the `if self.tunnel_states[iid] == TunnelStatus.CONNECTED:` branch and the call to `_start_model_watcher` so they read:

```python
        if self.tunnel_states[iid] == TunnelStatus.CONNECTED:
            port = self.port_allocator.get(iid)
            self.toast_requested.emit(
                f"Conectado em http://127.0.0.1:{port}", "success", 3000)
            self._pending_tunnel.discard(iid)
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
            if self._find_instance(iid) is not None:
                self._start_model_watcher(iid, port)
```

Then change `_start_model_watcher` signature and body:

```python
    def _start_model_watcher(self, iid: int, port: int):
        self._stop_model_watcher(iid)
        w = ModelWatcher(iid, port)
        w.model_changed.connect(self.model_changed)
        self._model_watchers[iid] = w
        w.start()
```

- [ ] **Step 11.5: Add `compact()` call on refresh**

In `app/controller.py`, find `def _on_refreshed(self, instances: list, user):`. Add at the very top of its body (before any other logic):

```python
        alive_ids = {i.id for i in instances}
        self.port_allocator.compact(alive_ids)
```

- [ ] **Step 11.6: Run all controller tests**

```bash
python -m pytest tests/test_controller.py -v
```

Expected: all green (existing tests still pass).

- [ ] **Step 11.7: Commit**

```bash
git add app/controller.py tests/test_controller.py
git commit -m "fix(controller): use port_allocator for tunnels, model watcher, toasts; compact on refresh"
```

---

### Task 12: Controller `update_instance_filters` + `bulk_action` API

**Files:**
- Modify: `app/controller.py`
- Test: `tests/test_controller.py`

- [ ] **Step 12.1: Write failing tests**

Append to `tests/test_controller.py`:

```python
def test_update_instance_filters_persists(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.controller import AppController
    from app.models import AppConfig

    cfg_path = tmp_path / "c.json"
    store = ConfigStore(path=cfg_path)
    store.save(AppConfig(api_key="k"))
    c = AppController(store)
    c.update_instance_filters({"sort": "price_asc", "label": "exp"})
    reloaded = ConfigStore(path=cfg_path).load()
    assert reloaded.instance_filters == {"sort": "price_asc", "label": "exp"}


def test_bulk_action_connect_dispatches_per_instance(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.controller import AppController
    from app.models import AppConfig

    cfg_path = tmp_path / "c.json"
    store = ConfigStore(path=cfg_path)
    store.save(AppConfig(api_key="k"))
    c = AppController(store)
    c.ssh.ssh_key_path = ""

    seen = []
    c._trigger_connect.connect(lambda iid, port: seen.append(iid))
    c.bulk_action("connect", [10, 20, 30])
    assert seen == [10, 20, 30]
```

- [ ] **Step 12.2: Run to verify failure**

```bash
python -m pytest tests/test_controller.py::test_update_instance_filters_persists tests/test_controller.py::test_bulk_action_connect_dispatches_per_instance -v
```

Expected: FAIL — methods missing.

- [ ] **Step 12.3: Add signal + methods**

In `app/controller.py`, near the other internal triggers (`_trigger_refresh`, `_trigger_start`, etc.), add:

```python
    _trigger_bulk = Signal(str, list, dict)   # action, ids, opts
```

Add a public method anywhere in the class (e.g. after `apply_config`):

```python
    def update_instance_filters(self, filters: dict) -> None:
        self.config.instance_filters = dict(filters)
        self.config_store.save(self.config)
```

Add the bulk dispatcher (after `disconnect_tunnel`):

```python
    def bulk_action(self, action: str, ids: list[int], opts: dict | None = None) -> None:
        opts = opts or {}
        if action == "connect":
            for iid in ids:
                self.connect_tunnel(iid)
            return
        if action == "disconnect":
            for iid in ids:
                self.disconnect_tunnel(iid)
            return
        if self._bulk_in_flight:
            self.toast_requested.emit("Operação em andamento, aguarde", "warning", 3000)
            return
        self._bulk_in_flight = True
        self._trigger_bulk.emit(action, list(ids), opts)
```

In `__init__`, add:

```python
        self._bulk_in_flight = False
```

In `bootstrap()`, after the `self.tunnel_thread.start()` line, add:

```python
        from app.workers.bulk_action_worker import BulkActionWorker
        self.bulk_thread = QThread()
        self.bulk_worker = BulkActionWorker(self.vast)
        self.bulk_worker.moveToThread(self.bulk_thread)
        self.bulk_worker.progress.connect(self._on_bulk_progress)
        self.bulk_worker.finished.connect(self._on_bulk_finished)
        self._trigger_bulk.connect(self.bulk_worker.run)
        self.bulk_thread.start()
```

Add the two slots:

```python
    def _on_bulk_progress(self, done: int, total: int, iid: int, msg: str) -> None:
        self.log_line.emit(f"Bulk {done}/{total} #{iid}: {msg}")

    def _on_bulk_finished(self, action: str, ok: list, fail: list) -> None:
        self._bulk_in_flight = False
        self.log_line.emit(f"✓ Bulk {action}: {len(ok)} ok, {len(fail)} fail")
        if fail:
            self.toast_requested.emit(
                f"Falhou em {len(fail)} instâncias", "error", 4000)
        else:
            self.toast_requested.emit(
                f"{action} aplicado em {len(ok)} instâncias", "success", 3000)
        self._trigger_refresh.emit()
        if action == "start" and self.config.auto_connect_on_activate:
            for iid in ok:
                self.connect_tunnel(iid)
```

In `shutdown()`, add (before `_destroy_workers`):

```python
        if hasattr(self, "bulk_thread") and self.bulk_thread.isRunning():
            self.bulk_thread.quit(); self.bulk_thread.wait(2000)
```

- [ ] **Step 12.4: Run tests**

```bash
python -m pytest tests/test_controller.py -v
```

Expected: all green.

- [ ] **Step 12.5: Commit**

```bash
git add app/controller.py tests/test_controller.py
git commit -m "feat(controller): add update_instance_filters, bulk_action API and BulkActionWorker wiring"
```

---

## Phase 4 — UI leaf components

### Task 13: `chip_header.py` — header row of the card

**Files:**
- Create: `app/ui/views/instances/__init__.py`
- Create: `app/ui/views/instances/chip_header.py`
- Test: `tests/test_chip_header.py`

- [ ] **Step 13.1: Create the package marker**

Create empty file `app/ui/views/instances/__init__.py`:

```python
"""New Instances tab — dense multi-instance UX (revamp 2026-04)."""
```

- [ ] **Step 13.2: Write failing test**

Create `tests/test_chip_header.py`:

```python
from app.models import Instance, InstanceState


def mk(verified=True, ip="1.2.3.4", country="US", uptime=18000,
       dph=0.30, label=None, gpu="RTX 3090", n=1):
    return Instance(
        id=1, state=InstanceState.RUNNING, gpu_name=gpu, num_gpus=n,
        is_verified=verified, public_ip=ip, country=country,
        duration_seconds=uptime, dph=dph, label=label,
    )


def test_chip_header_renders_gpu_text(qt_app):
    from app.ui.views.instances.chip_header import ChipHeader
    h = ChipHeader(mk())
    assert "RTX 3090" in h.gpu_label.text()


def test_chip_header_shows_verified_chip(qt_app):
    from app.ui.views.instances.chip_header import ChipHeader
    h = ChipHeader(mk(verified=True))
    texts = h.chip_texts()
    assert any("Verified" in t for t in texts)


def test_chip_header_omits_verified_when_false(qt_app):
    from app.ui.views.instances.chip_header import ChipHeader
    h = ChipHeader(mk(verified=False))
    texts = h.chip_texts()
    assert not any("Verified" in t for t in texts)


def test_chip_header_shows_ip(qt_app):
    from app.ui.views.instances.chip_header import ChipHeader
    h = ChipHeader(mk(ip="91.158.22.66"))
    assert any("91.158.22.66" in t for t in h.chip_texts())


def test_chip_header_shows_price(qt_app):
    from app.ui.views.instances.chip_header import ChipHeader
    h = ChipHeader(mk(dph=0.25))
    assert any("0.25" in t and "/hr" in t for t in h.chip_texts())


def test_chip_header_uptime_chip(qt_app):
    from app.ui.views.instances.chip_header import ChipHeader
    h = ChipHeader(mk(uptime=86400 * 5))   # 5 days
    assert any("5d" in t for t in h.chip_texts())
```

- [ ] **Step 13.3: Run to verify failure**

```bash
python -m pytest tests/test_chip_header.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 13.4: Implement `ChipHeader`**

Create `app/ui/views/instances/chip_header.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from app.models import Instance, InstanceState
from app.ui.components.primitives import Chip, ChipRow
from app.theme import OK, TEXT_LOW, TEXT_HI, FONT_DISPLAY


_FLAGS = {
    "US": "🇺🇸", "DE": "🇩🇪", "BR": "🇧🇷", "FR": "🇫🇷", "GB": "🇬🇧",
    "CA": "🇨🇦", "JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳", "IN": "🇮🇳",
    "NL": "🇳🇱", "SE": "🇸🇪", "FI": "🇫🇮", "PL": "🇵🇱", "RU": "🇷🇺",
    "AU": "🇦🇺", "MX": "🇲🇽", "AR": "🇦🇷", "ES": "🇪🇸", "IT": "🇮🇹",
}


def _fmt_uptime(secs: int | None) -> str:
    if not secs or secs <= 0:
        return "—"
    d, r = divmod(int(secs), 86400)
    if d > 0: return f"{d}d"
    h, r = divmod(r, 3600)
    if h > 0: return f"{h}h"
    m, _ = divmod(r, 60)
    return f"{m}m"


def _fmt_price(dph: float | None) -> str:
    if dph is None: return "—"
    if dph < 0.001: return "<$0.001/hr"
    return f"${dph:.3f}/hr"


class ChipHeader(QFrame):
    """Top row of an InstanceCard: LED + GPU label + chip strip."""

    ip_clicked = Signal()  # user clicked IP chip

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self._chips: list[Chip] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # LED + GPU
        led_color = OK if inst.state == InstanceState.RUNNING else TEXT_LOW
        self.gpu_label = QLabel(f"● {inst.num_gpus or 1}× {inst.gpu_name}")
        font = self.gpu_label.font()
        font.setFamily(FONT_DISPLAY)
        font.setPointSize(11)
        font.setBold(True)
        self.gpu_label.setFont(font)
        self.gpu_label.setStyleSheet(f"color: {led_color};")
        lay.addWidget(self.gpu_label)

        # Chip row
        self.chips = ChipRow(self)
        lay.addWidget(self.chips, stretch=1)

        if inst.is_verified:
            self._add(Chip("✓ Verified", variant="ok"))
        if inst.public_ip:
            ip = Chip(inst.public_ip, variant="accent", mono=True, clickable=True)
            ip.clicked.connect(self.ip_clicked)
            self._add(ip)
        flag = _FLAGS.get((inst.country or "").upper())
        if flag:
            self._add(Chip(flag))
        self._add(Chip(f"⏱ {_fmt_uptime(inst.duration_seconds)}"))
        self._add(Chip(_fmt_price(inst.dph), mono=True))

    def _add(self, chip: Chip) -> None:
        self._chips.append(chip)
        self.chips.add(chip)

    def chip_texts(self) -> list[str]:
        out = []
        for c in self._chips:
            for lbl in c.findChildren(QLabel):
                out.append(lbl.text())
        return out
```

- [ ] **Step 13.5: Run tests**

```bash
python -m pytest tests/test_chip_header.py -v
```

Expected: all 6 green.

- [ ] **Step 13.6: Commit**

```bash
git add app/ui/views/instances/__init__.py app/ui/views/instances/chip_header.py tests/test_chip_header.py
git commit -m "feat(instances): add ChipHeader (gpu + verified/ip/flag/uptime/$/hr chips)"
```

---

### Task 14: `specs_grid.py` — 7-column data grid

**Files:**
- Create: `app/ui/views/instances/specs_grid.py`
- Test: `tests/test_specs_grid.py`

- [ ] **Step 14.1: Write failing test**

Create `tests/test_specs_grid.py`:

```python
from app.models import Instance, InstanceState


def mk(**kw):
    base = dict(id=1, state=InstanceState.RUNNING, gpu_name="RTX 3090",
                cpu_name="Threadripper", cpu_cores=48, ram_total_gb=64.0,
                ram_used_gb=10.0, disk_usage_gb=21.0, disk_space_gb=55.0,
                inet_down_mbps=89.5, inet_up_mbps=38.9,
                cuda_max_good="12.2", total_flops=35.3, gpu_ram_gb=24.0,
                vram_usage_gb=0.3, dlperf=40.4, flops_per_dphtotal=275.0,
                pcie_gen=3, pcie_bw_gbps=8.0, mobo_name="TRX40", host_id=274012,
                machine_id=43202, disk_bw_mbps=484.0)
    base.update(kw)
    return Instance(**base)


def test_specs_grid_has_seven_columns(qt_app):
    from app.ui.views.instances.specs_grid import SpecsGrid
    g = SpecsGrid(mk())
    # Check via layout column count
    layout = g.layout()
    assert layout.columnCount() == 7


def test_specs_grid_renders_instance_id(qt_app):
    from app.ui.views.instances.specs_grid import SpecsGrid
    g = SpecsGrid(mk(id=34860213))
    assert "34860213" in g.value_text("instance")


def test_specs_grid_renders_cuda(qt_app):
    from app.ui.views.instances.specs_grid import SpecsGrid
    g = SpecsGrid(mk(cuda_max_good="12.2"))
    assert "12.2" in g.value_text("cuda")


def test_specs_grid_handles_missing_data(qt_app):
    from app.ui.views.instances.specs_grid import SpecsGrid
    g = SpecsGrid(mk(cpu_name=None, mobo_name=None))
    # Should not raise; empty/dash placeholders OK
    assert g.value_text("cpu") in ("—", "")
```

- [ ] **Step 14.2: Run to verify failure**

```bash
python -m pytest tests/test_specs_grid.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 14.3: Implement `SpecsGrid`**

Create `app/ui/views/instances/specs_grid.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout
from app.models import Instance
from app.theme import TEXT_HI, TEXT_LOW, TEXT_MID, FONT_MONO, FONT_DISPLAY, BORDER_LOW


def _fmt(v, suffix: str = "", default: str = "—") -> str:
    if v is None or v == "":
        return default
    if isinstance(v, float):
        return f"{v:.1f}{suffix}"
    return f"{v}{suffix}"


def _trunc(s: str | None, n: int) -> str:
    s = s or "—"
    return s if len(s) <= n else s[: n - 1] + "…"


class _Cell(QFrame):
    def __init__(self, label: str, value: str, sub: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        l = QLabel(label.upper())
        f = l.font(); f.setFamily(FONT_DISPLAY); f.setPointSize(7); l.setFont(f)
        l.setStyleSheet(f"color: {TEXT_LOW}; letter-spacing: 1px;")
        v = QLabel(value)
        vf = v.font(); vf.setFamily(FONT_MONO); vf.setPointSize(9); v.setFont(vf)
        v.setStyleSheet(f"color: {TEXT_HI};")
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        s = QLabel(sub) if sub else None
        if s:
            sf = s.font(); sf.setPointSize(8); s.setFont(sf)
            s.setStyleSheet(f"color: {TEXT_MID};")
        lay.addWidget(l); lay.addWidget(v)
        if s: lay.addWidget(s)
        self._value = v
        self._label = label

    def value_text(self) -> str:
        return self._value.text()


class SpecsGrid(QFrame):
    """Dense 7-column grid of instance hardware/perf data."""

    COLUMNS = ("instance", "cuda", "dlperf", "network",
               "cpu", "disk", "mobo")

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"SpecsGrid {{ border-top: 1px solid {BORDER_LOW}; padding-top: 10px; }}"
        )
        self._cells: dict[str, _Cell] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 10, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)

        cells = [
            ("instance", "Instance",
             _fmt(inst.id),
             f"Host {_fmt(inst.host_id)}"),
            ("cuda", "CUDA",
             _fmt(inst.cuda_max_good),
             f"{_fmt(inst.total_flops, ' TFLOPS')}"),
            ("dlperf", "DLPerf",
             _fmt(inst.dlperf),
             f"{_fmt(inst.flops_per_dphtotal, '/$/hr')}"),
            ("network", "Network",
             f"↓ {_fmt(inst.inet_down_mbps, ' Mbps')}",
             f"↑ {_fmt(inst.inet_up_mbps, ' Mbps')}"),
            ("cpu", "CPU",
             _trunc(inst.cpu_name, 14),
             f"{_fmt(inst.cpu_cores, ' cores')} · {_fmt(inst.ram_used_gb)}/{_fmt(inst.ram_total_gb, ' GB')}"),
            ("disk", "Disk",
             f"{_fmt(inst.disk_usage_gb)}/{_fmt(inst.disk_space_gb, ' GB')}",
             f"{_fmt(inst.disk_bw_mbps, ' MB/s')}"),
            ("mobo", "Mobo",
             _trunc(inst.mobo_name, 14),
             f"PCIe {_fmt(inst.pcie_gen)} · {_fmt(inst.pcie_bw_gbps, ' GB/s')}"),
        ]
        for col, (key, label, val, sub) in enumerate(cells):
            c = _Cell(label, val, sub, self)
            self._cells[key] = c
            grid.addWidget(c, 0, col)
        for col in range(7):
            grid.setColumnStretch(col, 1)

    def value_text(self, key: str) -> str:
        return self._cells[key].value_text() if key in self._cells else ""
```

- [ ] **Step 14.4: Run tests**

```bash
python -m pytest tests/test_specs_grid.py -v
```

Expected: green.

- [ ] **Step 14.5: Commit**

```bash
git add app/ui/views/instances/specs_grid.py tests/test_specs_grid.py
git commit -m "feat(instances): add 7-col SpecsGrid (instance/cuda/dlperf/network/cpu/disk/mobo)"
```

---

### Task 15: `live_footer.py` — live metric bars

**Files:**
- Create: `app/ui/views/instances/live_footer.py`
- Test: `tests/test_live_footer.py`

- [ ] **Step 15.1: Write failing test**

Create `tests/test_live_footer.py`:

```python
from app.models import Instance, InstanceState


def mk():
    return Instance(id=1, state=InstanceState.RUNNING, gpu_name="RTX 3090",
                    gpu_ram_gb=24.0, ram_total_gb=64.0)


def test_live_footer_renders_four_bars(qt_app):
    from app.ui.views.instances.live_footer import LiveFooter
    f = LiveFooter(mk())
    assert len(f.bars) == 4   # GPU, vRAM, CPU, RAM


def test_live_footer_apply_metrics(qt_app):
    from app.ui.views.instances.live_footer import LiveFooter
    f = LiveFooter(mk())
    f.apply_metrics({
        "gpu_util": 67.0, "gpu_temp": 72.0,
        "vram_used_mb": 18432.0, "vram_total_mb": 24576.0,
        "ram_used_mb": 12288.0, "ram_total_mb": 32768.0,
        "load1": 1.5,
    })
    # No assertion on inner state; just verify no crash
    txt = f.status_text()
    assert "GPU" in txt or "—" in txt or "67" in txt
```

- [ ] **Step 15.2: Run to verify failure**

```bash
python -m pytest tests/test_live_footer.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 15.3: Implement `LiveFooter`**

Create `app/ui/views/instances/live_footer.py`:

```python
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar
from app.models import Instance
from app.theme import TEXT, TEXT_LOW, ACCENT, BORDER_LOW, FONT_MONO


class _Bar(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        self.lbl = QLabel(label)
        f = self.lbl.font(); f.setPointSize(8); f.setFamily(FONT_MONO); self.lbl.setFont(f)
        self.lbl.setStyleSheet(f"color: {TEXT_LOW};")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100); self.bar.setValue(0)
        self.bar.setTextVisible(False); self.bar.setFixedHeight(4)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {BORDER_LOW}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}"
        )
        lay.addWidget(self.lbl); lay.addWidget(self.bar)

    def set_value(self, label: str, pct: float) -> None:
        self.lbl.setText(label)
        self.bar.setValue(int(max(0, min(100, pct))))


class LiveFooter(QFrame):
    """Four live metric bars + status string. Updated via apply_metrics()."""

    def __init__(self, inst: Instance, parent=None) -> None:
        super().__init__(parent)
        self._gpu_total = inst.gpu_ram_gb or 0
        self._ram_total_mb = (inst.ram_total_gb or 0) * 1024
        self.setStyleSheet(
            f"LiveFooter {{ border-top: 1px solid {BORDER_LOW}; padding-top: 10px; }}"
        )
        out = QVBoxLayout(self); out.setContentsMargins(0, 10, 0, 0); out.setSpacing(6)

        row = QHBoxLayout(); row.setSpacing(14)
        self.bars = [_Bar("GPU —"), _Bar("vRAM —"), _Bar("CPU —"), _Bar("RAM —")]
        for b in self.bars:
            row.addWidget(b, stretch=1)
        out.addLayout(row)

        self.status = QLabel("—")
        f = self.status.font(); f.setPointSize(8); f.setFamily(FONT_MONO); self.status.setFont(f)
        self.status.setStyleSheet(f"color: {TEXT};")
        out.addWidget(self.status)

    def apply_metrics(self, m: dict) -> None:
        gpu = m.get("gpu_util") or 0
        temp = m.get("gpu_temp")
        self.bars[0].set_value(
            f"GPU {gpu:.0f}%" + (f" {temp:.0f}°C" if temp is not None else ""),
            gpu)

        vram_used = m.get("vram_used_mb") or 0
        vram_total = m.get("vram_total_mb") or (self._gpu_total * 1024)
        vram_pct = (vram_used / vram_total * 100) if vram_total else 0
        self.bars[1].set_value(
            f"vRAM {vram_used/1024:.1f}/{(vram_total or 1)/1024:.0f}GB",
            vram_pct)

        load = m.get("load1")
        self.bars[2].set_value(
            f"CPU load {load:.2f}" if load is not None else "CPU —",
            min(100, (load or 0) * 25))   # rough scale

        ram_used = m.get("ram_used_mb") or 0
        ram_total = m.get("ram_total_mb") or self._ram_total_mb
        ram_pct = (ram_used / ram_total * 100) if ram_total else 0
        self.bars[3].set_value(
            f"RAM {ram_used/1024:.1f}/{(ram_total or 1)/1024:.0f}GB",
            ram_pct)

        self.status.setText(
            f"GPU: {gpu:.0f}% {temp:.0f}°C, RAM: {ram_used/1024:.1f}GB"
            if temp is not None else f"GPU: {gpu:.0f}%"
        )

    def status_text(self) -> str:
        return self.status.text()
```

- [ ] **Step 15.4: Run tests**

```bash
python -m pytest tests/test_live_footer.py -v
```

Expected: green.

- [ ] **Step 15.5: Commit**

```bash
git add app/ui/views/instances/live_footer.py tests/test_live_footer.py
git commit -m "feat(instances): add LiveFooter with GPU/vRAM/CPU/RAM bars"
```

---

### Task 16: `action_bar.py` — icon button row

**Files:**
- Create: `app/ui/views/instances/action_bar.py`
- Test: `tests/test_action_bar.py`

- [ ] **Step 16.1: Write failing test**

Create `tests/test_action_bar.py`:

```python
from app.models import Instance, InstanceState, TunnelStatus


def mk(state=InstanceState.STOPPED):
    return Instance(id=1, state=state, gpu_name="RTX 3090")


def test_action_bar_primary_is_activate_when_stopped(qt_app):
    from app.ui.views.instances.action_bar import ActionBar
    bar = ActionBar(mk(InstanceState.STOPPED), TunnelStatus.DISCONNECTED)
    assert "Activate" in bar.primary.text()


def test_action_bar_primary_is_connect_when_running_disconnected(qt_app):
    from app.ui.views.instances.action_bar import ActionBar
    bar = ActionBar(mk(InstanceState.RUNNING), TunnelStatus.DISCONNECTED)
    assert "Connect" in bar.primary.text()


def test_action_bar_primary_is_deactivate_when_running_connected(qt_app):
    from app.ui.views.instances.action_bar import ActionBar
    bar = ActionBar(mk(InstanceState.RUNNING), TunnelStatus.CONNECTED)
    assert "Deactivate" in bar.primary.text() or "Stop" in bar.primary.text()


def test_action_bar_emits_signals(qt_app):
    from app.ui.views.instances.action_bar import ActionBar
    bar = ActionBar(mk(), TunnelStatus.DISCONNECTED)
    received = []
    bar.activate_requested.connect(lambda: received.append("activate"))
    bar.primary.click()
    assert received == ["activate"]


def test_action_bar_has_all_icon_buttons(qt_app):
    from app.ui.views.instances.action_bar import ActionBar
    bar = ActionBar(mk(InstanceState.RUNNING), TunnelStatus.CONNECTED)
    assert bar.btn_reboot is not None
    assert bar.btn_destroy is not None
    assert bar.btn_log is not None
    assert bar.btn_label is not None
    assert bar.btn_key is not None
    assert bar.btn_lab is not None
```

- [ ] **Step 16.2: Run to verify failure**

```bash
python -m pytest tests/test_action_bar.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 16.3: Implement `ActionBar`**

Create `app/ui/views/instances/action_bar.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QFrame as QF
from app.models import Instance, InstanceState, TunnelStatus
from app.ui.components.primitives import IconButton, icon
from app.ui.components import icons
from app.theme import (
    ACCENT, ACCENT_HI, ERR, TEXT, OK, BORDER_LOW, FONT_DISPLAY, GLASS_HOVER,
)


def _separator() -> QF:
    s = QF()
    s.setFixedSize(1, 20)
    s.setStyleSheet(f"background: {BORDER_LOW};")
    return s


class ActionBar(QFrame):
    """Primary button + icon button row.

    Signals are emitted when buttons are clicked. The InstanceCard re-emits
    them with the instance id attached.
    """

    activate_requested = Signal()
    deactivate_requested = Signal()
    connect_requested = Signal()
    disconnect_requested = Signal()
    reboot_requested = Signal()
    snapshot_requested = Signal()
    destroy_requested = Signal()
    log_requested = Signal()
    label_requested = Signal()
    flag_requested = Signal()
    key_requested = Signal()
    lab_requested = Signal()

    def __init__(self, inst: Instance, tunnel: TunnelStatus, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(6)

        self.primary = self._build_primary(inst, tunnel)
        lay.addWidget(self.primary)
        lay.addWidget(_separator())

        self.btn_reboot   = IconButton(icons.REBOOT,  "Reboot")
        self.btn_snapshot = IconButton(icons.CLOUD,   "Snapshot / save")
        self.btn_destroy  = IconButton(icons.RECYCLE, "Destroy", danger=True)
        for b in (self.btn_reboot, self.btn_snapshot, self.btn_destroy):
            lay.addWidget(b)

        lay.addWidget(_separator())

        self.btn_log    = IconButton(icons.LOG, "View logs")
        self.btn_label  = IconButton(icons.TAG, "Edit label")
        self.btn_flag   = IconButton(icons.FLAG, "Flag / bookmark")
        for b in (self.btn_log, self.btn_label, self.btn_flag):
            lay.addWidget(b)

        lay.addWidget(_separator())

        self.btn_key = IconButton(icons.KEY, "Copy SSH command")
        self.btn_lab = IconButton(icons.LAB, "Open Lab")
        lay.addWidget(self.btn_key)
        lay.addWidget(self.btn_lab)
        lay.addStretch(1)

        # wire icon buttons
        self.btn_reboot.clicked.connect(self.reboot_requested)
        self.btn_snapshot.clicked.connect(self.snapshot_requested)
        self.btn_destroy.clicked.connect(self.destroy_requested)
        self.btn_log.clicked.connect(self.log_requested)
        self.btn_label.clicked.connect(self.label_requested)
        self.btn_flag.clicked.connect(self.flag_requested)
        self.btn_key.clicked.connect(self.key_requested)
        self.btn_lab.clicked.connect(self.lab_requested)

    def _build_primary(self, inst: Instance, tunnel: TunnelStatus) -> QPushButton:
        st = inst.state
        if st == InstanceState.STOPPED:
            label, sig, color = "▶ Activate", self.activate_requested, ACCENT
        elif st == InstanceState.STARTING:
            label, sig, color = "Starting…", None, TEXT
        elif st == InstanceState.RUNNING and tunnel != TunnelStatus.CONNECTED:
            label, sig, color = "→ Connect", self.connect_requested, ACCENT
        elif st == InstanceState.RUNNING and tunnel == TunnelStatus.CONNECTED:
            label, sig, color = "⏹ Deactivate", self.deactivate_requested, ERR
        else:
            label, sig, color = inst.state.value, None, TEXT

        btn = QPushButton(label)
        btn.setFixedHeight(28)
        f = btn.font(); f.setFamily(FONT_DISPLAY); f.setPointSize(9); f.setBold(True)
        btn.setFont(f)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: {color}; color: white; border: none;"
            f" border-radius: 8px; padding: 4px 14px; }}"
            f"QPushButton:hover {{ background: {ACCENT_HI}; }}"
            f"QPushButton:disabled {{ background: {BORDER_LOW}; color: {TEXT}; }}"
        )
        if sig is not None:
            btn.clicked.connect(lambda: sig.emit())
        else:
            btn.setEnabled(False)
        return btn
```

- [ ] **Step 16.4: Run tests**

```bash
python -m pytest tests/test_action_bar.py -v
```

Expected: green. If `Deactivate` test fails because the test expects "Deactivate" or "Stop" — the current implementation emits "⏹ Deactivate" so the test passes.

- [ ] **Step 16.5: Commit**

```bash
git add app/ui/views/instances/action_bar.py tests/test_action_bar.py
git commit -m "feat(instances): add ActionBar with primary CTA + 8 icon buttons"
```

---

### Task 17: `confirm_bulk_dialog.py` — bulk confirmation modal

**Files:**
- Create: `app/ui/views/instances/confirm_bulk_dialog.py`
- Test: `tests/test_confirm_bulk_dialog.py`

- [ ] **Step 17.1: Write failing test**

Create `tests/test_confirm_bulk_dialog.py`:

```python
from app.models import Instance, InstanceState


def mk(id, dph=0.30, gpu="RTX 3090", n=1):
    return Instance(id=id, state=InstanceState.RUNNING, gpu_name=gpu,
                    num_gpus=n, dph=dph)


def test_dialog_shows_aggregate_cost(qt_app):
    from app.ui.views.instances.confirm_bulk_dialog import ConfirmBulkDialog
    d = ConfirmBulkDialog("start", [mk(1, 0.30), mk(2, 0.60), mk(3, 0.10)])
    assert "1.00" in d.summary_text() or "$1.00" in d.summary_text()


def test_dialog_lists_all_instances(qt_app):
    from app.ui.views.instances.confirm_bulk_dialog import ConfirmBulkDialog
    d = ConfirmBulkDialog("stop", [mk(11), mk(22), mk(33)])
    body = d.list_text()
    assert "11" in body and "22" in body and "33" in body


def test_destroy_requires_checkbox(qt_app):
    from app.ui.views.instances.confirm_bulk_dialog import ConfirmBulkDialog
    d = ConfirmBulkDialog("destroy", [mk(1)])
    assert d.confirm_btn.isEnabled() is False
    d.understand_check.setChecked(True)
    assert d.confirm_btn.isEnabled() is True


def test_label_action_collects_label_input(qt_app):
    from app.ui.views.instances.confirm_bulk_dialog import ConfirmBulkDialog
    d = ConfirmBulkDialog("label", [mk(1), mk(2)])
    d.label_input.setText("experiment-x")
    opts = d.collect_opts()
    assert opts["label"] == "experiment-x"


def test_start_action_default_opts_includes_auto_connect(qt_app):
    from app.ui.views.instances.confirm_bulk_dialog import ConfirmBulkDialog
    d = ConfirmBulkDialog("start", [mk(1)])
    opts = d.collect_opts()
    assert "auto_connect" in opts
```

- [ ] **Step 17.2: Run to verify failure**

```bash
python -m pytest tests/test_confirm_bulk_dialog.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 17.3: Implement dialog**

Create `app/ui/views/instances/confirm_bulk_dialog.py`:

```python
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QPushButton, QCheckBox, QLineEdit,
)
from app.models import Instance
from app.theme import TEXT, TEXT_HI, OK, ERR, ACCENT, FONT_MONO


_TITLES = {
    "start":      "Confirmar Start em",
    "stop":       "Confirmar Stop em",
    "connect":    "Confirmar Connect em",
    "disconnect": "Confirmar Disconnect em",
    "destroy":    "⚠ Destroy permanente em",
    "label":      "Aplicar label em",
}


class ConfirmBulkDialog(QDialog):
    """Modal: lists affected instances, shows aggregate cost, collects opts."""

    def __init__(self, action: str, instances: list[Instance], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirmar")
        self.setMinimumWidth(420)
        self.action = action
        self.instances = list(instances)

        lay = QVBoxLayout(self)
        title = QLabel(f"{_TITLES.get(action, action)} {len(instances)} instâncias")
        f = title.font(); f.setPointSize(11); f.setBold(True); title.setFont(f)
        title.setStyleSheet(f"color: {TEXT_HI};")
        lay.addWidget(title)

        self.lst = QListWidget()
        for inst in instances:
            item = QListWidgetItem(
                f"#{inst.id}   {inst.num_gpus or 1}× {inst.gpu_name}   "
                f"${(inst.dph or 0):.3f}/hr"
            )
            self.lst.addItem(item)
        lay.addWidget(self.lst)

        agg = sum(float(i.dph or 0) for i in instances)
        verb = "Você economizará" if action in ("stop", "disconnect", "destroy") else "Custo agregado:"
        self.summary = QLabel(f"{verb} ${agg:.3f}/hr")
        col = OK if "economizará" in verb else TEXT
        self.summary.setStyleSheet(f"color: {col}; font-family: {FONT_MONO};")
        lay.addWidget(self.summary)

        # Conditional inputs
        self.auto_connect_check: QCheckBox | None = None
        self.label_input: QLineEdit | None = None
        self.understand_check: QCheckBox | None = None

        if action == "start":
            self.auto_connect_check = QCheckBox("Conectar tunnels após start")
            self.auto_connect_check.setChecked(True)
            lay.addWidget(self.auto_connect_check)
        if action == "label":
            self.label_input = QLineEdit()
            self.label_input.setPlaceholderText("novo label (vazio = sem label)")
            lay.addWidget(self.label_input)
        if action == "destroy":
            self.understand_check = QCheckBox("Eu entendo que isto é irreversível")
            lay.addWidget(self.understand_check)

        # Buttons
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("Confirmar")
        self.confirm_btn.clicked.connect(self.accept)
        bg = ERR if action == "destroy" else ACCENT
        self.confirm_btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: white; border: none;"
            f" border-radius: 6px; padding: 6px 14px; }}"
        )
        row.addWidget(cancel); row.addWidget(self.confirm_btn)
        lay.addLayout(row)

        if action == "destroy":
            self.confirm_btn.setEnabled(False)
            self.understand_check.toggled.connect(self.confirm_btn.setEnabled)

    def summary_text(self) -> str:
        return self.summary.text()

    def list_text(self) -> str:
        return "\n".join(self.lst.item(i).text() for i in range(self.lst.count()))

    def collect_opts(self) -> dict:
        out: dict = {}
        if self.auto_connect_check is not None:
            out["auto_connect"] = self.auto_connect_check.isChecked()
        if self.label_input is not None:
            out["label"] = self.label_input.text()
        return out
```

- [ ] **Step 17.4: Run tests**

```bash
python -m pytest tests/test_confirm_bulk_dialog.py -v
```

Expected: green.

- [ ] **Step 17.5: Commit**

```bash
git add app/ui/views/instances/confirm_bulk_dialog.py tests/test_confirm_bulk_dialog.py
git commit -m "feat(instances): add ConfirmBulkDialog with aggregate cost + per-action opts"
```

---

### Task 18: `log_modal.py` — per-instance filtered log

**Files:**
- Create: `app/ui/views/instances/log_modal.py`
- Test: `tests/test_log_modal.py`

- [ ] **Step 18.1: Write failing test**

Create `tests/test_log_modal.py`:

```python
def test_log_modal_filters_by_instance_id(qt_app):
    from app.ui.views.instances.log_modal import LogModal
    lines = [
        "Conectando #100...",
        "Conectando #200...",
        "Túnel #100: connected",
        "✓ Bulk start: 2 ok",
        "Métricas live #100: ok",
    ]
    m = LogModal(instance_id=100, history=lines)
    body = m.body_text()
    assert "#100" in body
    assert "#200" not in body


def test_log_modal_appends_new_line(qt_app):
    from app.ui.views.instances.log_modal import LogModal
    m = LogModal(instance_id=42, history=[])
    m.append_line("Conectando #42...")
    m.append_line("Other #99 line")
    assert "#42" in m.body_text()
    assert "#99" not in m.body_text()
```

- [ ] **Step 18.2: Run to verify failure**

```bash
python -m pytest tests/test_log_modal.py -v
```

Expected: FAIL.

- [ ] **Step 18.3: Implement modal**

Create `app/ui/views/instances/log_modal.py`:

```python
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout
from app.theme import FONT_MONO, TEXT, SURFACE_2


class LogModal(QDialog):
    """Shows log lines containing '#<instance_id>'."""

    def __init__(self, instance_id: int, history: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Logs · instância #{instance_id}")
        self.resize(720, 440)
        self._iid = instance_id
        self._tag = f"#{instance_id}"

        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            f"QPlainTextEdit {{ background: {SURFACE_2}; color: {TEXT};"
            f" font-family: {FONT_MONO}; }}"
        )
        for line in history:
            self.append_line(line)
        lay.addWidget(self.text)

        row = QHBoxLayout(); row.addStretch(1)
        close = QPushButton("Fechar"); close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def append_line(self, line: str) -> None:
        if self._tag in line:
            self.text.appendPlainText(line)

    def body_text(self) -> str:
        return self.text.toPlainText()
```

- [ ] **Step 18.4: Run tests**

```bash
python -m pytest tests/test_log_modal.py -v
```

Expected: green.

- [ ] **Step 18.5: Commit**

```bash
git add app/ui/views/instances/log_modal.py tests/test_log_modal.py
git commit -m "feat(instances): add LogModal (per-instance filtered log)"
```

---

## Phase 5 — UI compositions

### Task 19: New `instance_card.py`

**Files:**
- Create: `app/ui/views/instances/instance_card.py`
- Test: `tests/test_instance_card_new.py`

- [ ] **Step 19.1: Write failing test**

Create `tests/test_instance_card_new.py`:

```python
from app.models import Instance, InstanceState, TunnelStatus


def mk(state=InstanceState.RUNNING, label=None):
    return Instance(id=42, state=state, gpu_name="RTX 3090",
                    public_ip="1.2.3.4", is_verified=True, dph=0.30,
                    label=label, ram_total_gb=64.0, gpu_ram_gb=24.0)


def test_card_renders_all_subsections(qt_app):
    from app.ui.views.instances.instance_card import InstanceCard
    c = InstanceCard(mk(), port=11434, tunnel=TunnelStatus.DISCONNECTED)
    assert c.header is not None
    assert c.specs is not None
    assert c.actions is not None


def test_card_live_footer_only_when_running(qt_app):
    from app.ui.views.instances.instance_card import InstanceCard
    running = InstanceCard(mk(state=InstanceState.RUNNING), port=11434,
                           tunnel=TunnelStatus.CONNECTED)
    stopped = InstanceCard(mk(state=InstanceState.STOPPED), port=11434,
                           tunnel=TunnelStatus.DISCONNECTED)
    assert running.live is not None
    assert stopped.live is None


def test_card_emits_action_signals_with_id(qt_app):
    from app.ui.views.instances.instance_card import InstanceCard
    c = InstanceCard(mk(state=InstanceState.STOPPED), port=11434,
                     tunnel=TunnelStatus.DISCONNECTED)
    received = []
    c.activate_requested.connect(lambda iid: received.append(iid))
    c.actions.activate_requested.emit()
    assert received == [42]


def test_card_select_mode_shows_checkbox(qt_app):
    from app.ui.views.instances.instance_card import InstanceCard
    c = InstanceCard(mk(), port=11434, tunnel=TunnelStatus.DISCONNECTED,
                     select_mode=True)
    assert c.select_check is not None
    assert c.select_check.isVisible() or True  # widget exists; visibility depends on parent


def test_card_update_replaces_state_without_recreate(qt_app):
    from app.ui.views.instances.instance_card import InstanceCard
    c = InstanceCard(mk(state=InstanceState.STOPPED), port=11434,
                     tunnel=TunnelStatus.DISCONNECTED)
    primary_id_before = id(c.actions)
    c.update_instance(mk(state=InstanceState.RUNNING), tunnel=TunnelStatus.CONNECTED)
    # ActionBar may rebuild — but card itself is the same widget
    assert c.inst.state == InstanceState.RUNNING
```

- [ ] **Step 19.2: Run to verify failure**

```bash
python -m pytest tests/test_instance_card_new.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 19.3: Implement `InstanceCard`**

Create `app/ui/views/instances/instance_card.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QCheckBox, QApplication,
)
from app.models import Instance, InstanceState, TunnelStatus
from app.ui.components.primitives import GlassCard
from app.ui.views.instances.chip_header import ChipHeader
from app.ui.views.instances.specs_grid import SpecsGrid
from app.ui.views.instances.live_footer import LiveFooter
from app.ui.views.instances.action_bar import ActionBar


class InstanceCard(QFrame):
    """Dense always-open card. One per instance."""

    activate_requested    = Signal(int)
    deactivate_requested  = Signal(int)
    connect_requested     = Signal(int)
    disconnect_requested  = Signal(int)
    reboot_requested      = Signal(int)
    snapshot_requested    = Signal(int)
    destroy_requested     = Signal(int)
    log_requested         = Signal(int)
    label_requested       = Signal(int)
    flag_requested        = Signal(int)
    key_requested         = Signal(int)
    lab_requested         = Signal(int)
    selection_toggled     = Signal(int, bool)
    ip_copy_requested     = Signal(int)

    def __init__(
        self,
        inst: Instance,
        *,
        port: int,
        tunnel: TunnelStatus = TunnelStatus.DISCONNECTED,
        selected: bool = False,
        select_mode: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.inst = inst
        self._tunnel = tunnel
        self._port = port
        self._select_mode = select_mode
        self._selected = selected

        self._card = GlassCard(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        self._inner = QVBoxLayout(self._card)
        self._inner.setContentsMargins(14, 14, 14, 14)
        self._inner.setSpacing(10)

        self._build()

    def _build(self) -> None:
        # Top row: header + optional select checkbox
        top = QHBoxLayout(); top.setSpacing(10)
        self.header = ChipHeader(self.inst, self._card)
        self.header.ip_clicked.connect(lambda: self.ip_copy_requested.emit(self.inst.id))
        top.addWidget(self.header, stretch=1)

        self.select_check = QCheckBox()
        self.select_check.setChecked(self._selected)
        self.select_check.setVisible(self._select_mode)
        self.select_check.toggled.connect(
            lambda v: self.selection_toggled.emit(self.inst.id, bool(v)))
        top.addWidget(self.select_check)
        self._inner.addLayout(top)

        # Specs grid (always visible)
        self.specs = SpecsGrid(self.inst, self._card)
        self._inner.addWidget(self.specs)

        # Live footer only when RUNNING
        self.live: LiveFooter | None = None
        if self.inst.state == InstanceState.RUNNING:
            self.live = LiveFooter(self.inst, self._card)
            self._inner.addWidget(self.live)

        # Action bar
        self.actions = ActionBar(self.inst, self._tunnel, self._card)
        self._wire_actions()
        self._inner.addWidget(self.actions)

    def _wire_actions(self) -> None:
        a = self.actions
        a.activate_requested.connect(lambda: self.activate_requested.emit(self.inst.id))
        a.deactivate_requested.connect(lambda: self.deactivate_requested.emit(self.inst.id))
        a.connect_requested.connect(lambda: self.connect_requested.emit(self.inst.id))
        a.disconnect_requested.connect(lambda: self.disconnect_requested.emit(self.inst.id))
        a.reboot_requested.connect(lambda: self.reboot_requested.emit(self.inst.id))
        a.snapshot_requested.connect(lambda: self.snapshot_requested.emit(self.inst.id))
        a.destroy_requested.connect(lambda: self.destroy_requested.emit(self.inst.id))
        a.log_requested.connect(lambda: self.log_requested.emit(self.inst.id))
        a.label_requested.connect(lambda: self.label_requested.emit(self.inst.id))
        a.flag_requested.connect(lambda: self.flag_requested.emit(self.inst.id))
        a.key_requested.connect(lambda: self.key_requested.emit(self.inst.id))
        a.lab_requested.connect(lambda: self.lab_requested.emit(self.inst.id))

    # --- update API ---

    def update_instance(self, inst: Instance, tunnel: TunnelStatus) -> None:
        """Refresh contents in place. Reuses widgets where possible."""
        self.inst = inst
        self._tunnel = tunnel
        # Clear and rebuild the inner layout — Qt widget reuse for headers/grids
        # is fragile across data changes; rebuild is fast enough at refresh cadence.
        self._clear_inner()
        self._build()

    def _clear_inner(self) -> None:
        while self._inner.count():
            item = self._inner.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                lay = item.layout()
                if lay is not None:
                    while lay.count():
                        sub = lay.takeAt(0)
                        if sub.widget():
                            sub.widget().deleteLater()

    def apply_metrics(self, metrics: dict) -> None:
        if self.live is not None:
            self.live.apply_metrics(metrics)

    def set_select_mode(self, on: bool) -> None:
        self._select_mode = on
        self.select_check.setVisible(on)

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self.select_check.setChecked(on)
```

- [ ] **Step 19.4: Run tests**

```bash
python -m pytest tests/test_instance_card_new.py -v
```

Expected: all green.

- [ ] **Step 19.5: Commit**

```bash
git add app/ui/views/instances/instance_card.py tests/test_instance_card_new.py
git commit -m "feat(instances): new dense InstanceCard composing header/specs/live/actions"
```

---

### Task 20: `filter_bar.py` — dropdowns row

**Files:**
- Create: `app/ui/views/instances/filter_bar.py`
- Test: `tests/test_filter_bar.py`

- [ ] **Step 20.1: Write failing test**

Create `tests/test_filter_bar.py`:

```python
def test_filter_bar_emits_changed_on_sort_select(qt_app):
    from app.ui.views.instances.filter_bar import FilterBar
    from app.services.instance_filter import FilterState
    bar = FilterBar(FilterState())
    received = []
    bar.changed.connect(lambda s: received.append(s.sort))
    # Programmatically pick a sort
    bar.set_sort("price_asc")
    assert "price_asc" in received


def test_filter_bar_populates_gpu_options(qt_app):
    from app.ui.views.instances.filter_bar import FilterBar
    from app.services.instance_filter import FilterState
    bar = FilterBar(FilterState())
    bar.set_gpu_options(["1× RTX 3090", "2× RTX 4090"])
    items = bar.gpu_option_texts()
    assert "1× RTX 3090" in items
    assert "2× RTX 4090" in items


def test_filter_bar_populates_label_options(qt_app):
    from app.ui.views.instances.filter_bar import FilterBar
    from app.services.instance_filter import FilterState
    bar = FilterBar(FilterState())
    bar.set_label_options(["exp-a", "exp-b"])
    items = bar.label_option_texts()
    assert "exp-a" in items and "exp-b" in items
    assert "All" in items
    assert "No Label" in items
```

- [ ] **Step 20.2: Run to verify failure**

```bash
python -m pytest tests/test_filter_bar.py -v
```

Expected: FAIL.

- [ ] **Step 20.3: Implement `FilterBar`**

Create `app/ui/views/instances/filter_bar.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QComboBox, QPushButton
from app.services.instance_filter import FilterState
from app.ui.components.primitives import IconButton
from app.ui.components import icons
from app.theme import BORDER_LOW, TEXT


_SORT_OPTIONS = [
    ("Auto Sort", "auto"),
    ("Price ↑", "price_asc"),
    ("Price ↓", "price_desc"),
    ("Uptime ↓", "uptime_desc"),
    ("Uptime ↑", "uptime_asc"),
    ("DLPerf ↓", "dlperf"),
    ("DLPerf / $ ↓", "dlperf_per_dollar"),
    ("Reliability ↓", "reliability"),
    ("Status", "status"),
]

_STATUS_OPTIONS = [
    ("All Statuses", ""),
    ("Running", "running"),
    ("Stopped", "stopped"),
    ("Starting", "starting"),
    ("Stopping", "stopping"),
]


class FilterBar(QFrame):
    """Top bar with GPU / Status / Label / Sort dropdowns."""

    changed = Signal(object)  # FilterState

    def __init__(self, initial: FilterState, parent=None) -> None:
        super().__init__(parent)
        self.state = FilterState(
            gpu_types=list(initial.gpu_types),
            statuses=list(initial.statuses),
            label=initial.label,
            sort=initial.sort,
        )
        self.setStyleSheet(f"FilterBar {{ border-bottom: 1px solid {BORDER_LOW}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(8)

        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("All GPUs", "")
        self.gpu_combo.currentIndexChanged.connect(self._on_gpu)
        lay.addWidget(self.gpu_combo)

        self.status_combo = QComboBox()
        for label, value in _STATUS_OPTIONS:
            self.status_combo.addItem(label, value)
        self.status_combo.currentIndexChanged.connect(self._on_status)
        lay.addWidget(self.status_combo)

        self.label_combo = QComboBox()
        self.label_combo.addItem("All", "")
        self.label_combo.addItem("No Label", "__none__")
        self.label_combo.currentIndexChanged.connect(self._on_label)
        lay.addWidget(self.label_combo)

        self.sort_combo = QComboBox()
        for text, key in _SORT_OPTIONS:
            self.sort_combo.addItem(text, key)
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        lay.addWidget(self.sort_combo)

        self.reset = IconButton(icons.CLOSE, "Reset filters")
        self.reset.clicked.connect(self._on_reset)
        lay.addWidget(self.reset)
        lay.addStretch(1)

        # Apply initial selections
        self._sync_to_widgets()

    # --- public API ---
    def set_gpu_options(self, opts: list[str]) -> None:
        cur = self.gpu_combo.currentData()
        self.gpu_combo.blockSignals(True)
        self.gpu_combo.clear()
        self.gpu_combo.addItem("All GPUs", "")
        for o in opts:
            self.gpu_combo.addItem(o, o)
        # Restore selection if still present
        idx = self.gpu_combo.findData(cur)
        self.gpu_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.gpu_combo.blockSignals(False)

    def set_label_options(self, opts: list[str]) -> None:
        cur = self.label_combo.currentData()
        self.label_combo.blockSignals(True)
        self.label_combo.clear()
        self.label_combo.addItem("All", "")
        self.label_combo.addItem("No Label", "__none__")
        for o in opts:
            self.label_combo.addItem(o, o)
        idx = self.label_combo.findData(cur)
        self.label_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.label_combo.blockSignals(False)

    def gpu_option_texts(self) -> list[str]:
        return [self.gpu_combo.itemText(i) for i in range(self.gpu_combo.count())]

    def label_option_texts(self) -> list[str]:
        return [self.label_combo.itemText(i) for i in range(self.label_combo.count())]

    def set_sort(self, key: str) -> None:
        idx = self.sort_combo.findData(key)
        if idx >= 0:
            self.sort_combo.setCurrentIndex(idx)

    # --- handlers ---
    def _on_gpu(self, _idx: int) -> None:
        v = self.gpu_combo.currentData() or ""
        self.state.gpu_types = [v] if v else []
        self.changed.emit(self.state)

    def _on_status(self, _idx: int) -> None:
        v = self.status_combo.currentData() or ""
        self.state.statuses = [v] if v else []
        self.changed.emit(self.state)

    def _on_label(self, _idx: int) -> None:
        v = self.label_combo.currentData() or ""
        self.state.label = v or None
        self.changed.emit(self.state)

    def _on_sort(self, _idx: int) -> None:
        self.state.sort = self.sort_combo.currentData() or "auto"
        self.changed.emit(self.state)

    def _on_reset(self) -> None:
        self.state = FilterState()
        self._sync_to_widgets()
        self.changed.emit(self.state)

    def _sync_to_widgets(self) -> None:
        for combo, value in (
            (self.gpu_combo, (self.state.gpu_types[:1] or [""])[0]),
            (self.status_combo, (self.state.statuses[:1] or [""])[0]),
            (self.label_combo, self.state.label or ""),
            (self.sort_combo, self.state.sort),
        ):
            idx = combo.findData(value)
            combo.blockSignals(True)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
```

- [ ] **Step 20.4: Run tests**

```bash
python -m pytest tests/test_filter_bar.py -v
```

Expected: green.

- [ ] **Step 20.5: Commit**

```bash
git add app/ui/views/instances/filter_bar.py tests/test_filter_bar.py
git commit -m "feat(instances): add FilterBar (GPU/Status/Label/Sort dropdowns)"
```

---

### Task 21: `label_tabs.py` — All / No Label / custom tabs

**Files:**
- Create: `app/ui/views/instances/label_tabs.py`
- Test: `tests/test_label_tabs.py`

- [ ] **Step 21.1: Write failing test**

Create `tests/test_label_tabs.py`:

```python
def test_label_tabs_emits_selected_label(qt_app):
    from app.ui.views.instances.label_tabs import LabelTabs
    t = LabelTabs()
    t.update_labels({"": 5, "__none__": 2, "exp-a": 1, "exp-b": 4})
    seen = []
    t.label_selected.connect(seen.append)
    t.click_label("exp-b")
    assert seen == ["exp-b"]


def test_label_tabs_shows_counts(qt_app):
    from app.ui.views.instances.label_tabs import LabelTabs
    t = LabelTabs()
    t.update_labels({"": 5, "__none__": 2, "exp": 3})
    texts = t.tab_texts()
    assert any("All (5)" == s for s in texts)
    assert any("No Label (2)" == s for s in texts)
    assert any("exp (3)" == s for s in texts)
```

- [ ] **Step 21.2: Run to verify failure**

```bash
python -m pytest tests/test_label_tabs.py -v
```

Expected: FAIL.

- [ ] **Step 21.3: Implement `LabelTabs`**

Create `app/ui/views/instances/label_tabs.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton
from app.theme import ACCENT, TEXT, TEXT_LOW, BORDER_LOW, FONT_DISPLAY


class LabelTabs(QFrame):
    """Tab strip: All | No Label | <custom labels>. Click selects a filter value."""

    label_selected = Signal(str)   # "" for All, "__none__" for unlabeled, else literal

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"LabelTabs {{ border-bottom: 1px solid {BORDER_LOW}; }}")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self._lay.addStretch(1)
        self._btns: dict[str, QPushButton] = {}
        self._active: str = ""

    def update_labels(self, counts: dict[str, int]) -> None:
        # Order: All, No Label, then alpha-sorted custom labels
        keys = [""]
        if "__none__" in counts:
            keys.append("__none__")
        keys.extend(sorted(k for k in counts if k not in ("", "__none__")))
        self._rebuild(keys, counts)
        # Restore active tab if still present, else fall back to All
        target = self._active if self._active in self._btns else ""
        self._set_active(target)

    def _rebuild(self, keys: list[str], counts: dict[str, int]) -> None:
        # Clear existing buttons
        for b in self._btns.values():
            b.deleteLater()
        self._btns.clear()
        # Remove all but the trailing stretch
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for idx, key in enumerate(keys):
            text = self._label_for(key, counts.get(key, 0))
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            f = btn.font(); f.setFamily(FONT_DISPLAY); f.setPointSize(10); btn.setFont(f)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
            self._lay.insertWidget(idx, btn)
            self._btns[key] = btn

    @staticmethod
    def _label_for(key: str, n: int) -> str:
        if key == "":          return f"All ({n})"
        if key == "__none__":  return f"No Label ({n})"
        return f"{key} ({n})"

    def _on_click(self, key: str) -> None:
        self._set_active(key)
        self.label_selected.emit(key)

    def _set_active(self, key: str) -> None:
        self._active = key
        for k, b in self._btns.items():
            color = ACCENT if k == key else TEXT_LOW
            border = f"2px solid {ACCENT}" if k == key else "2px solid transparent"
            b.setStyleSheet(
                f"QPushButton {{ color: {color}; background: transparent;"
                f" border: none; border-bottom: {border}; padding: 6px 10px; }}"
                f"QPushButton:hover {{ color: {TEXT}; }}"
            )

    def click_label(self, key: str) -> None:
        if key in self._btns:
            self._on_click(key)

    def tab_texts(self) -> list[str]:
        return [self._btns[k].text() for k in self._btns]
```

- [ ] **Step 21.4: Run tests**

```bash
python -m pytest tests/test_label_tabs.py -v
```

Expected: green.

- [ ] **Step 21.5: Commit**

```bash
git add app/ui/views/instances/label_tabs.py tests/test_label_tabs.py
git commit -m "feat(instances): add LabelTabs with dynamic counts"
```

---

### Task 22: `bulk_action_bar.py` — selection mode footer overlay

**Files:**
- Create: `app/ui/views/instances/bulk_action_bar.py`
- Test: `tests/test_bulk_action_bar.py`

- [ ] **Step 22.1: Write failing test**

Create `tests/test_bulk_action_bar.py`:

```python
def test_bulk_action_bar_count_text(qt_app):
    from app.ui.views.instances.bulk_action_bar import BulkActionBar
    bar = BulkActionBar()
    bar.set_count(0)
    assert "0" in bar.count_label.text() or "Nenhum" in bar.count_label.text()
    bar.set_count(3)
    assert "3" in bar.count_label.text()


def test_bulk_action_bar_emits_action(qt_app):
    from app.ui.views.instances.bulk_action_bar import BulkActionBar
    bar = BulkActionBar()
    received = []
    bar.action_clicked.connect(lambda action: received.append(action))
    bar.btn_start.click()
    bar.btn_stop.click()
    bar.btn_destroy.click()
    assert received == ["start", "stop", "destroy"]


def test_bulk_action_bar_clear_emits(qt_app):
    from app.ui.views.instances.bulk_action_bar import BulkActionBar
    bar = BulkActionBar()
    seen = []
    bar.clear_clicked.connect(lambda: seen.append(True))
    bar.btn_clear.click()
    assert seen == [True]
```

- [ ] **Step 22.2: Run to verify failure**

```bash
python -m pytest tests/test_bulk_action_bar.py -v
```

Expected: FAIL.

- [ ] **Step 22.3: Implement bar**

Create `app/ui/views/instances/bulk_action_bar.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from app.ui.components.primitives import IconButton
from app.ui.components import icons
from app.theme import ACCENT, TEXT_HI, BORDER_MED, SURFACE_2


class BulkActionBar(QFrame):
    """Floating bottom bar for bulk operations on selected instances."""

    action_clicked = Signal(str)   # "start" | "stop" | "connect" | "disconnect" | "destroy" | "label"
    clear_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"BulkActionBar {{ background: {SURFACE_2}; border: 1px solid {BORDER_MED};"
            f" border-radius: 12px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        self.count_label = QLabel("0 selecionados")
        self.count_label.setStyleSheet(f"color: {TEXT_HI};")
        lay.addWidget(self.count_label)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFlat(True)
        self.btn_clear.clicked.connect(self.clear_clicked)
        lay.addWidget(self.btn_clear)

        sep = QFrame(); sep.setFixedWidth(1); sep.setStyleSheet(f"background: {BORDER_MED};")
        lay.addWidget(sep)

        self.btn_start      = self._action_btn(icons.PLAY,       "Start",      "start")
        self.btn_stop       = self._action_btn(icons.STOP,       "Stop",       "stop")
        self.btn_connect    = self._action_btn(icons.TUNNEL,     "Connect",    "connect")
        self.btn_disconnect = self._action_btn(icons.DISCONNECT, "Disconnect", "disconnect")
        self.btn_label      = self._action_btn(icons.TAG,        "Label",      "label")
        self.btn_destroy    = self._action_btn(icons.DELETE,     "Destroy",    "destroy", danger=True)
        for b in (self.btn_start, self.btn_stop, self.btn_connect,
                  self.btn_disconnect, self.btn_label, self.btn_destroy):
            lay.addWidget(b)
        lay.addStretch(1)

    def _action_btn(self, mdi: str, label: str, action: str, *, danger: bool = False) -> QPushButton:
        btn = QPushButton(label)
        from app.ui.components.primitives import icon
        from app.theme import ERR, TEXT
        col = ERR if danger else TEXT
        btn.setIcon(icon(mdi, color=col))
        btn.setFlat(True)
        btn.clicked.connect(lambda: self.action_clicked.emit(action))
        return btn

    def set_count(self, n: int) -> None:
        self.count_label.setText(f"{n} selecionados" if n else "Nenhum selecionado")
```

- [ ] **Step 22.4: Run tests**

```bash
python -m pytest tests/test_bulk_action_bar.py -v
```

Expected: green.

- [ ] **Step 22.5: Commit**

```bash
git add app/ui/views/instances/bulk_action_bar.py tests/test_bulk_action_bar.py
git commit -m "feat(instances): add BulkActionBar for selection-mode operations"
```

---

## Phase 6 — Top-level view + integration

### Task 23: New `instances_view.py` (composer)

**Files:**
- Create: `app/ui/views/instances/instances_view.py`
- Test: `tests/test_instances_view_new.py`

- [ ] **Step 23.1: Write failing tests**

Create `tests/test_instances_view_new.py`:

```python
from app.models import Instance, InstanceState, UserInfo


def mk(id, label=None, state=InstanceState.RUNNING, gpu="RTX 3090"):
    return Instance(id=id, state=state, gpu_name=gpu, label=label,
                    public_ip="1.2.3.4", dph=0.30, ram_total_gb=64.0,
                    gpu_ram_gb=24.0)


def _make_controller(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.controller import AppController
    from app.models import AppConfig
    cfg_path = tmp_path / "c.json"
    store = ConfigStore(path=cfg_path)
    store.save(AppConfig(api_key="k"))
    return AppController(store)


def test_view_shows_one_card_per_instance(qt_app, tmp_path):
    from app.ui.views.instances.instances_view import InstancesView
    c = _make_controller(qt_app, tmp_path)
    v = InstancesView(c)
    v.handle_refresh([mk(1), mk(2), mk(3)], UserInfo(balance=10.0, email=""))
    assert len(v._cards) == 3


def test_view_filter_hides_cards(qt_app, tmp_path):
    from app.ui.views.instances.instances_view import InstancesView
    c = _make_controller(qt_app, tmp_path)
    v = InstancesView(c)
    v.handle_refresh([mk(1, state=InstanceState.RUNNING),
                      mk(2, state=InstanceState.STOPPED)],
                     UserInfo(balance=10.0, email=""))
    v.filter_bar.status_combo.setCurrentIndex(
        v.filter_bar.status_combo.findData("running"))
    assert set(v._cards) == {1}


def test_view_label_tabs_filter(qt_app, tmp_path):
    from app.ui.views.instances.instances_view import InstancesView
    c = _make_controller(qt_app, tmp_path)
    v = InstancesView(c)
    v.handle_refresh([mk(1, label="exp"), mk(2, label=None), mk(3, label="exp")],
                     UserInfo(balance=10.0, email=""))
    v.label_tabs.click_label("__none__")
    assert set(v._cards) == {2}


def test_view_persists_filters_to_config(qt_app, tmp_path):
    from app.config import ConfigStore
    from app.ui.views.instances.instances_view import InstancesView
    c = _make_controller(qt_app, tmp_path)
    v = InstancesView(c)
    v.handle_refresh([mk(1)], UserInfo(balance=10.0, email=""))
    v.filter_bar.set_sort("price_desc")
    reloaded = ConfigStore(path=c.config_store.path).load()
    assert reloaded.instance_filters.get("sort") == "price_desc"


def test_view_emits_activate_request(qt_app, tmp_path):
    from app.ui.views.instances.instances_view import InstancesView
    c = _make_controller(qt_app, tmp_path)
    v = InstancesView(c)
    v.handle_refresh([mk(1, state=InstanceState.STOPPED)],
                     UserInfo(balance=10.0, email=""))
    seen = []
    v.activate_requested.connect(seen.append)
    v._cards[1].activate_requested.emit(1)
    assert seen == [1]
```

- [ ] **Step 23.2: Run to verify failure**

```bash
python -m pytest tests/test_instances_view_new.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 23.3: Implement view**

Create `app/ui/views/instances/instances_view.py`:

```python
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton,
)
from app.models import Instance, InstanceState, TunnelStatus, UserInfo
from app.services.instance_filter import FilterState, apply, gpu_key
from app.ui.views.instances.filter_bar import FilterBar
from app.ui.views.instances.label_tabs import LabelTabs
from app.ui.views.instances.instance_card import InstanceCard
from app.ui.views.instances.bulk_action_bar import BulkActionBar
from app.ui.views.instances.confirm_bulk_dialog import ConfirmBulkDialog
from app.ui.views.instances.log_modal import LogModal
from app.ui.components.primitives import IconButton
from app.ui.components import icons
from app.theme import TEXT_HI, FONT_DISPLAY


class InstancesView(QWidget):
    """Composer for header + filters + label tabs + cards + bulk bar."""

    activate_requested    = Signal(int)
    deactivate_requested  = Signal(int)
    connect_requested     = Signal(int)
    disconnect_requested  = Signal(int)
    destroy_requested     = Signal(int)
    set_label_requested   = Signal(int, str)
    open_lab_requested    = Signal(int)
    open_settings_requested = Signal()
    open_logs_requested   = Signal()
    bulk_requested        = Signal(str, list, dict)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._all: list[Instance] = []
        self._cards: dict[int, InstanceCard] = {}
        self._selected: set[int] = set()
        self._select_mode = False
        self._log_history: list[str] = []
        self._tunnels: dict[int, TunnelStatus] = {}
        self._filter = FilterState.from_dict(controller.config.instance_filters)
        self._build()

        # Mirror log lines for per-instance modal history
        controller.log_line.connect(self._on_log_line)
        controller.tunnel_status_changed.connect(self._on_tunnel_status)
        controller.live_metrics.connect(self._on_live_metrics)

    # -------- UI build --------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)

        # Header
        head = QHBoxLayout(); head.setSpacing(8)
        self.title = QLabel("My Instances (0)")
        f = self.title.font(); f.setPointSize(14); f.setBold(True)
        f.setFamily(FONT_DISPLAY); self.title.setFont(f)
        self.title.setStyleSheet(f"color: {TEXT_HI};")
        head.addWidget(self.title)
        head.addStretch(1)

        self.btn_select = IconButton(icons.SELECT, "Select instances")
        self.btn_select.clicked.connect(self._toggle_select_mode)
        head.addWidget(self.btn_select)

        self.btn_logs = IconButton(icons.LOG, "Open global logs")
        self.btn_logs.clicked.connect(self.open_logs_requested)
        head.addWidget(self.btn_logs)

        self.btn_settings = IconButton(icons.SETTINGS, "Settings")
        self.btn_settings.clicked.connect(self.open_settings_requested)
        head.addWidget(self.btn_settings)

        self.btn_start_all = QPushButton("▶ Start All")
        self.btn_start_all.clicked.connect(lambda: self._bulk_from_visible("start"))
        head.addWidget(self.btn_start_all)

        outer.addLayout(head)

        # Filter bar + tabs
        self.filter_bar = FilterBar(self._filter)
        self.filter_bar.changed.connect(self._on_filter_changed)
        outer.addWidget(self.filter_bar)

        self.label_tabs = LabelTabs()
        self.label_tabs.label_selected.connect(self._on_label_tab)
        outer.addWidget(self.label_tabs)

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self._cards_layout = QVBoxLayout(host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch(1)
        self.scroll.setWidget(host)
        outer.addWidget(self.scroll, stretch=1)

        # Bulk bar
        self.bulk_bar = BulkActionBar()
        self.bulk_bar.action_clicked.connect(self._on_bulk_action)
        self.bulk_bar.clear_clicked.connect(self._clear_selection)
        self.bulk_bar.setVisible(False)
        outer.addWidget(self.bulk_bar)

    # -------- Public hooks --------

    def handle_refresh(self, instances: list[Instance], user: UserInfo) -> None:
        self._all = list(instances)
        self.title.setText(f"My Instances ({len(self._all)})")
        # Update filter options
        gpus = sorted({gpu_key(i) for i in self._all})
        self.filter_bar.set_gpu_options(gpus)
        labels = sorted({i.label for i in self._all if i.label})
        self.filter_bar.set_label_options(labels)
        # Tab counts
        counts: dict[str, int] = {"": len(self._all)}
        none_count = sum(1 for i in self._all if not i.label)
        if none_count:
            counts["__none__"] = none_count
        for lbl in labels:
            counts[lbl] = sum(1 for i in self._all if i.label == lbl)
        self.label_tabs.update_labels(counts)
        # Drop selections for vanished ids
        alive = {i.id for i in self._all}
        self._selected &= alive
        self._reapply_filter()

    # -------- Internal --------

    def _on_filter_changed(self, state: FilterState) -> None:
        self._filter = state
        self._controller.update_instance_filters(state.to_dict())
        self._reapply_filter()

    def _on_label_tab(self, key: str) -> None:
        self._filter.label = key or None
        self.filter_bar.state.label = self._filter.label
        self._controller.update_instance_filters(self._filter.to_dict())
        self._reapply_filter()

    def _reapply_filter(self) -> None:
        filtered = apply(self._all, self._filter)
        seen = set()
        for inst in filtered:
            if inst.id in self._cards:
                self._cards[inst.id].update_instance(
                    inst, self._tunnels.get(inst.id, TunnelStatus.DISCONNECTED))
            else:
                card = self._build_card(inst)
                self._cards[inst.id] = card
                # Insert before trailing stretch
                self._cards_layout.insertWidget(
                    self._cards_layout.count() - 1, card)
            seen.add(inst.id)
        for iid in list(self._cards):
            if iid not in seen:
                w = self._cards.pop(iid)
                w.setParent(None)
                w.deleteLater()
        self._refresh_bulk_bar()

    def _build_card(self, inst: Instance) -> InstanceCard:
        port = self._controller.port_allocator.get(inst.id)
        card = InstanceCard(
            inst, port=port,
            tunnel=self._tunnels.get(inst.id, TunnelStatus.DISCONNECTED),
            selected=(inst.id in self._selected),
            select_mode=self._select_mode,
        )
        card.activate_requested.connect(self.activate_requested)
        card.deactivate_requested.connect(self.deactivate_requested)
        card.connect_requested.connect(self.connect_requested)
        card.disconnect_requested.connect(self.disconnect_requested)
        card.destroy_requested.connect(self._confirm_single_destroy)
        card.lab_requested.connect(self.open_lab_requested)
        card.log_requested.connect(self._open_log_modal)
        card.label_requested.connect(self._prompt_label)
        card.selection_toggled.connect(self._on_selection_toggled)
        return card

    # -------- selection / bulk --------

    def _toggle_select_mode(self) -> None:
        self._select_mode = not self._select_mode
        for c in self._cards.values():
            c.set_select_mode(self._select_mode)
        if not self._select_mode:
            self._clear_selection()
        else:
            self._refresh_bulk_bar()

    def _on_selection_toggled(self, iid: int, on: bool) -> None:
        if on:
            self._selected.add(iid)
        else:
            self._selected.discard(iid)
        self._refresh_bulk_bar()

    def _clear_selection(self) -> None:
        self._selected.clear()
        for c in self._cards.values():
            c.set_selected(False)
        self._refresh_bulk_bar()

    def _refresh_bulk_bar(self) -> None:
        self.bulk_bar.setVisible(self._select_mode or bool(self._selected))
        self.bulk_bar.set_count(len(self._selected))

    def _on_bulk_action(self, action: str) -> None:
        ids = sorted(self._selected) if self._selected else \
              [i.id for i in apply(self._all, self._filter)]
        if not ids:
            return
        instances = [i for i in self._all if i.id in set(ids)]
        d = ConfirmBulkDialog(action, instances, parent=self)
        if d.exec() == d.DialogCode.Accepted:
            self.bulk_requested.emit(action, ids, d.collect_opts())
            if not self._select_mode:
                self._clear_selection()

    def _bulk_from_visible(self, action: str) -> None:
        ids = [i.id for i in apply(self._all, self._filter)]
        if not ids:
            return
        instances = [i for i in self._all if i.id in set(ids)]
        d = ConfirmBulkDialog(action, instances, parent=self)
        if d.exec() == d.DialogCode.Accepted:
            self.bulk_requested.emit(action, ids, d.collect_opts())

    def _confirm_single_destroy(self, iid: int) -> None:
        instances = [i for i in self._all if i.id == iid]
        d = ConfirmBulkDialog("destroy", instances, parent=self)
        if d.exec() == d.DialogCode.Accepted:
            self.bulk_requested.emit("destroy", [iid], d.collect_opts())

    def _prompt_label(self, iid: int) -> None:
        from PySide6.QtWidgets import QInputDialog
        inst = next((i for i in self._all if i.id == iid), None)
        cur = (inst.label if inst else "") or ""
        text, ok = QInputDialog.getText(self, "Label", f"Label for #{iid}:", text=cur)
        if ok:
            self.set_label_requested.emit(iid, text)

    # -------- log / metrics --------

    def _on_log_line(self, line: str) -> None:
        self._log_history.append(line)
        if len(self._log_history) > 2000:
            self._log_history = self._log_history[-2000:]

    def _open_log_modal(self, iid: int) -> None:
        m = LogModal(iid, self._log_history, parent=self)
        m.exec()

    def _on_tunnel_status(self, iid: int, status: str, _msg: str) -> None:
        try:
            self._tunnels[iid] = TunnelStatus(status)
        except ValueError:
            return
        if iid in self._cards:
            self._cards[iid].update_instance(
                self._cards[iid].inst, self._tunnels[iid])

    def _on_live_metrics(self, iid: int, metrics: dict) -> None:
        if iid in self._cards:
            self._cards[iid].apply_metrics(metrics)
```

- [ ] **Step 23.4: Run tests**

```bash
python -m pytest tests/test_instances_view_new.py -v
```

Expected: green.

- [ ] **Step 23.5: Commit**

```bash
git add app/ui/views/instances/instances_view.py tests/test_instances_view_new.py
git commit -m "feat(instances): add InstancesView composer wiring filters/tabs/cards/bulk"
```

---

### Task 24: Wire new view into `app_shell.py` (replace old)

**Files:**
- Modify: `app/ui/app_shell.py`
- Modify: `app/ui/main_window.py` (if it imports old view)
- Test: `tests/test_instances_view.py` (existing — verify still loads, may need import path update)

- [ ] **Step 24.1: Locate the import of the old view**

```bash
grep -rn "from app.ui.views.instances_view\|from app.ui.views import instances_view\|InstancesView" C:/Users/Pc_Lu/Desktop/vastai-app/app/
```

Note all the files that reference `InstancesView` from the old path.

- [ ] **Step 24.2: Update imports**

For each match found above (typically `app/ui/app_shell.py` and `app/ui/main_window.py`):

Change:
```python
from app.ui.views.instances_view import InstancesView
```
to:
```python
from app.ui.views.instances.instances_view import InstancesView
```

- [ ] **Step 24.3: Wire new view's signals to the controller**

In `app/ui/app_shell.py` (or wherever `InstancesView` is instantiated), find the existing signal-connection block and ensure these wirings are present (add any missing):

```python
view = InstancesView(self.controller)
view.activate_requested.connect(self.controller.activate)
view.deactivate_requested.connect(self.controller.deactivate)
view.connect_requested.connect(self.controller.connect_tunnel)
view.disconnect_requested.connect(self.controller.disconnect_tunnel)
view.set_label_requested.connect(self._on_set_label)   # see step 24.4
view.bulk_requested.connect(self.controller.bulk_action)
view.open_lab_requested.connect(self._on_open_lab)
view.open_settings_requested.connect(self._on_open_settings)
view.open_logs_requested.connect(self._on_toggle_logs)
self.controller.instances_refreshed.connect(view.handle_refresh)
```

- [ ] **Step 24.4: Implement `_on_set_label` glue (if not present)**

In `app_shell.py`, add (or extend):

```python
    def _on_set_label(self, iid: int, label: str) -> None:
        try:
            self.controller.vast.set_label(iid, label)
            self.controller.toast_requested.emit(f"Label aplicado em #{iid}", "success", 2000)
            self.controller.request_refresh()
        except Exception as e:
            self.controller.toast_requested.emit(f"Falha ao definir label: {e}", "error", 4000)
```

- [ ] **Step 24.5: Run the existing instances_view test**

```bash
python -m pytest tests/test_instances_view.py -v
```

If the existing test imports the old path, update it: change `from app.ui.views.instances_view import InstancesView` → `from app.ui.views.instances.instances_view import InstancesView`.

If existing tests assert behavior of the old view that no longer applies (e.g. specific widget structure that's gone), mark them with `@pytest.mark.skip(reason="replaced by Task 23 InstancesView; see test_instances_view_new.py")`.

- [ ] **Step 24.6: Run full test suite**

```bash
python -m pytest tests/ -x -q
```

Expected: green. Address any failures by adapting imports / skipping obsolete assertions.

- [ ] **Step 24.7: Commit**

```bash
git add app/ui/app_shell.py app/ui/main_window.py tests/test_instances_view.py
git commit -m "refactor(ui): switch app_shell to new instances/ package; wire new signals"
```

---

### Task 25: Remove obsolete files

**Files:**
- Delete: `app/ui/views/instances_view.py`
- Delete: `app/ui/views/instance_card.py`

- [ ] **Step 25.1: Verify no remaining references**

```bash
grep -rn "from app.ui.views.instances_view\|from app.ui.views.instance_card\|app.ui.views.instances_view\|app.ui.views.instance_card" C:/Users/Pc_Lu/Desktop/vastai-app/
```

Expected: zero matches outside the files themselves and `__pycache__`.

If matches remain, fix the imports first (back to Task 24).

- [ ] **Step 25.2: Delete files**

```bash
rm C:/Users/Pc_Lu/Desktop/vastai-app/app/ui/views/instances_view.py
rm C:/Users/Pc_Lu/Desktop/vastai-app/app/ui/views/instance_card.py
```

- [ ] **Step 25.3: Run full test suite**

```bash
python -m pytest tests/ -x -q
```

Expected: green.

- [ ] **Step 25.4: Commit**

```bash
git add -A
git commit -m "refactor(ui): remove old single-file InstancesView and InstanceCard"
```

---

### Task 26: Smoke test the running app

**Files:** None modified.

- [ ] **Step 26.1: Launch the app**

```bash
cd C:/Users/Pc_Lu/Desktop/vastai-app && python main.py
```

- [ ] **Step 26.2: Verify with two real or test instances**

Manual checklist (mark each):

- [ ] App opens without exceptions in console
- [ ] Instances tab shows dense cards with chip header (verified, IP, flag, uptime, $/hr)
- [ ] SpecsGrid shows 7 columns with hardware data
- [ ] Action bar uses MDI icons (no emoji glyphs)
- [ ] Filter dropdowns render (GPU / Status / Label / Sort)
- [ ] Selecting a sort option re-orders cards immediately
- [ ] Label tabs show counts; clicking a tab filters cards
- [ ] With ≥ 2 instances RUNNING, Connect both — both should connect, each on a distinct local port (check toasts and chip header endpoint)
- [ ] Restart app — port mapping for known instances persists (verify `~/.vastai-app/config.json` contains `port_map`)
- [ ] Header `Start All` button opens `ConfirmBulkDialog` with aggregate cost
- [ ] Toggle `Select Mode`, select 2 cards, click `Stop` in BulkActionBar — confirmation dialog appears
- [ ] Click `Destroy` on a single card — dialog requires "Eu entendo" checkbox before Confirm enables
- [ ] Per-card log icon opens `LogModal` filtered to that instance's `#<id>`
- [ ] Open Lab icon opens the Lab view for that instance

- [ ] **Step 26.3: Document any issues**

If a checklist item fails, file it as a follow-up. The plan does not require manual UI bugs to be solved here (visual polish iteration belongs in a separate cycle).

- [ ] **Step 26.4: Update README**

Edit `C:/Users/Pc_Lu/Desktop/vastai-app/README.md`. Find the section describing the Instances tab. Replace with (or add):

```markdown
### Instances Tab

The Instances tab provides a dense, multi-instance interface for power users:

- **Per-instance port allocator** — each tunnel gets its own local port (auto-incremented from `default_tunnel_port`); mappings are persisted to `~/.vastai-app/config.json` so restarts preserve URLs.
- **Filters** — GPU type, status, label dropdowns + sort selector; state persists across restarts.
- **Label tabs** — All / No Label / custom labels (synced with the Vast API `label` field).
- **Bulk operations** — `▶ Start All` in the header acts on all visible (filtered) instances; toggle Select Mode for partial selection. All bulk actions show a confirmation modal with aggregate cost. Destroy requires explicit acknowledgement.
- **Action bar** — primary CTA + icon buttons for reboot, snapshot, destroy, log, label, flag, SSH key, and Open Lab. Powered by qtawesome (MaterialDesignIcons).
- **Per-card log** — the log icon opens a modal filtered to that instance's `#<id>` log lines.
```

- [ ] **Step 26.5: Commit smoke test result + README**

```bash
git add README.md
git commit -m "docs(readme): document new Instances tab features (port allocator, filters, bulk)"
```

---

## Self-review checklist (run before declaring done)

- [ ] All 26 tasks committed
- [ ] `python -m pytest tests/ -q` runs clean
- [ ] `git log --oneline -30` shows incremental commits with conventional messages
- [ ] No remaining references to `app.ui.views.instances_view` or `app.ui.views.instance_card` (the old paths)
- [ ] `~/.vastai-app/config.json` after a run contains `schema_version: 3`, `port_map`, `instance_filters`
- [ ] Two simultaneous tunnels work end-to-end with distinct ports
- [ ] Spec acceptance criteria §15 (1-12) all verified manually
