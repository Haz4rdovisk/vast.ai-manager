# Model Store Side Panel — Design Spec

**Date:** 2026-04-19
**Status:** Draft — brainstormed, awaiting user review before plan
**Supersedes (partial):** Tasks 12, 13, 14 of `2026-04-19-ai-lab-studio-revamp.md` (install/download flow). Studio view tasks (15–22) unaffected.

## 1. Goal

Revamp the Model Store (Discover) so that:

- Search actually works (currently capped at 20 results with broken category filter).
- Cards are visually on par with the rest of the app.
- Selecting a model opens a right-side panel (split view) instead of a modal dialog.
- Installs are transparent: the user sees what is being installed, with a single confirmation up front and live progress (stage checklist + percentage bar + collapsible log).
- Install state persists across app crashes / restarts by reattaching to the remote SSH process that is still running on the Vast.ai VM.
- Only one install can run per instance at a time; concurrent installs on *different* instances are allowed.

## 2. Problems in current state

File references use line numbers at time of writing.

- **`app/lab/views/discover_view.py:191`** — `HFSearchWorker(query=search_term, limit=20)` hard-caps result set at 20.
- **`app/lab/views/discover_view.py:182-184`** — category filter is concatenated into the HF query string (`f"{search_term} {filter_val}"`). This pollutes the search rather than filtering it; no server-side category filter is used.
- **`app/lab/views/model_details_dialog.py`** — install flow lives in a modal `QDialog`. Visually disconnected from the rest of the Lab, competes with main nav. Buttons (`Deploy Model` in particular) render faint/gray and are easy to miss.
- **`app/lab/views/install_panel.py`** — install progress lives in a *separate full-page view* that the app navigates to, taking the user away from Discover. No persistence: if the app is killed mid-download, UI has no recollection that a job was running.
- **No per-instance lock** — clicking Deploy a second time while a job is running would spawn a second worker. Safe by accident (SSH contention), but bad UX.
- Cards are plain rectangles with every element left-aligned; no hover, no selected state, no indication that a model is already installed.

## 3. Scope

**In scope**
- `DiscoverView` (layout, filters, pagination, cards).
- `ModelDetailsDialog` → replaced by `InstallPanelSide` (side panel).
- `InstallPanel` (legacy full-page) → removed; its progress UI is inlined into the side panel.
- `HuggingFaceClient.search_gguf_models` — new `pipeline_tag` param, higher default limit.
- `JobRegistry` service — new; tracks active installs, persists to disk, enforces per-instance lock.
- `RemoteJobProbe` worker — new; checks remote state on app boot for reattachment.
- Remote install script (`script_download_model`, `script_install_llamacpp`) — writes JSON state files on the VM so we can probe/reattach.
- `AppShell` wiring — registry initialization, reattachment on boot, routing.

**Out of scope**
- Studio view, analytics, hardware view.
- Local GGUF management (Models view).
- Migration of older jobs — no persisted state existed before this spec.
- Pause/resume mid-download as a first-class feature (partial via `wget -c` on STALE resume, but not a live-pause button).

## 4. Architecture

Three new components plus two refactors:

**New**
- **`InstallPanelSide`** (`app/lab/views/install_panel_side.py`) — right-side widget embedded in `DiscoverView` via `QSplitter`. Replaces `ModelDetailsDialog`. Three render modes (idle / model-selected / active-job).
- **`JobRegistry`** (`app/lab/services/job_registry.py`) — `QObject` singleton owned by `AppShell`. Holds `active_jobs: dict[int, JobDescriptor]` (keyed by `iid`). Persists to `~/.vastai-app/jobs.json`. Emits `job_started | job_updated | job_finished | job_reattached`.
- **`RemoteJobProbe`** (`app/lab/workers/remote_job_probe.py`) — `QThread` that runs `script_check_job` over SSH and parses the result into `RUNNING | DONE | STALE | MISSING`.

**Refactored**
- **`DiscoverView`** — converts top-level layout to `QSplitter(Qt.Horizontal)` with list on the left (min 60%) and `InstallPanelSide` on the right (min 380px, collapsible). Cards extracted to `app/ui/components/model_card.py`. Filters rewritten (see §6). Pagination via "Load more" button (see §6.3).
- **`HuggingFaceClient.search_gguf_models`** — accepts `pipeline_tag: str | None` and `limit: int = 100`.

### 4.1 Data flow

```
Click card → DiscoverView selects model → InstallPanelSide.set_model(model)
Click Deploy → InstallPanelSide.confirm_deploy() → inline overlay
Confirm → JobRegistry.can_start(iid)? → JobRegistry.start_job(descriptor)
        → AppShell._download_model_by_name(iid, repo, filename)
        → StreamingRemoteWorker (existing) streams lines
        → progress_parsers (existing) → JobRegistry.update(...)
        → InstallPanelSide listens to job_updated → refreshes bar/stages
Finish → JobRegistry.finish(key, ok) → probe_instance(iid) → state.gguf refreshes
```

### 4.2 Reattachment flow (boot)

```
AppShell.attach_controller → JobRegistry.load_from_disk()
First instances_refreshed signal → _try_reattach_jobs_once(instances)
  For each active job:
    inst = find(desc.iid)
    if inst offline → skip, retry on next refresh
    RemoteJobProbe(ssh, host, port, desc)
    Result:
      RUNNING → start new StreamingRemoteWorker that does:
                  `tail -n +1 -f {LOG_FILE}` + periodic `cat {STATE_FILE}`
                → emit job_reattached, toast "Resumed install on #X"
      DONE    → JobRegistry.finish(key, True); cleanup remote state; toast
      STALE   → panel shows banner: "Previous install died at {stage}
                 ({%}) — [Resume with wget -c] [Discard]"
      MISSING → JobRegistry.drop(key) silently
```

## 5. Data model

New dataclass in `app/lab/state/models.py`:

```python
@dataclass
class JobDescriptor:
    key: str                  # "{iid}-{slug(repo)}-{quant}"
    iid: int
    repo_id: str              # "bartowski/Meta-Llama-3-8B-Instruct-GGUF"
    filename: str             # "meta-llama-3-8b-instruct-Q5_K_M.gguf"
    quant: str                # "Q5_K_M"
    size_bytes: int
    needs_llamacpp: bool
    remote_state_path: str    # "/workspace/.vastai-app/jobs/{key}.json"
    remote_log_path: str      # "/tmp/install-{key}.log"
    started_at: float         # epoch seconds
    stage: str                # "starting|apt|clone|cmake|build|download|verify|done|failed|cancelled"
    percent: int              # 0..100
    speed: str                # "12.3 MB/s" (cosmetic)
    bytes_downloaded: int     # for ETA calc
    error: str | None
```

### 5.1 Local persistence

Path: `~/.vastai-app/jobs.json` (same directory as existing user settings).

Schema:
```json
{
  "active_jobs": {
    "35273157": { /* JobDescriptor fields */ }
  },
  "completed_recent": [ /* up to 20 recent finished, for history UI later */ ]
}
```

Atomic write: serialize → write to `jobs.json.tmp` → `os.replace("jobs.json.tmp", "jobs.json")`. A `.jobs.lock` file is taken during mutations to protect against a second app instance.

### 5.2 Remote persistence

Written by the install script itself at each stage transition:

```
/workspace/.vastai-app/jobs/{key}.json
    {"pid": 12345, "stage": "download", "percent": 43,
     "bytes_downloaded": 2300000000, "updated_at": 1713552000}

/tmp/install-{key}.log       # full stdout/stderr of install+download
```

### 5.3 `script_check_job(key)` (new helper)

Returns one of `RUNNING | DONE | STALE | MISSING` on stdout line 1, followed by the JSON state on line 2.

Uses `python3 -c` (not `jq`) to parse state, since Python is guaranteed on Vast images and `jq` is not.

```bash
STATE=/workspace/.vastai-app/jobs/{KEY}.json
if [ ! -f $STATE ]; then echo "MISSING"; exit 0; fi
PID=$(python3 -c "import json; print(json.load(open('$STATE')).get('pid',''))")
STAGE=$(python3 -c "import json; print(json.load(open('$STATE')).get('stage',''))")
if [ "$STAGE" = "done" ]; then echo "DONE"; cat $STATE; exit 0; fi
if [ -n "$PID" ] && kill -0 $PID 2>/dev/null; then
  echo "RUNNING"; cat $STATE; exit 0
fi
echo "STALE"; cat $STATE
```

### 5.4 `JobRegistry` public API

```python
class JobRegistry(QObject):
    job_started    = Signal(str)        # key
    job_updated    = Signal(str)        # key
    job_finished   = Signal(str, bool)  # key, ok
    job_reattached = Signal(str)        # key

    def can_start(self, iid: int) -> bool:
        return iid not in self._active

    def active_for(self, iid: int) -> JobDescriptor | None: ...
    def active_items(self) -> list[tuple[str, JobDescriptor]]: ...
    def start_job(self, descriptor: JobDescriptor) -> None: ...
    def update(self, key: str, **fields) -> None: ...
    def finish(self, key: str, ok: bool, error: str | None = None) -> None: ...
    def drop(self, key: str) -> None: ...
    def load_from_disk(self) -> None: ...
    def save(self) -> None: ...   # called after every mutation
```

## 6. Filters and pagination

### 6.1 HF client changes

```python
def search_gguf_models(
    self,
    query: str = "",
    limit: int = 100,
    pipeline_tag: str | None = None,
) -> list[HFModel]:
    params = {"search": query, "filter": "gguf",
              "sort": "downloads", "direction": "-1",
              "limit": limit, "full": "True"}
    if pipeline_tag:
        params["pipeline_tag"] = pipeline_tag
    ...
```

### 6.2 Category filter (hybrid)

```python
CATEGORY_MAP = {
    "All":        {"pipeline": None,                   "heuristic": None},
    "General":    {"pipeline": "text-generation",      "heuristic": None},
    "Coding":     {"pipeline": "text-generation",      "heuristic": "coding"},
    "Reasoning":  {"pipeline": "text-generation",      "heuristic": "reasoning"},
    "Chat":       {"pipeline": "text-generation",      "heuristic": "chat"},
    "Multimodal": {"pipeline": "image-text-to-text",   "heuristic": None},
    "Embedding":  {"pipeline": "feature-extraction",   "heuristic": None},
}

CODING_RX    = re.compile(r"\b(coder?|starcode|deepseek-?coder|qwen-?coder|wizardcoder|codellama|codegemma)\b", re.I)
REASONING_RX = re.compile(r"\b(r1|qwq|reason|o1|phi-?reason|deepseek-?r)\b", re.I)
CHAT_RX      = re.compile(r"\b(chat|instruct|sft|assistant|rp|roleplay)\b", re.I)
```

The category is no longer concatenated into the query. Query stays pure; `pipeline_tag` goes through the API; heuristic regex runs client-side on returned `HFModel.name` and `tags`.

### 6.3 Pagination

- Default `limit=100` per request.
- `DiscoverView` keeps `self.all_models: list[HFModel]` accumulated.
- "Load more" button at the bottom of the list; when clicked, re-fires the search with the next cursor from the HF `Link` header.
- Status line: `"Showing 43 of 100+ (after filters) — [Load more]"`.
- Scroll infinito explicitly rejected for predictability and testability.

## 7. UI layout

### 7.1 Split view

```
┌─────────────────────────────────────────────────────────────────┐
│ Model Store   [🔍 search]  [Category▾][Size▾][Sort▾] [Search]  │
├────────────────────────────────────┬────────────────────────────┤
│ Cards (grid-ish, vertical flow)    │ InstallPanelSide           │
│ [Load more]                        │ (idle/selected/active)     │
└────────────────────────────────────┴────────────────────────────┘
    60% flex                           40% (min 380px)
```

- `QSplitter(Qt.Horizontal)`, `setChildrenCollapsible(True)` on handle 0 so the panel can be hidden via its `[✕]` button.
- Sizes saved in `~/.vastai-app/ui_state.json` as `{"discover_splitter": [720, 480]}`.

### 7.2 Model card (`app/ui/components/model_card.py`)

```
╭────────────────────────────────────────────────────────────╮
│ [avatar] vntl-llama3-8b-v2-gguf                    [8.0B] │
│          by lmg-anon                                       │
│          [gguf] [llama] [uncensored]                       │
│          ❤ 13   ↓ 1.7M                                     │
│ ─────────────────────────────────────────                  │
│   #35273157 ● 95  Perfect       [Open HF ↗] [Details →]   │
╰────────────────────────────────────────────────────────────╯
```

States:
- **Default** — `GlassCard` baseline.
- **Hover** — border gradient `t.ACCENT` alpha 30% + soft `QGraphicsDropShadowEffect` lift.
- **Selected** (matching model is open in side panel) — solid `t.ACCENT` border + subtle background tint.
- **Installed** (this repo+quant already present in any `state.gguf`) — chip `✓ Installed on #X`.
- **Installing** (`JobRegistry.active_for(iid)` matches this model) — thin progress stripe at the top of the card + chip `↓ 43% on #X`.

Avatar fetched from `https://huggingface.co/{author}/avatar` via `QNetworkAccessManager`, cached under `~/.vastai-app/avatars/{author}.png`, fallback to circular initial.

### 7.3 Side panel modes

**Mode A — idle:** illustration + "Select a model from the left".

**Mode B — model selected, no active job for any instance:**
- Hero (name, author, stats, Open HF).
- Target configuration dropdown (quant list, default Q4_K_M if present).
- "Deployment Pipeline" section with one card per instance:
  - GPU name, VRAM, fit score + label.
  - `Setup Environment` (if llama.cpp missing) + `Deploy Model`.

**Mode C — active job visible:**
- Hero.
- "Installing on #X" card:
  - Current stage heading ("Downloading GGUF").
  - Big progress bar with % + speed + ETA.
  - Vertical stage checklist (✓ / ● running / ○ pending / ✗ failed).
  - "Show live log" collapsible (reuses `ProgressPanel`).
  - `Cancel install` button.
- Other instances shown below in their normal Mode B card (so user can deploy same model to another instance in parallel).

**Per-instance lock display in Mode B:**
- If `registry.active_for(iid)` exists for some *other* model (i.e. the currently-selected model differs from the one being installed on that instance) → show `BusyCard`:
  `⚠ BUSY with {model} · [View install ↗]` (clicking switches the panel's selected model back to the installing one, which auto-triggers Mode C).

**Mode selection trigger:** Mode C renders when `registry.active_for(iid)` exists *and* its descriptor matches the currently-selected model (repo+quant) on at least one instance. Otherwise Mode B is used with per-instance BusyCards where applicable.

### 7.4 Confirmation overlay (inline in panel)

Not a `QDialog`. Renders inside `InstallPanelSide` via an internal `QStackedWidget` so it sits within the same visual hierarchy.

```
╭─ Confirm Deployment ───────────────────╮
│  Target: #35273157 · RTX 3090 · 24GB  │
│  Model:  vntl-llama3-8b-v2-gguf        │
│  File:   ..v2-Q5_K_M.gguf (5.3 GB)     │
│  Dest:   /workspace/models/            │
│                                        │
│  Steps:                                │
│    ✓ llama.cpp already installed       │
│    • Download 5.3 GB                   │
│                                        │
│             [ Cancel ]  [ Confirm → ]  │
╰────────────────────────────────────────╯
```

After confirm → overlay dismissed → panel switches to Mode C.

### 7.5 Visual/theme fixes

- `Deploy Model` button: fill `t.ACCENT`, text white 600, hover `t.ACCENT_HI`. Currently it reads as grey.
- `Setup Environment`: already violet, bump weight to 700 for parity.
- Disabled state: `rgba(255,255,255,0.04)` fill, dashed `t.BORDER_LOW` border, `t.TEXT_LOW` text, `ForbiddenCursor`.
- Score pill in panel: `StatusPill` with `setProperty("size", "lg")`; add selector in global QSS.

## 8. Install flow

### 8.1 Happy path

1. User clicks **Deploy Model** in Mode B.
2. `InstallPanelSide.confirm_deploy()` shows overlay (§7.4).
3. User clicks **Confirm**. Registry lock re-checked; if acquired, descriptor built:
   ```python
   key = f"{iid}-{slug(repo)}-{quant}"
   desc = JobDescriptor(key, iid, repo_id, filename, quant, size_bytes,
                        needs_llamacpp=not state.setup.llamacpp_installed,
                        remote_state_path=f"/workspace/.vastai-app/jobs/{key}.json",
                        remote_log_path=f"/tmp/install-{key}.log",
                        started_at=time.time(),
                        stage="starting", percent=0,
                        bytes_downloaded=0, speed="", error=None)
   JobRegistry.start_job(desc)
   ```
4. `AppShell._download_model_by_name` runs (essentially unchanged), but the composed script now wraps its stages with `write_state` helpers so the remote JSON file reflects each transition:
   ```bash
   write_state() {
     mkdir -p /workspace/.vastai-app/jobs
     python3 - <<EOF
   import json, os, time
   json.dump({"pid": $$, "stage": "$1", "percent": int("${2:-0}"),
              "bytes_downloaded": int("${3:-0}"),
              "updated_at": int(time.time())},
             open("$STATE", "w"))
   EOF
   }
   ```
5. `StreamingRemoteWorker` emits lines; existing `progress_parsers` translate them into stage/percent; handler calls `JobRegistry.update(key, stage=..., percent=..., speed=...)`.
6. `InstallPanelSide` listens to `JobRegistry.job_updated` and re-renders the progress block.
7. On `StreamingRemoteWorker.finished(ok)`, `JobRegistry.finish(key, ok)`; probe refreshes `state.gguf`; toast surfaces.

### 8.2 Reattach (see §4.2)

### 8.3 Cancel

1. User clicks `Cancel install` in Mode C.
2. Inline confirm: "This will kill the remote process and leave the partial file. Continue?"
3. App runs a short SSH script: read PID from state file, `kill -TERM $PID`, remove state file.
4. `JobRegistry.finish(key, ok=False, error="cancelled")`.
5. Partial `.gguf` retained (so STALE-resume with `wget -c` is possible later if user reopens).

### 8.4 Error classification

| Signal | Stage set to | UI surface |
|---|---|---|
| SSH disconnect while running | current stage kept, error="disconnect" | Yellow banner "Connection lost — reattach on reconnect" |
| "No space left on device" in log | "failed", error="disk_full" | Red card with `[Free space] [Pick smaller quant]` |
| Size mismatch vs HF sibling size | "failed", error="size_mismatch" | Red card with `[Retry]` (re-downloads clean) |
| cmake/build non-zero | "failed", error=tail(log, 200) | Red card, tail log shown, `[Retry]` |
| User cancel | "cancelled" | Neutral card, `[Retry]` |

## 9. Per-instance lock enforcement

Three enforcement points:

1. **Render-time gate** (`InstallPanelSide._render_instance_card`): if `registry.active_for(iid)` is set, render `BusyCard` instead of ReadyCard.
2. **Pre-start race guard** (`InstallPanelSide._confirm_deploy` handler): final `registry.can_start(iid)` check before `start_job`. If false, show an inline error and rerender.
3. **Discover card overlay**: if `registry.active_for(iid)` matches a card's repo+quant, overlay progress stripe on that card.

Different instances never block each other. If you have two instances connected, both can install (different) models at the same time.

## 10. File structure

```
app/lab/
├── services/
│   ├── job_registry.py          # NEW
│   ├── huggingface.py           # MOD (pipeline_tag, limit)
│   └── remote_setup.py          # MOD (write_state + script_check_job)
├── state/
│   └── models.py                # MOD (+ JobDescriptor)
├── workers/
│   ├── huggingface_worker.py    # MOD (pipeline_tag)
│   └── remote_job_probe.py      # NEW
└── views/
    ├── discover_view.py         # MOD (splitter, filters, pagination, card extraction)
    ├── install_panel_side.py    # NEW (replaces model_details_dialog)
    ├── model_details_dialog.py  # DELETE
    └── install_panel.py         # DELETE

app/ui/components/
├── model_card.py                # NEW
└── install_progress.py          # NEW

app/ui/app_shell.py              # MOD (registry init, reattach, route removal)
```

`NavRail` loses the `install` entry (if present) since install is no longer a standalone view.

## 11. Wiring in `AppShell`

```python
# __init__
self.job_registry = JobRegistry(self)
self.job_registry.load_from_disk()

self.discover = DiscoverView(self.store, self.job_registry, self)
self._add_view("discover", self.discover)
self.discover.download_requested.connect(self._download_model_by_name)
self.discover.setup_requested.connect(lambda iid: self._chain_setup(["install_llamacpp"], iid))

# attach_controller
controller.instances_refreshed.connect(self._try_reattach_jobs_once)

def _try_reattach_jobs_once(self, instances, _user):
    if getattr(self, "_reattach_done", False):
        return
    self._reattach_done = True
    for key, desc in self.job_registry.active_items():
        inst = next((i for i in instances if i.id == desc.iid), None)
        if not inst or not inst.ssh_host:
            continue  # next refresh will try again
        probe = RemoteJobProbe(self._ssh, inst.ssh_host, inst.ssh_port, desc, self)
        probe.result.connect(lambda r, d=desc: self._on_job_probe_result(d, r))
        probe.start()

def _on_job_probe_result(self, desc, result):
    # result is tuple: (state: str, parsed_json: dict)
    match result[0]:
        case "RUNNING": self._reattach_stream(desc, result[1])
        case "DONE":    self.job_registry.finish(desc.key, True)
        case "STALE":   self.discover.show_stale_banner(desc, result[1])
        case "MISSING": self.job_registry.drop(desc.key)
```

`_download_model_by_name` stays structurally the same but also writes to `JobRegistry` in addition to emitting `store.update_install_job`. The store signal stays for StudioView and others; registry is the durable source of truth.

## 12. Testing

### 12.1 Unit

- `tests/lab/services/test_job_registry.py`
  - persist/load roundtrip
  - `can_start` gate
  - atomic write (crash between tmp and replace → file still valid)
  - signals: `start/update/finish` emit correctly
- `tests/lab/services/test_huggingface.py`
  - mock `requests.get` — verify `pipeline_tag`, `limit` sent
  - siblings parsing with size + quant regex
- `tests/lab/views/test_discover_filters.py` (pytest-qt headless)
  - 50 fake `HFModel`s in; apply each category → correct subset
  - size filter combined with category
  - sort-by-score with empty instance list doesn't crash
- `tests/lab/views/test_install_panel_side.py`
  - Mode A/B/C render correctly per registry state
  - Confirm flow calls `start_job` + emits `download_requested`
  - Busy instance renders BusyCard
- `tests/lab/workers/test_remote_job_probe.py`
  - mock SSH output → parse all four outcomes
- `tests/lab/services/test_remote_setup_jobs.py`
  - `script_download_model` includes `write_state` blocks
  - `bash -n` syntax check on rendered scripts

### 12.2 Manual integration checklist (in spec repo)

- [ ] Split view opens/closes smoothly
- [ ] Cards show fit chips per instance
- [ ] Filter "Coding" returns qwen-coder/deepseek-coder, not llama
- [ ] Filter "Multimodal" returns image-text-to-text repos
- [ ] Load more advances cursor and appends
- [ ] Deploy → happy path → model usable in Studio
- [ ] Kill app during download → reopen → reattach → completes
- [ ] Open second model while iid=#X downloading → Busy card
- [ ] Two instances downloading two models in parallel both progress
- [ ] Cancel install → remote state cleaned → retry fresh works
- [ ] Disk full → red error card with actionable fix

## 13. Risks

| Risk | Mitigation |
|---|---|
| `jq` not on VM | Use `python3 -c` (guaranteed) |
| Two app instances racing on `jobs.json` | `.jobs.lock` file + `flock` where available |
| `QSplitter` collapses to 0 | `setMinimumWidth(380)` on panel |
| Avatar fetch blocks UI | async `QNetworkAccessManager` + disk cache |
| Reattach tail sees rotated log | `tail -n +1 -f` from start; accept repeated last lines |
| User closes panel during install | Install continues; panel reopens in Mode C automatically |
| `pipeline_tag` filter returns fewer than expected | Fallback: keep "All" as default; user can widen |

## 14. Open questions

None at time of writing. Brainstorm resolved:
- Persistence: reattach to remote SSH process (state files on VM).
- Panel: permanent split view.
- Filters: hybrid `pipeline_tag` + client-side heuristic; limit 100.
- Lock: per-instance.
- Confirmations: one pre-deploy confirm + transparent progress UI.

## 15. Next step

Invoke `superpowers:writing-plans` to produce an ordered implementation plan that can be executed incrementally (recommended phasing: filters/pagination fix → card redesign → side panel shell → job registry + persistence → reattach flow → polish).
