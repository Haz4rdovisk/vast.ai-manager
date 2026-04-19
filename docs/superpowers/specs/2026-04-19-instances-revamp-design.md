# Instances Tab Revamp — Design Spec

**Date:** 2026-04-19
**Status:** Approved (pending user re-review)
**Scope:** Full redesign of the Instances tab: dense Vast-style cards, multi-instance workflows, bulk operations, and a fix for the multi-tunnel connection bug.

---

## 1. Problem Statement

The current Instances tab has three overlapping problems:

1. **Multi-instance bug.** All tunnels share `default_tunnel_port` (e.g. 11434). The 2nd instance fails to connect because `ssh -L 11434:...` aborts with `ExitOnForwardFailure=yes`. UI also displays the same port for every card, so even when a tunnel succeeds, the user gets misleading info. References: `controller.py:424,457,522`, `ssh_service.py:51`, `instance_card.py:166-170`.

2. **Sparse, single-instance UX.** Cards are tall and spacious (designed for 1-2 instances) and lack filters, tabs, sort, bulk actions, or the rich data shown in Vast's web UI (verified badge, IP, region, uptime, billing period, savings, $/hr breakdown, full specs grid).

3. **No bulk affordances.** Operating on multiple instances at once requires N individual clicks. There is no "Start All", "Connect All", or selection mode.

This revamp delivers a dense, multi-instance-first interface with all the Vast feature parity adapted to our glassmorphism design language, plus a robust per-instance port allocator.

---

## 2. Goals

- Support 5-20 instances visible at once with all relevant data on screen
- Eliminate the multi-tunnel port collision (deterministic per-instance port allocation, persisted)
- Provide bulk Start / Stop / Connect / Disconnect / Destroy / Label with cost confirmation
- Filters: GPU type, status, label; tabs by label; sort dropdown
- Action bar with proper iconography (qtawesome + MDI), not emoji
- Maintain consistency with existing design language (`theme.py`, glassmorphism `primitives.py`)

## 3. Non-Goals

- Sort drag-and-drop / custom order
- Saved filter presets
- Card pinning that reorders the list (flag = bookmark only)
- CSV export
- Multi-select label rename with templating
- Webhooks for state changes

---

## 4. Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Card density | **Always-dense** (Vast-style) | User chose A. Maximum info per scroll for power users. |
| Bulk action UX | Confirmation modal w/ aggregate cost + checkbox selection mode | Combines safety with flexibility for partial selection |
| Port allocation | Auto-increment from `default_tunnel_port`, persisted in config, compacted on stale | Predictable, stable across runs, debuggable |
| Open Lab placement | Icon in action bar (`flask-outline`) | Consistent visual rhythm with other actions |
| Console drawer fate | Keep global drawer behind header `Logs` toggle; add per-card log icon for filtered view | Debuggability without permanent footer overhead |
| Icon system | qtawesome + MaterialDesignIcons | Already installed; consistent rendering; runtime colorizable |
| Filter sources | Vast API for labels (`label_instance` SDK method); local discovery for GPU types/statuses | Labels are user-set on Vast → cross-device |
| Sort options | Auto / Price ↑↓ / Uptime ↑↓ / DLPerf / DLPerf-per-$ / Reliability / Status | Covers the most common power-user comparisons |
| Filter/sort persistence | `AppConfig.instance_filters` dict | Survive app restart |
| Architectural approach | **In-place modular refactor** (Approach 1) | Best balance of decomposition and delivery speed |

---

## 5. Module Map

### 5.1 New files

```
app/services/port_allocator.py
app/services/instance_filter.py
app/workers/bulk_action_worker.py
app/ui/components/icons.py
app/ui/views/instances/__init__.py
app/ui/views/instances/instances_view.py        (moved from app/ui/views/instances_view.py)
app/ui/views/instances/filter_bar.py
app/ui/views/instances/label_tabs.py
app/ui/views/instances/instance_card.py         (replaces app/ui/views/instance_card.py)
app/ui/views/instances/chip_header.py
app/ui/views/instances/specs_grid.py
app/ui/views/instances/action_bar.py
app/ui/views/instances/live_footer.py
app/ui/views/instances/bulk_action_bar.py
app/ui/views/instances/log_modal.py
app/ui/views/instances/confirm_bulk_dialog.py
```

### 5.2 Modified files

```
app/controller.py        — port_allocator wiring; bulk slots; set_label
app/models.py            — Instance.label, public_ip, is_verified; AppConfig.port_map, instance_filters, bulk_confirm_threshold; schema_version 2→3
app/config.py            — migration v2→v3 (port_map int-key coercion)
app/services/vast_service.py — fix label≠image bug; add set_label() method
app/workers/tunnel_starter.py — toast/log uses passed-in port (not default)
app/ui/components/primitives.py — icon() helper, IconButton, Chip, ChipRow
```

### 5.3 Removed files

```
app/ui/views/instances_view.py    (moved into instances/)
app/ui/views/instance_card.py     (replaced)
```

`app/ui/components/instance_dashboard_card.py` is preserved — it is used by other views; the implementation plan must verify usage before removing.

---

## 6. Data Model Changes

### 6.1 `Instance` (additions only)

```python
@dataclass
class Instance:
    # ... existing fields ...
    label: str | None = None
    public_ip: str | None = None
    is_verified: bool = False
    inet_billed_per_gb: float = 0.0
```

### 6.2 `AppConfig` (additions only)

```python
@dataclass
class AppConfig:
    # ... existing fields ...
    port_map: dict[int, int] = field(default_factory=dict)
    instance_filters: dict = field(default_factory=dict)
    bulk_confirm_threshold: int = 1
    schema_version: int = 3
```

### 6.3 Migration

```python
# app/config.py
def _migrate(raw: dict) -> dict:
    v = raw.get("schema_version", 1)
    if v < 3:
        raw.setdefault("port_map", {})
        raw.setdefault("instance_filters", {})
        raw.setdefault("bulk_confirm_threshold", 1)
        # JSON serializes int keys as str; coerce back
        raw["port_map"] = {int(k): int(v) for k, v in raw.get("port_map", {}).items()}
        raw["schema_version"] = 3
    return raw
```

### 6.4 `parse_instance` bug fix

```python
# Before (BUG — label is the user label, not the image):
image = raw.get("label") or raw.get("image_uuid")

# After:
image = raw.get("image_uuid") or raw.get("docker_image") or ""
label = raw.get("label") or None
is_verified = (raw.get("verification") == "verified")
public_ip = raw.get("public_ipaddr") or ""
inet_billed_per_gb = _to_float(raw.get("inet_up_billed")) or 0.0
```

### 6.5 New `VastService.set_label`

```python
def set_label(self, instance_id: int, label: str) -> None:
    """Wraps vastai_sdk.label_instance(id=..., label=...)."""
    self.client.label_instance(id=instance_id, label=label)
```

---

## 7. Multi-Tunnel Infrastructure

### 7.1 `PortAllocator` (full reference implementation)

```python
# app/services/port_allocator.py
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
    def __init__(self,
                 default_port: int,
                 initial_map: dict[int, int],
                 persist: Callable[[dict[int, int]], None]):
        self._default = default_port
        self._map: dict[int, int] = dict(initial_map)
        self._persist = persist
        self._lock = Lock()

    def get(self, instance_id: int) -> int:
        with self._lock:
            if instance_id in self._map:
                return self._map[instance_id]
            port = self._next_free()
            self._map[instance_id] = port
            self._persist(dict(self._map))
            return port

    def _next_free(self) -> int:
        used = set(self._map.values())
        p = self._default
        while p in used:
            p += 1
            if p > self._default + 999:
                raise RuntimeError(
                    f"Port exhaustion in [{self._default}, {self._default+999}]")
        return p

    def release(self, instance_id: int) -> None:
        with self._lock:
            if self._map.pop(instance_id, None) is not None:
                self._persist(dict(self._map))

    def compact(self, alive_ids: set[int]) -> None:
        """Free ports for instances no longer present. Call on each refresh."""
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

### 7.2 Controller wiring

```python
# In AppController.__init__:
self.port_allocator = PortAllocator(
    default_port=self.config.default_tunnel_port,
    initial_map=self.config.port_map,
    persist=self._persist_port_map,
)

def _persist_port_map(self, m: dict[int, int]) -> None:
    self.config.port_map = m
    self.config_store.save(self.config)

# In _on_refreshed (after instance list refresh):
alive = {i.id for i in instances}
self.port_allocator.compact(alive)

# Refactored connect_tunnel:
def connect_tunnel(self, iid: int):
    if iid in self._pending_tunnel:
        return
    if not self._has_usable_passphrase():
        self._on_passphrase_success = lambda: self.connect_tunnel(iid)
        self.passphrase_needed.emit()
        return
    port = self.port_allocator.get(iid)   # ← was: self.config.default_tunnel_port
    self._pending_tunnel.add(iid)
    self.tunnel_states[iid] = TunnelStatus.CONNECTING
    self.tunnel_status_changed.emit(iid, TunnelStatus.CONNECTING.value, "connecting")
    self.log_line.emit(f"Conectando #{iid} em :{port}...")
    self._trigger_connect.emit(iid, port)

# In _on_tunnel_status — fix hard-coded port in toast:
if self.tunnel_states[iid] == TunnelStatus.CONNECTED:
    port = self.port_allocator.get(iid)
    self.toast_requested.emit(
        f"Conectado em http://127.0.0.1:{port}", "success", 3000)
    if iid not in self._live_workers:
        self._start_live_metrics(iid)
    if self._find_instance(iid) is not None:
        self._start_model_watcher(iid, port)

# _start_model_watcher takes port as param:
def _start_model_watcher(self, iid: int, port: int):
    self._stop_model_watcher(iid)
    w = ModelWatcher(iid, port)            # ← was: self.config.default_tunnel_port
    w.model_changed.connect(self.model_changed)
    self._model_watchers[iid] = w
    w.start()
```

### 7.3 Behavior guarantees

1. New instance → smallest free port ≥ `default_tunnel_port`
2. Reconnect → same port (stable across app restarts)
3. Destroyed instance → port released on next refresh's `compact()`
4. `Lock` prevents races during parallel allocation (Bulk Connect All)
5. `default_tunnel_port` removed from runtime path but still serves as the allocator base; changing it in Settings affects new allocations only

`ssh_service.start_tunnel(iid, host, port, local_port)` already accepts `local_port` per call — no change needed there.

---

## 8. UI Components & Layout

### 8.1 View hierarchy

```
InstancesView (QWidget)
├─ Header (56px)
│  ├─ Title "My Instances (N)"
│  ├─ Refresh button + interval dropdown
│  ├─ Logs toggle (📋) + Settings (⚙)
│  ├─ Select Mode toggle (☑)
│  └─ Start All split-button (▶ + ▼ menu)
├─ FilterBar (48px)
│  ├─ GPU type dropdown (multi-select)
│  ├─ Status dropdown (multi-select)
│  ├─ Label dropdown (single-select)
│  ├─ Sort dropdown (single-select)
│  └─ Reset filters icon
├─ LabelTabs (40px)
│  ├─ "All (N)"
│  ├─ "No Label (N)"
│  └─ <custom label tabs, dynamic>
├─ BillingStrip (existing)
├─ ScrollArea (cards)
└─ BulkActionBar (overlay, visible when selection.active)
   "N selecionados · Clear │ ▶ Start  ⏹ Stop  🔌 Connect  🔌 Disconnect  🗑 Destroy  🏷 Label"
```

### 8.2 `InstanceCard` composition

```
GlassCard (padding 14px)
├─ ChipHeader
│  ├─ LED + "● 1× RTX 3090" (status color)
│  ├─ ChipRow:
│  │  ├─ Chip(verified, ok-color)
│  │  ├─ Chip(public_ip, accent, mono, click→copy)
│  │  ├─ Chip(country flag emoji)
│  │  ├─ Chip(uptime)
│  │  ├─ Chip(billing period)
│  │  ├─ Chip(savings %)
│  │  └─ Chip($/hr, mono)
│  └─ SelectCheckbox (only when select_mode)
├─ SpecsGrid (7-col QGridLayout)
│  Col 1: Instance / Host / Machine / Vol
│  Col 2: Max CUDA / TFLOPS / VRAM total / Disk speed
│  Col 3: DLPerf / DLPerf-per-$
│  Col 4: Network ports / ↑↓ Mbps
│  Col 5: CPU model / cores used / RAM used
│  Col 6: Disk model / used/total / MB/s
│  Col 7: Mobo / PCIe gen / bus speed
├─ LiveFooter (RUNNING only)
│  ├─ 4 mini-bars: GPU%/temp · vRAM · CPU · RAM
│  └─ Status string "GPU: 67% 72°C, CPU: 23%, running <image>"
└─ ActionBar
   ├─ Primary button (Activate / Connect / Stop, contextual)
   ├─ separator
   ├─ IconButton(reboot)
   ├─ IconButton(cloud-upload)
   ├─ IconButton(recycle)
   ├─ separator
   ├─ IconButton(text-box) → log_modal
   ├─ IconButton(tag) → rename label inline
   ├─ IconButton(flag) → bookmark
   ├─ separator
   ├─ IconButton(key) → SSH-key copy
   └─ IconButton(flask) → Open Lab
```

### 8.3 `primitives.py` additions

```python
import qtawesome as qta

def icon(name: str, color: str = TEXT, size: int = 16) -> QIcon:
    """qta wrapper using MDI namespace."""
    return qta.icon(f"mdi.{name}", color=color)

class IconButton(QPushButton):
    """26×26 ghost button with qta icon, tooltip required."""
    def __init__(self, mdi_name: str, tooltip: str, *,
                 color: str = TEXT, danger: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setToolTip(tooltip)
        self._mdi = mdi_name
        self._color = ERR if danger else color
        self._refresh_icon()

    def _refresh_icon(self):
        col = TEXT_LOW if not self.isEnabled() else self._color
        self.setIcon(icon(self._mdi, color=col))

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._refresh_icon()

class Chip(QFrame):
    """Pill widget. Variants: default, ok, accent, danger. Optional onClick."""
    clicked = Signal()
    def __init__(self, text: str, *, variant: str = "default",
                 mono: bool = False, clickable: bool = False, parent=None): ...

class ChipRow(QFrame):
    """HBox of chips, gap=6px, FlowLayout for wrapping."""
```

### 8.4 Icon catalog

```python
# app/ui/components/icons.py
PLAY        = "play"
STOP        = "stop"
POWER       = "power"
DELETE      = "delete-outline"
REBOOT      = "restart"
CLOUD       = "cloud-upload-outline"
RECYCLE     = "recycle"
LOG         = "text-box-outline"
TAG         = "tag-outline"
FLAG        = "flag-outline"
KEY         = "key-variant"
LAB         = "flask-outline"
TUNNEL      = "lan-connect"
DISCONNECT  = "lan-disconnect"
COPY        = "content-copy"
VERIFIED    = "shield-check"
EXPAND      = "chevron-down"
FILTER      = "filter-variant"
SORT        = "sort"
SELECT      = "checkbox-multiple-outline"
```

### 8.5 `InstancesView` data flow

```python
class InstancesView(QWidget):
    activate_requested = Signal(int)
    deactivate_requested = Signal(int)
    connect_requested = Signal(int)
    disconnect_requested = Signal(int)
    set_label_requested = Signal(int, str)
    bulk_action_requested = Signal(str, list, dict)  # action, ids, opts
    open_lab_requested = Signal(int)
    open_settings_requested = Signal()
    open_logs_requested = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._all_instances: list[Instance] = []
        self._cards: dict[int, InstanceCard] = {}
        self._selected: set[int] = set()
        self._select_mode = False
        self._filter_state = FilterState.from_dict(
            controller.config.instance_filters)
        # build_ui(); wire filter_bar / label_tabs / cards

    @Slot(list, object)
    def handle_refresh(self, instances, user):
        self._all_instances = instances
        self._rebuild_label_tabs()
        self._rebuild_filter_options()
        self._reapply_filter()

    def _reapply_filter(self):
        filtered = instance_filter.apply(self._all_instances, self._filter_state)
        self._render_cards(filtered)
        self._update_count_badges()
        self._controller.update_instance_filters(self._filter_state.to_dict())

    def _render_cards(self, instances: list[Instance]):
        seen = set()
        for inst in instances:
            if inst.id in self._cards:
                self._cards[inst.id].update(inst)
            else:
                card = InstanceCard(
                    inst,
                    port=self._controller.port_allocator.get(inst.id),
                    selected=(inst.id in self._selected),
                    select_mode=self._select_mode,
                )
                self._wire_card(card)
                self._cards[inst.id] = card
                self._scroll_layout.addWidget(card)
            seen.add(inst.id)
        for iid in list(self._cards):
            if iid not in seen:
                self._cards.pop(iid).deleteLater()
```

### 8.6 Style tokens

- Card bg `SURFACE_1`, border `BORDER_LOW`, hover `BORDER_MED`
- Chip bg `SURFACE_2`; variants apply 10% alpha bg + 30% border in their accent color
- IconButton hover: `GLASS_HOVER`, icon goes `TEXT` → `TEXT_HI`
- Selected card: 2px border `ACCENT_GLOW`
- Responsive breakpoint at 1100px viewport: SpecsGrid drops from 7-col to 5-col (merges Mobo+PCIe and Disk model+used)

---

## 9. Bulk Operations & Selection Mode

### 9.1 Selection state

```python
@dataclass
class SelectionState:
    mode: bool = False
    selected: set[int] = field(default_factory=set)

    @property
    def active(self) -> bool:
        return self.mode or bool(self.selected)
```

### 9.2 Trigger paths

- **Header `Start All ▼` split-button** — applies to all visible (filtered) instances; no checkbox interaction needed
- **Select Mode toggle** — enables checkboxes on all cards; click on card body toggles selection; `BulkActionBar` shows selected count and action buttons
- **Card body click while in select mode** — toggles selection. Action buttons inside the card consume the event so they execute individual actions, NOT toggle.

### 9.3 `ConfirmBulkDialog`

Shown whenever an action affects ≥ `bulk_confirm_threshold` instances (default 1 = always). For destroy, threshold is ignored — destroy always confirms with an additional checkbox "Eu entendo que isto é irreversível".

Layout:

```
Confirmar <action> em <N> instâncias
─────────────────────────────────────
• #34860213  1× RTX 3090   $0.30/hr
• #35170813  1× RTX 3090   $0.30/hr
• #35400001  2× RTX 4090   $0.90/hr

Custo agregado: $1.50/hr      (or "Você economizará $X/hr" for stop)
☑ Conectar tunnels após start  (start only)
[input "Label"]                (label only)
☑ Eu entendo                   (destroy only, required)

[ Cancelar ]   [ Confirmar ]
```

Returns `(accepted: bool, opts: dict)` from `exec()`.

### 9.4 `BulkActionWorker`

```python
# app/workers/bulk_action_worker.py
class BulkActionWorker(QObject):
    progress = Signal(int, int, int, str)   # done, total, iid, last_msg
    finished = Signal(str, list, list)      # action, ok_ids, fail_ids

    def __init__(self, vast: VastService):
        super().__init__()
        self.vast = vast

    @Slot(str, list, dict)
    def run(self, action: str, ids: list[int], opts: dict):
        ok, fail = [], []
        for i, iid in enumerate(ids, 1):
            try:
                if action == "start":
                    self.vast.start_instance(iid)
                elif action == "stop":
                    self.vast.stop_instance(iid)
                elif action == "destroy":
                    self.vast.destroy_instance(iid)
                elif action == "label":
                    self.vast.set_label(iid, opts["label"])
                ok.append(iid)
                self.progress.emit(i, len(ids), iid, "ok")
            except Exception as e:
                fail.append(iid)
                self.progress.emit(i, len(ids), iid, str(e)[:80])
        self.finished.emit(action, ok, fail)
```

For `connect` / `disconnect`, the controller dispatches per-instance `connect_tunnel(iid)` / `disconnect_tunnel(iid)` calls — these are local tunnel ops, not API calls.

### 9.5 Controller bulk API

```python
_trigger_bulk = Signal(str, list, dict)

# In bootstrap():
self.bulk_thread = QThread()
self.bulk_worker = BulkActionWorker(self.vast)
self.bulk_worker.moveToThread(self.bulk_thread)
self.bulk_worker.progress.connect(self._on_bulk_progress)
self.bulk_worker.finished.connect(self._on_bulk_finished)
self._trigger_bulk.connect(self.bulk_worker.run)
self.bulk_thread.start()

def bulk_action(self, action: str, ids: list[int], opts: dict | None = None):
    opts = opts or {}
    if action in ("connect", "disconnect"):
        for iid in ids:
            (self.connect_tunnel if action == "connect"
             else self.disconnect_tunnel)(iid)
        return
    self._trigger_bulk.emit(action, ids, opts)

def _on_bulk_finished(self, action, ok, fail):
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

### 9.6 Concurrency guarantee

The bulk worker is **single-flight** (no overlapping bulk runs). If the user triggers a second bulk while one is in progress, show toast "Operação em andamento, aguarde" and reject. Per-instance tunnel ops (connect/disconnect) are independent and may run in parallel via `TunnelStarter` thread.

---

## 10. Filtering & Sorting

### 10.1 `FilterState`

```python
# app/services/instance_filter.py
@dataclass
class FilterState:
    gpu_types: list[str] = field(default_factory=list)   # ["1× RTX 3090", "2× RTX 4090"]
    statuses: list[str] = field(default_factory=list)    # ["RUNNING", "STOPPED"]
    label: str | None = None                              # "" = All, "__none__" = No Label, else literal
    sort: str = "auto"                                    # see options below

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "FilterState": ...

def apply(instances: list[Instance], state: FilterState) -> list[Instance]:
    """Pure function — no Qt, no I/O. Filters then sorts."""
    out = list(instances)
    if state.gpu_types:
        out = [i for i in out if _gpu_key(i) in state.gpu_types]
    if state.statuses:
        out = [i for i in out if i.state.value in state.statuses]
    if state.label is not None:
        if state.label == "__none__":
            out = [i for i in out if not i.label]
        elif state.label:
            out = [i for i in out if i.label == state.label]
    return _sort(out, state.sort)
```

### 10.2 Sort options

| Key | Behavior |
|---|---|
| `auto` | RUNNING first, then by uptime desc; STOPPED last by recency |
| `price_asc` / `price_desc` | by `dph` |
| `uptime_asc` / `uptime_desc` | by `duration_seconds` |
| `dlperf` | by `dlperf` desc |
| `dlperf_per_dollar` | by `flops_per_dphtotal` desc |
| `reliability` | by `reliability` desc |
| `status` | grouped: RUNNING / STARTING / STOPPING / STOPPED |

### 10.3 Persistence

Each filter change calls `controller.update_instance_filters(state.to_dict())` which stores into `AppConfig.instance_filters` and saves to disk.

---

## 11. Error Handling & Edge Cases

| Scenario | Behavior |
|---|---|
| `port_allocator` exhausts range (>999) | Log + error toast; bulk continues for instances that successfully allocated |
| `set_label` API failure | Toast error; local label unchanged; next refresh syncs |
| Filter state corrupted in config | Reset to defaults, log warning, no crash |
| Bulk with 0 selected ids | Buttons disabled — no error path |
| Vast SDK returns `None` for `label` | OK — `Instance.label = None`, instance falls into "No Label" tab |
| Concurrent renders during bulk | `_render_cards` diffs by iid, reuses cards |
| Tunnel fails during Bulk Connect | Other tunnels continue; aggregated toast at end |
| User changes `default_tunnel_port` in Settings | Existing port_map preserved; new allocations use new base |
| Empty list + active filter | Empty state: "Nenhuma instância corresponde · [Limpar filtros]" |
| Empty list + no filter | Existing welcome card |
| Custom label tab whose instance is deleted | Tab disappears next refresh; if active, fall back to "All" |
| Selection survives filter change | Hidden selected count: "(2 ocultos pelo filtro)" |
| Card update vs recreate | `card.update(inst)` preserves animation/scroll state |
| Bulk Connect with non-RUNNING instance | Filtered out before dialog: "1 ignorada (não está rodando)" |
| Window resize | ChipRow wraps via FlowLayout; SpecsGrid 7→5 col under 1100px |
| Select mode + click Activate on a card | Action runs; selection NOT toggled (event consumed) |

---

## 12. Testing Strategy

```
tests/
├── unit/
│   ├── services/
│   │   ├── test_port_allocator.py
│   │   ├── test_instance_filter.py
│   │   └── test_vast_service_parse.py
│   ├── workers/
│   │   └── test_bulk_action_worker.py
│   └── ui/
│       ├── test_chip_row_layout.py
│       └── test_specs_grid.py
├── integration/
│   ├── test_multi_tunnel_e2e.py
│   ├── test_bulk_start_flow.py
│   └── test_filter_persistence.py
```

**Critical tests not to skip:**

- `test_port_allocator_concurrent_get` — 20 threads call `get(random_iid)`, all unique, no collision
- `test_port_allocator_persists_on_mutation` — callback invoked exactly once per `get` of new id, never on cache hit
- `test_port_allocator_compact_releases_stale` — instance vanishes from API → port returns to pool
- `test_bulk_destroy_requires_confirmation_checkbox` — submit without checkbox = button disabled
- `test_label_tab_count_updates_on_label_change` — `set_label("foo")` → "old" tab decrements, "foo" tab increments or appears
- `test_card_diff_preserves_live_metrics_state` — rapid refreshes do not flicker `LiveFooter`
- `test_filter_state_survives_app_restart` — set filter → reload `AppConfig` → `FilterState.from_dict` round-trips exactly
- `test_parse_instance_label_separated_from_image` — raw with both `label` and `image_uuid` produces the right values in the right fields

`pytest-qt` required for widget tests (verify in `requirements.txt` during plan).

---

## 13. Documentation Updates

- `README.md` — Instances section: screenshots, mention of persisted port_map
- `docs/review_and_redesign.md` — mark Instances section "delivered v2"

---

## 14. Out-of-scope Follow-ups

Captured here so they're not forgotten:

- Sort by drag-and-drop (custom order)
- Saved filter presets ("My GPU farm", "Cheap experiments")
- Card pinning that reorders the list
- CSV / JSON export of the instance list
- Multi-select label rename with regex/template
- Webhooks "instance state changed"
- Per-card live cost ticker (extrapolated from start time)

---

## 15. Acceptance Criteria

The revamp is done when:

1. Two or more instances can have active tunnels simultaneously, each on its own local port, with the correct port displayed in each card and toast
2. Restarting the app preserves the port mapping for instances still on the account
3. Destroying an instance frees its port within one refresh cycle
4. Filter bar (GPU/Status/Label/Sort) is functional, persisted across restarts, and applies in <50ms on a list of 50 instances
5. Label tabs reflect actual `Instance.label` from the Vast API; "No Label" tab counts instances with `label is None`
6. `Start All` from the header opens a confirmation dialog showing aggregate cost and lists each affected instance
7. Selection mode allows partial bulk operations with the same confirmation dialog
8. Destroy always requires the explicit "Eu entendo" checkbox
9. All action bar icons render via qtawesome MDI (no emoji glyphs in buttons)
10. Card layout uses the dense Vast-style structure (chip header + 7-col specs grid + live footer + action bar)
11. The console drawer is hidden by default behind a header toggle; per-card log icon opens a filtered modal for that instance
12. All tests in §12 pass; `parse_instance` no longer maps `label` to `image`
