# Model Store Side Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Deployment Studio modal with a persistent right-side panel in Discover, fix the 20-model search cap + broken category filter, and add durable install-job state that reattaches to the running remote SSH process after an app restart.

**Architecture:** A new `JobRegistry` QObject owns install-job state (in-memory + `~/.vastai-app/jobs.json`) and enforces a per-instance lock. Remote install scripts write JSON state files so a new `RemoteJobProbe` worker can classify each job as RUNNING/DONE/STALE/MISSING on boot and reattach via `tail -f`. `DiscoverView` switches to a `QSplitter` with a new `InstallPanelSide` widget on the right; `ModelDetailsDialog` and the legacy full-page `InstallPanel` are removed.

**Tech Stack:** Python 3, PySide6 (Qt 6), pytest + pytest-qt, requests, SSH via existing `SSHService`, `StreamingRemoteWorker`, `progress_parsers`.

**Related documents:**
- Spec: `docs/superpowers/specs/2026-04-19-model-store-side-panel-design.md`
- Partial supersede: Tasks 12, 13, 14 of `docs/superpowers/plans/2026-04-19-ai-lab-studio-revamp.md`

---

## Conventions

- **TDD cadence:** write failing test → run it → implement → run it → commit. Each commit is self-contained and passes every existing test.
- **Commit style:** `feat|fix|refactor|test|docs: short imperative` (same as recent commits in main).
- **Test location:** `tests/lab/` mirrors `app/lab/`; UI component tests use the existing `qt_app` fixture in `tests/lab/conftest.py`.
- **No `jq` on the VM** — always use `python3 -c` for JSON parsing in remote scripts.
- **Windows path note:** This repo is developed on Windows. All `git`/`pytest` commands run from the repo root `C:\Users\Pc_Lu\Desktop\vastai-app` via the bash available in WSL/Git Bash.

---

## File Structure

```
app/lab/
├── services/
│   ├── job_registry.py          # NEW — JobRegistry QObject + persistence
│   ├── huggingface.py           # MOD — pipeline_tag, limit, return cursor
│   └── remote_setup.py          # MOD — write_state helper, check_job, cancel_job
├── state/
│   └── models.py                # MOD — + JobDescriptor dataclass
├── workers/
│   ├── huggingface_worker.py    # MOD — accepts pipeline_tag
│   └── remote_job_probe.py      # NEW — SSH probe with RUNNING/DONE/STALE/MISSING
└── views/
    ├── discover_view.py         # MOD — QSplitter, filter rewrite, pagination, card extract
    ├── install_panel_side.py    # NEW — right-side panel, Mode A/B/C
    ├── model_details_dialog.py  # DELETE
    └── install_panel.py         # DELETE

app/ui/components/
├── model_card.py                # NEW — card w/ default/hover/selected/installed/installing
└── install_progress.py          # NEW — bar + stage checklist + collapsible log

app/ui/app_shell.py              # MOD — JobRegistry init, reattach wiring, route removal

tests/lab/
├── services/
│   ├── test_job_registry.py     # NEW
│   ├── test_huggingface.py      # NEW (or MOD if exists)
│   └── test_remote_setup_jobs.py# NEW
├── workers/
│   └── test_remote_job_probe.py # NEW
└── views/
    ├── test_discover_filters.py # NEW
    └── test_install_panel_side.py # NEW
```

---

## Phase 1 — HuggingFace client, filters, pagination

### Task 1: `HuggingFaceClient.search_gguf_models` accepts `pipeline_tag` and returns cursor

**Files:**
- Modify: `app/lab/services/huggingface.py`
- Test: `tests/lab/services/test_huggingface.py` (new file)

- [ ] **Step 1.1: Write the failing test**

Create `tests/lab/services/__init__.py` (empty) if it doesn't exist, then create `tests/lab/services/test_huggingface.py`:

```python
from unittest.mock import patch, Mock
from app.lab.services.huggingface import HuggingFaceClient


def _fake_response(payload, link_header=None):
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.headers = {"Link": link_header} if link_header else {}
    resp.raise_for_status = Mock()
    return resp


def test_search_passes_pipeline_tag_and_limit():
    client = HuggingFaceClient()
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response([])
        client.search_gguf_models(query="llama", limit=100, pipeline_tag="text-generation")
        args, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert params["pipeline_tag"] == "text-generation"
        assert params["limit"] == 100
        assert params["search"] == "llama"
        assert params["filter"] == "gguf"


def test_search_omits_pipeline_tag_when_none():
    client = HuggingFaceClient()
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response([])
        client.search_gguf_models(query="", limit=50, pipeline_tag=None)
        params = mock_get.call_args.kwargs["params"]
        assert "pipeline_tag" not in params
        assert params["limit"] == 50


def test_search_returns_models_and_cursor():
    client = HuggingFaceClient()
    payload = [{
        "id": "bartowski/Meta-Llama-3-8B-Instruct-GGUF",
        "downloads": 12345, "likes": 42,
        "tags": ["gguf", "llama"],
        "siblings": [
            {"rfilename": "meta-llama-3-8b-instruct-Q4_K_M.gguf", "size": 4700000000},
        ],
    }]
    link = '<https://huggingface.co/api/models?cursor=XYZ>; rel="next"'
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response(payload, link_header=link)
        models, cursor = client.search_gguf_models(query="llama")
        assert len(models) == 1
        assert models[0].id == "bartowski/Meta-Llama-3-8B-Instruct-GGUF"
        assert cursor == "XYZ"
        assert models[0].files[0].quantization == "Q4_K_M"


def test_search_returns_none_cursor_when_no_link_header():
    client = HuggingFaceClient()
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response([])
        _, cursor = client.search_gguf_models()
        assert cursor is None
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run: `pytest tests/lab/services/test_huggingface.py -v`
Expected: FAIL — current return type is `list`, not `tuple`.

- [ ] **Step 1.3: Update `HuggingFaceClient.search_gguf_models`**

Replace the method in `app/lab/services/huggingface.py`:

```python
    def search_gguf_models(
        self,
        query: str = "",
        limit: int = 100,
        pipeline_tag: str | None = None,
        cursor: str | None = None,
    ) -> tuple[list[HFModel], str | None]:
        """Search GGUF models on Hugging Face.

        Returns (models, next_cursor) where next_cursor is the HF API cursor
        for the next page (None if no more pages)."""
        url = f"{self.BASE_URL}/models"
        params: dict[str, Any] = {
            "search": query,
            "filter": "gguf",
            "sort": "downloads",
            "direction": "-1",
            "limit": limit,
            "full": "True",
        }
        if pipeline_tag:
            params["pipeline_tag"] = pipeline_tag
        if cursor:
            params["cursor"] = cursor

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            models = []
            for item in data:
                model_id = item.get("id", "")
                parts = model_id.split("/")
                author = parts[0] if len(parts) > 1 else ""
                name = parts[1] if len(parts) > 1 else model_id

                files = []
                import re
                for sibling in item.get("siblings", []):
                    filename = sibling.get("rfilename", "")
                    if filename.endswith(".gguf"):
                        quant = ""
                        match = re.search(r'-(q\d_[k_a-z0-9]+)\.gguf$', filename.lower())
                        if match:
                            quant = match.group(1).upper()
                        files.append(HFModelFile(
                            filename=filename,
                            size_bytes=sibling.get("size") or sibling.get("lfs", {}).get("size", 0),
                            quantization=quant,
                        ))

                models.append(HFModel(
                    id=model_id,
                    author=author,
                    name=name,
                    downloads=item.get("downloads", 0),
                    likes=item.get("likes", 0),
                    tags=item.get("tags", []),
                    files=files,
                ))

            next_cursor = _parse_next_cursor(response.headers.get("Link"))
            return models, next_cursor
        except Exception as e:
            print(f"Error fetching from Hugging Face: {e}")
            return [], None
```

At the end of the file (outside the class), add the cursor parser:

```python
def _parse_next_cursor(link_header: str | None) -> str | None:
    """Extract the `cursor=…` value from a `rel="next"` Link header."""
    if not link_header:
        return None
    import re
    for part in link_header.split(","):
        if 'rel="next"' in part:
            m = re.search(r"cursor=([^&>\s]+)", part)
            if m:
                return m.group(1)
    return None
```

- [ ] **Step 1.4: Run the test to verify it passes**

Run: `pytest tests/lab/services/test_huggingface.py -v`
Expected: 4 passed.

- [ ] **Step 1.5: Run the full test suite to confirm nothing else broke**

Run: `pytest tests/lab -x -q`
Expected: all green (the method's signature changed from returning `list` to `tuple`, so any existing caller that unpacks a list will now fail — we fix those in Tasks 2–3).

**Known caller breakage to fix in Task 2:** `app/lab/workers/huggingface_worker.py:19` (`client.search_gguf_models(self.query, self.limit)` returns tuple now; worker emits `list`). Flag if the suite fails here and proceed.

- [ ] **Step 1.6: Commit**

```bash
git add app/lab/services/huggingface.py tests/lab/services/__init__.py tests/lab/services/test_huggingface.py
git commit -m "feat(hf): support pipeline_tag + cursor pagination in GGUF search

Return (models, next_cursor) tuple. Accept pipeline_tag and cursor
kwargs. Prepares for the Model Store side-panel revamp which needs
server-side category filtering and Load-more pagination."
```

---

### Task 2: `HFSearchWorker` accepts `pipeline_tag`, `cursor`, and emits cursor

**Files:**
- Modify: `app/lab/workers/huggingface_worker.py`
- Test: `tests/lab/workers/test_hf_search_worker.py` (new — dir exists)

- [ ] **Step 2.1: Write the failing test**

Create `tests/lab/workers/__init__.py` if missing, then `tests/lab/workers/test_hf_search_worker.py`:

```python
from unittest.mock import patch
from app.lab.workers.huggingface_worker import HFSearchWorker


def test_worker_forwards_pipeline_tag_and_cursor():
    with patch("app.lab.workers.huggingface_worker.HuggingFaceClient") as MockClient:
        instance = MockClient.return_value
        instance.search_gguf_models.return_value = ([], "NEXTCURSOR")
        w = HFSearchWorker(query="qwen", limit=100, pipeline_tag="text-generation", cursor="PREV")

        captured = {}
        def on_finished(models, cursor):
            captured["models"] = models
            captured["cursor"] = cursor
        w.finished.connect(on_finished)

        w.run()  # call synchronously in-thread for test

        instance.search_gguf_models.assert_called_once_with(
            query="qwen", limit=100, pipeline_tag="text-generation", cursor="PREV"
        )
        assert captured["cursor"] == "NEXTCURSOR"
        assert captured["models"] == []
```

- [ ] **Step 2.2: Run the test to verify it fails**

Run: `pytest tests/lab/workers/test_hf_search_worker.py -v`
Expected: FAIL — worker currently has no `pipeline_tag`/`cursor` kwargs and emits a single `list`.

- [ ] **Step 2.3: Rewrite the worker**

Replace `app/lab/workers/huggingface_worker.py` with:

```python
"""Worker for fetching Hugging Face models asynchronously."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from app.lab.services.huggingface import HuggingFaceClient


class HFSearchWorker(QThread):
    finished = Signal(list, object)  # list[HFModel], str | None (cursor)
    error = Signal(str)

    def __init__(
        self,
        query: str = "",
        limit: int = 100,
        pipeline_tag: str | None = None,
        cursor: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.query = query
        self.limit = limit
        self.pipeline_tag = pipeline_tag
        self.cursor = cursor
        self.client = HuggingFaceClient()

    def run(self):
        try:
            models, next_cursor = self.client.search_gguf_models(
                query=self.query,
                limit=self.limit,
                pipeline_tag=self.pipeline_tag,
                cursor=self.cursor,
            )
            self.finished.emit(models, next_cursor)
        except Exception as e:
            self.error.emit(str(e))
```

- [ ] **Step 2.4: Run the test to verify it passes**

Run: `pytest tests/lab/workers/test_hf_search_worker.py -v`
Expected: PASS.

- [ ] **Step 2.5: Commit**

```bash
git add app/lab/workers/huggingface_worker.py tests/lab/workers/test_hf_search_worker.py
git commit -m "feat(hf-worker): support pipeline_tag + cursor + emit next cursor

finished signal now has (models, cursor) so the Discover view can
drive Load-more pagination."
```

---

### Task 3: Rewrite `DiscoverView._search` with `CATEGORY_MAP` and client-side heuristics

**Files:**
- Modify: `app/lab/views/discover_view.py`
- Test: `tests/lab/views/test_discover_filters.py` (new)

- [ ] **Step 3.1: Write the failing test**

Create `tests/lab/views/__init__.py` if missing, then `tests/lab/views/test_discover_filters.py`:

```python
from dataclasses import dataclass
from app.lab.views.discover_view import (
    CATEGORY_MAP,
    apply_category_heuristic,
)
from app.lab.services.huggingface import HFModel


def _m(name, tags=None):
    return HFModel(
        id=f"author/{name}", author="author", name=name,
        downloads=0, likes=0, tags=tags or [], files=[],
    )


def test_category_map_has_all_required_entries():
    assert set(CATEGORY_MAP.keys()) == {
        "All", "General", "Coding", "Reasoning", "Chat", "Multimodal", "Embedding"
    }
    assert CATEGORY_MAP["Multimodal"]["pipeline"] == "image-text-to-text"
    assert CATEGORY_MAP["Embedding"]["pipeline"] == "feature-extraction"
    assert CATEGORY_MAP["All"]["pipeline"] is None


def test_heuristic_coding_matches_common_coder_names():
    models = [
        _m("Qwen2.5-Coder-14B-Instruct-GGUF"),
        _m("deepseek-coder-v2-lite-gguf"),
        _m("Meta-Llama-3-8B-Instruct-GGUF"),
        _m("starcoder2-15b-gguf"),
    ]
    result = apply_category_heuristic("Coding", models)
    names = [m.name for m in result]
    assert "Qwen2.5-Coder-14B-Instruct-GGUF" in names
    assert "deepseek-coder-v2-lite-gguf" in names
    assert "starcoder2-15b-gguf" in names
    assert "Meta-Llama-3-8B-Instruct-GGUF" not in names


def test_heuristic_reasoning_matches_r1_and_qwq():
    models = [
        _m("DeepSeek-R1-Distill-Qwen-7B-GGUF"),
        _m("Qwen-QwQ-32B-Preview-GGUF"),
        _m("Meta-Llama-3-8B-Instruct-GGUF"),
    ]
    result = apply_category_heuristic("Reasoning", models)
    names = [m.name for m in result]
    assert "DeepSeek-R1-Distill-Qwen-7B-GGUF" in names
    assert "Qwen-QwQ-32B-Preview-GGUF" in names
    assert "Meta-Llama-3-8B-Instruct-GGUF" not in names


def test_heuristic_all_passes_everything_through():
    models = [_m("A"), _m("B")]
    assert apply_category_heuristic("All", models) == models


def test_heuristic_multimodal_and_embedding_do_not_filter():
    # Pipeline already narrowed server-side; client-side heuristic is a no-op.
    models = [_m("X"), _m("Y")]
    assert apply_category_heuristic("Multimodal", models) == models
    assert apply_category_heuristic("Embedding", models) == models
```

- [ ] **Step 3.2: Run the test to verify it fails**

Run: `pytest tests/lab/views/test_discover_filters.py -v`
Expected: FAIL — `CATEGORY_MAP` and `apply_category_heuristic` don't exist yet.

- [ ] **Step 3.3: Add the module-level constants and helper to `discover_view.py`**

Add at the top of `app/lab/views/discover_view.py` (after existing imports, before `_FIT_LEVEL`):

```python
import re

CATEGORY_MAP: dict[str, dict] = {
    "All":        {"pipeline": None,                    "heuristic": None},
    "General":    {"pipeline": "text-generation",       "heuristic": None},
    "Coding":     {"pipeline": "text-generation",       "heuristic": "coding"},
    "Reasoning":  {"pipeline": "text-generation",       "heuristic": "reasoning"},
    "Chat":       {"pipeline": "text-generation",       "heuristic": "chat"},
    "Multimodal": {"pipeline": "image-text-to-text",    "heuristic": None},
    "Embedding":  {"pipeline": "feature-extraction",    "heuristic": None},
}

_CODING_RX    = re.compile(r"\b(coder?|starcoder?|deepseek[-_]?coder|qwen[-_]?coder|wizardcoder|codellama|codegemma)\b", re.I)
_REASONING_RX = re.compile(r"\b(r1|qwq|reasoner?|o1|phi[-_]?reason|deepseek[-_]?r)\b", re.I)
_CHAT_RX      = re.compile(r"\b(chat|instruct|sft|assistant|rp|roleplay)\b", re.I)

_HEURISTIC_RX = {
    "coding":    _CODING_RX,
    "reasoning": _REASONING_RX,
    "chat":      _CHAT_RX,
}


def apply_category_heuristic(category: str, models: list) -> list:
    """Client-side filter for categories not expressible via HF pipeline_tag.

    For General/Multimodal/Embedding/All this is a no-op; for Coding/Reasoning/Chat
    it narrows the list by regex over model name and tags."""
    cfg = CATEGORY_MAP.get(category)
    if not cfg or not cfg["heuristic"]:
        return models
    rx = _HEURISTIC_RX[cfg["heuristic"]]
    return [m for m in models if rx.search(m.name) or any(rx.search(t) for t in m.tags)]
```

- [ ] **Step 3.4: Run the test to verify it passes**

Run: `pytest tests/lab/views/test_discover_filters.py -v`
Expected: 5 passed.

- [ ] **Step 3.5: Rewrite `DiscoverView._search` to use the new contract**

In `app/lab/views/discover_view.py`, replace `_search` and `_on_search_finished`:

```python
    def _search(self, query: str = "", append: bool = False):
        if self.worker and self.worker.isRunning():
            return

        term = query if isinstance(query, str) and query else self.search_input.text().strip()
        category = self.filter.currentText()
        cfg = CATEGORY_MAP.get(category, CATEGORY_MAP["All"])

        self._append_mode = append
        cursor = self._next_cursor if append else None

        self.progress.setVisible(True)
        self.search_btn.setEnabled(False)
        self.search_input.setEnabled(False)
        if append:
            self.status_lbl.setText("Loading more…")
        else:
            desc = f"'{term}'" if term else "GGUF models"
            self.status_lbl.setText(f"Searching Hugging Face for {desc}…")

        self.worker = HFSearchWorker(
            query=term,
            limit=100,
            pipeline_tag=cfg["pipeline"],
            cursor=cursor,
            parent=self,
        )
        self.worker.finished.connect(self._on_search_finished)
        self.worker.error.connect(self._on_search_error)
        self.worker.start()

    def _on_search_finished(self, models: list, next_cursor):
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self.search_input.setEnabled(True)

        if self._append_mode:
            self.current_models.extend(models)
        else:
            self.current_models = list(models)

        self._next_cursor = next_cursor

        if not self.current_models:
            self.status_lbl.setText("No GGUF models found for that search term.")
        else:
            more = " (more available)" if next_cursor else ""
            self.status_lbl.setText(f"Loaded {len(self.current_models)} models{more}.")

        self._render()
```

In `__init__`, initialise the new attributes (right after `self.current_models = []`):

```python
        self._next_cursor: str | None = None
        self._append_mode: bool = False
```

Also update the import at the top if not already present:

```python
from app.lab.views.discover_view  # (self-import not needed; this line is just a reminder)
```

No new import needed inside `discover_view.py` — `CATEGORY_MAP` and `HFSearchWorker` are already in-module.

- [ ] **Step 3.6: Run the full suite to catch callers**

Run: `pytest tests/lab -x -q`
Expected: existing tests may fail if they mocked `HFSearchWorker.finished` as a single-arg signal. If `tests/lab/test_discover_view_scoring.py` breaks, inspect and update the mock — the signal is now `(list, object)`.

- [ ] **Step 3.7: Commit**

```bash
git add app/lab/views/discover_view.py tests/lab/views/__init__.py tests/lab/views/test_discover_filters.py
git commit -m "fix(discover): stop concatenating category into HF query

Introduce CATEGORY_MAP with pipeline_tag passthrough for Multimodal
and Embedding; client-side regex for Coding/Reasoning/Chat. Remove
the old 'query + filter-text' concat that polluted searches. Raise
default result limit to 100."
```

---

### Task 4: "Load more" pagination button in `DiscoverView`

**Files:**
- Modify: `app/lab/views/discover_view.py`

- [ ] **Step 4.1: Add the Load-more button to the content widget**

In `DiscoverView.__init__`, after `content_lay.addWidget(self.scroll, 1)`, add:

```python
        self.load_more_btn = QPushButton("Load more")
        self.load_more_btn.setVisible(False)
        self.load_more_btn.clicked.connect(lambda: self._search(append=True))
        content_lay.addWidget(self.load_more_btn, 0, Qt.AlignCenter)
```

- [ ] **Step 4.2: Toggle its visibility at the end of `_render`**

In `_render`, after the final `self.list_lay.addStretch()`, add:

```python
        self.load_more_btn.setVisible(bool(self._next_cursor))
```

- [ ] **Step 4.3: Manual smoke check**

Run: `python -m app` (or the app's existing entry-point script). Search `llama`. Scroll to the bottom. Confirm a **Load more** button appears and clicking it appends results without blanking the list. Close the app.

- [ ] **Step 4.4: Commit**

```bash
git add app/lab/views/discover_view.py
git commit -m "feat(discover): add Load-more pagination via HF cursor

Accumulates models as the user clicks through, shows the button only
when the previous search returned a next-cursor."
```

---

## Phase 2 — JobRegistry + JobDescriptor

### Task 5: `JobDescriptor` dataclass + `build_job_key` helper

**Files:**
- Modify: `app/lab/state/models.py`
- Test: `tests/lab/state/test_job_descriptor.py` (new; `tests/lab/state/` may need creation)

- [ ] **Step 5.1: Write the failing test**

Create `tests/lab/state/__init__.py` if missing, then `tests/lab/state/test_job_descriptor.py`:

```python
from app.lab.state.models import JobDescriptor, build_job_key


def test_build_key_slugifies_repo_and_appends_quant():
    k = build_job_key(
        iid=35273157,
        repo_id="bartowski/Meta-Llama-3-8B-Instruct-GGUF",
        quant="Q5_K_M",
    )
    # Slash → dash, lowercase, then "-<quant lowercase>"
    assert k == "35273157-bartowski-meta-llama-3-8b-instruct-gguf-q5_k_m"


def test_job_descriptor_defaults_and_init():
    d = JobDescriptor(
        key="35273157-x-q4",
        iid=35273157,
        repo_id="x/y",
        filename="y-Q4_K_M.gguf",
        quant="Q4_K_M",
        size_bytes=5_300_000_000,
        needs_llamacpp=True,
        remote_state_path="/workspace/.vastai-app/jobs/35273157-x-q4.json",
        remote_log_path="/tmp/install-35273157-x-q4.log",
        started_at=1_700_000_000.0,
    )
    assert d.stage == "starting"
    assert d.percent == 0
    assert d.bytes_downloaded == 0
    assert d.speed == ""
    assert d.error is None
```

- [ ] **Step 5.2: Run test — expect failure**

Run: `pytest tests/lab/state/test_job_descriptor.py -v`
Expected: FAIL — neither `JobDescriptor` nor `build_job_key` exist.

- [ ] **Step 5.3: Add the dataclass and helper to `app/lab/state/models.py`**

Append at the bottom of `app/lab/state/models.py`:

```python
@dataclass
class JobDescriptor:
    """Durable descriptor for an install/download job running on a remote instance."""
    key: str
    iid: int
    repo_id: str
    filename: str
    quant: str
    size_bytes: int
    needs_llamacpp: bool
    remote_state_path: str
    remote_log_path: str
    started_at: float
    stage: str = "starting"           # starting|apt|clone|cmake|build|download|verify|done|failed|cancelled
    percent: int = 0
    bytes_downloaded: int = 0
    speed: str = ""
    error: str | None = None


def build_job_key(iid: int, repo_id: str, quant: str) -> str:
    """Build a stable, filesystem-safe key for a job.

    Format: "{iid}-{slug(repo_id)}-{quant.lower()}"
    where slug replaces '/' with '-' and lowercases.
    """
    slug = repo_id.replace("/", "-").lower()
    return f"{iid}-{slug}-{quant.lower()}"
```

- [ ] **Step 5.4: Run test — expect pass**

Run: `pytest tests/lab/state/test_job_descriptor.py -v`
Expected: 2 passed.

- [ ] **Step 5.5: Commit**

```bash
git add app/lab/state/models.py tests/lab/state/__init__.py tests/lab/state/test_job_descriptor.py
git commit -m "feat(state): add JobDescriptor dataclass + build_job_key

Durable descriptor for install/download jobs — will be persisted to
~/.vastai-app/jobs.json and written as remote state files so the app
can reattach after restart."
```

---

### Task 6: `JobRegistry` in-memory API + signals

**Files:**
- Create: `app/lab/services/job_registry.py`
- Test: `tests/lab/services/test_job_registry.py`

- [ ] **Step 6.1: Write the failing test**

Create `tests/lab/services/test_job_registry.py`:

```python
import time

from app.lab.services.job_registry import JobRegistry
from app.lab.state.models import JobDescriptor


def _mk(iid: int, key_suffix: str = "a") -> JobDescriptor:
    key = f"{iid}-x-{key_suffix}"
    return JobDescriptor(
        key=key, iid=iid, repo_id="x/y", filename="f.gguf", quant="Q4_K_M",
        size_bytes=1000, needs_llamacpp=False,
        remote_state_path=f"/tmp/{key}.json",
        remote_log_path=f"/tmp/{key}.log",
        started_at=time.time(),
    )


def test_empty_registry_allows_start():
    r = JobRegistry.in_memory()
    assert r.can_start(42) is True
    assert r.active_for(42) is None
    assert r.active_items() == []


def test_start_job_locks_instance_and_emits_signal(qtbot):
    r = JobRegistry.in_memory()
    desc = _mk(42)
    with qtbot.waitSignal(r.job_started, timeout=500) as blocker:
        r.start_job(desc)
    assert blocker.args == [desc.key]
    assert r.can_start(42) is False
    assert r.active_for(42).key == desc.key


def test_different_instances_are_independent():
    r = JobRegistry.in_memory()
    r.start_job(_mk(1))
    assert r.can_start(1) is False
    assert r.can_start(2) is True


def test_update_emits_job_updated(qtbot):
    r = JobRegistry.in_memory()
    desc = _mk(7)
    r.start_job(desc)
    with qtbot.waitSignal(r.job_updated, timeout=500) as blocker:
        r.update(desc.key, stage="download", percent=43)
    assert blocker.args == [desc.key]
    assert r.active_for(7).stage == "download"
    assert r.active_for(7).percent == 43


def test_finish_releases_lock_and_emits(qtbot):
    r = JobRegistry.in_memory()
    desc = _mk(7)
    r.start_job(desc)
    with qtbot.waitSignal(r.job_finished, timeout=500) as blocker:
        r.finish(desc.key, ok=True)
    assert blocker.args == [desc.key, True]
    assert r.can_start(7) is True


def test_drop_silently_removes_missing_job():
    r = JobRegistry.in_memory()
    desc = _mk(9)
    r.start_job(desc)
    r.drop(desc.key)
    assert r.can_start(9) is True
```

- [ ] **Step 6.2: Run — expect fail**

Run: `pytest tests/lab/services/test_job_registry.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 6.3: Create `app/lab/services/job_registry.py`**

```python
"""JobRegistry — durable tracker for install/download jobs.

This module defines the in-memory API + signals only. Persistence
(to ~/.vastai-app/jobs.json) is added in Task 7 as a mix-in layer.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import Iterable

from PySide6.QtCore import QObject, Signal

from app.lab.state.models import JobDescriptor


class JobRegistry(QObject):
    job_started    = Signal(str)        # key
    job_updated    = Signal(str)        # key
    job_finished   = Signal(str, bool)  # key, ok
    job_reattached = Signal(str)        # key

    def __init__(self, persist_path: str | None = None, parent=None):
        super().__init__(parent)
        self._active: dict[int, JobDescriptor] = {}
        self._by_key: dict[str, JobDescriptor] = {}
        self._recent: list[JobDescriptor] = []  # last 20 finished, for UI history
        self._persist_path = persist_path  # None in tests ("in_memory")

    # --- constructors -------------------------------------------------

    @classmethod
    def in_memory(cls, parent=None) -> "JobRegistry":
        return cls(persist_path=None, parent=parent)

    # --- read API -----------------------------------------------------

    def can_start(self, iid: int) -> bool:
        return iid not in self._active

    def active_for(self, iid: int) -> JobDescriptor | None:
        return self._active.get(iid)

    def active_items(self) -> list[tuple[str, JobDescriptor]]:
        return [(d.key, d) for d in self._active.values()]

    def get(self, key: str) -> JobDescriptor | None:
        return self._by_key.get(key)

    # --- mutate API ---------------------------------------------------

    def start_job(self, desc: JobDescriptor) -> None:
        if desc.iid in self._active:
            raise RuntimeError(f"Instance {desc.iid} already has an active job")
        self._active[desc.iid] = desc
        self._by_key[desc.key] = desc
        self._save_if_needed()
        self.job_started.emit(desc.key)

    def update(self, key: str, **fields) -> None:
        desc = self._by_key.get(key)
        if desc is None:
            return
        new_desc = replace(desc, **fields)
        self._active[desc.iid] = new_desc
        self._by_key[key] = new_desc
        self._save_if_needed()
        self.job_updated.emit(key)

    def finish(self, key: str, ok: bool, error: str | None = None) -> None:
        desc = self._by_key.get(key)
        if desc is None:
            return
        final_stage = "done" if ok else (desc.stage if desc.stage == "cancelled" else "failed")
        final = replace(desc, stage=final_stage, error=error if not ok else None)
        self._active.pop(desc.iid, None)
        self._by_key.pop(key, None)
        self._recent.append(final)
        if len(self._recent) > 20:
            self._recent = self._recent[-20:]
        self._save_if_needed()
        self.job_finished.emit(key, ok)

    def drop(self, key: str) -> None:
        desc = self._by_key.pop(key, None)
        if desc is None:
            return
        self._active.pop(desc.iid, None)
        self._save_if_needed()

    def mark_reattached(self, key: str) -> None:
        if key in self._by_key:
            self.job_reattached.emit(key)

    # --- persistence hooks (filled in in Task 7) ----------------------

    def _save_if_needed(self) -> None:
        """No-op in the in-memory registry. Persistent subclass overrides."""

    # Helpers for persistence layer in Task 7.
    def _serialize(self) -> dict:
        return {
            "active_jobs": {str(d.iid): asdict(d) for d in self._active.values()},
            "completed_recent": [asdict(d) for d in self._recent],
        }

    def _hydrate(self, payload: dict) -> None:
        self._active.clear()
        self._by_key.clear()
        self._recent.clear()
        for _iid_str, raw in (payload.get("active_jobs") or {}).items():
            desc = JobDescriptor(**raw)
            self._active[desc.iid] = desc
            self._by_key[desc.key] = desc
        for raw in payload.get("completed_recent") or []:
            self._recent.append(JobDescriptor(**raw))
```

- [ ] **Step 6.4: Run — expect pass**

Run: `pytest tests/lab/services/test_job_registry.py -v`
Expected: 6 passed.

- [ ] **Step 6.5: Commit**

```bash
git add app/lab/services/job_registry.py tests/lab/services/test_job_registry.py
git commit -m "feat(job-registry): in-memory API with per-instance lock

Exposes can_start/active_for/start_job/update/finish/drop + four
signals. Persistence layer comes in the next commit."
```

---

### Task 7: `JobRegistry` persistence (atomic write + load + lock)

**Files:**
- Modify: `app/lab/services/job_registry.py`
- Test: extend `tests/lab/services/test_job_registry.py`

- [ ] **Step 7.1: Add failing tests for persistence**

Append to `tests/lab/services/test_job_registry.py`:

```python
import json
import os
from pathlib import Path


def test_save_writes_atomically(tmp_path):
    path = tmp_path / "jobs.json"
    r = JobRegistry(persist_path=str(path))
    r.start_job(_mk(11))
    assert path.exists()
    # tmp should be gone (atomic replace)
    assert not path.with_suffix(".json.tmp").exists()
    data = json.loads(path.read_text())
    assert "active_jobs" in data
    assert "11" in data["active_jobs"]


def test_load_from_disk_restores_active_jobs(tmp_path):
    path = tmp_path / "jobs.json"
    r1 = JobRegistry(persist_path=str(path))
    desc = _mk(99, "zz")
    r1.start_job(desc)

    r2 = JobRegistry(persist_path=str(path))
    r2.load_from_disk()
    assert r2.can_start(99) is False
    assert r2.active_for(99).key == desc.key


def test_load_from_disk_handles_missing_file(tmp_path):
    path = tmp_path / "jobs.json"  # does not exist
    r = JobRegistry(persist_path=str(path))
    r.load_from_disk()  # must not raise
    assert r.active_items() == []


def test_load_from_disk_handles_corrupt_file(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("{{{ not json")
    r = JobRegistry(persist_path=str(path))
    r.load_from_disk()  # must not raise
    assert r.active_items() == []


def test_finish_persists_state(tmp_path):
    path = tmp_path / "jobs.json"
    r = JobRegistry(persist_path=str(path))
    desc = _mk(3)
    r.start_job(desc)
    r.finish(desc.key, ok=True)

    data = json.loads(path.read_text())
    assert data["active_jobs"] == {}
    assert len(data["completed_recent"]) == 1
    assert data["completed_recent"][0]["key"] == desc.key
```

- [ ] **Step 7.2: Run — expect fail**

Run: `pytest tests/lab/services/test_job_registry.py -v`
Expected: new 5 tests FAIL — `_save_if_needed` is a no-op; `load_from_disk` doesn't exist.

- [ ] **Step 7.3: Implement persistence in `job_registry.py`**

Replace `_save_if_needed` and add `load_from_disk`/`save` in `app/lab/services/job_registry.py`:

```python
    # --- persistence --------------------------------------------------

    def _save_if_needed(self) -> None:
        if self._persist_path is None:
            return
        self.save()

    def save(self) -> None:
        """Atomic write: serialize → .tmp → os.replace → .json."""
        if self._persist_path is None:
            return
        import json, os, pathlib
        path = pathlib.Path(self._persist_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = self._serialize()
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(str(tmp), str(path))

    def load_from_disk(self) -> None:
        """Hydrate active_jobs + recent from disk. Silent on missing/corrupt file."""
        if self._persist_path is None:
            return
        import json, pathlib
        path = pathlib.Path(self._persist_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text())
        except Exception as e:
            print(f"JobRegistry.load_from_disk: ignoring corrupt file ({e})")
            return
        self._hydrate(payload)
```

- [ ] **Step 7.4: Run — expect pass**

Run: `pytest tests/lab/services/test_job_registry.py -v`
Expected: 11 passed.

- [ ] **Step 7.5: Commit**

```bash
git add app/lab/services/job_registry.py tests/lab/services/test_job_registry.py
git commit -m "feat(job-registry): atomic persistence to ~/.vastai-app/jobs.json

Write-to-tmp then os.replace; load_from_disk is fault-tolerant to
missing or corrupt files. finish/update also persist."
```

---

### Task 8: Instantiate `JobRegistry` in `AppShell`, load on startup

**Files:**
- Modify: `app/ui/app_shell.py`

- [ ] **Step 8.1: Add the registry to `AppShell.__init__`**

In `app/ui/app_shell.py`, add the import at the top:

```python
from app.lab.services.job_registry import JobRegistry
```

In `AppShell.__init__`, immediately after `self.store = LabStore(self)`, add:

```python
        import pathlib
        jobs_path = pathlib.Path.home() / ".vastai-app" / "jobs.json"
        self.job_registry = JobRegistry(persist_path=str(jobs_path), parent=self)
        self.job_registry.load_from_disk()
```

- [ ] **Step 8.2: Verify the app still boots**

Run: `python -m app` (or the repo's launcher). App should open normally; close it.
If there's a pre-existing `~/.vastai-app/jobs.json` from development, the load is silent — no change visible yet.

- [ ] **Step 8.3: Commit**

```bash
git add app/ui/app_shell.py
git commit -m "feat(shell): create JobRegistry and load persisted jobs on startup

Registry will be wired to Discover and install flow in later commits."
```

---

## Phase 3 — Remote scripts

### Task 9: `write_state` helper and job-aware `script_install_llamacpp` + `script_download_model`

**Files:**
- Modify: `app/lab/services/remote_setup.py`
- Test: `tests/lab/services/test_remote_setup_jobs.py` (new)

- [ ] **Step 9.1: Write the failing test**

Create `tests/lab/services/test_remote_setup_jobs.py`:

```python
import subprocess
import os

from app.lab.services.remote_setup import (
    script_install_llamacpp,
    script_download_model,
)


def _bash_syntax_check(script: str):
    """Fail if bash -n rejects the script (Windows: requires WSL or Git Bash)."""
    try:
        r = subprocess.run(
            ["bash", "-n", "-c", script],
            capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        # No bash — skip (Windows dev without Git Bash). CI will still run this.
        import pytest
        pytest.skip("bash not available for -n syntax check")
    assert r.returncode == 0, f"bash -n failed:\n{r.stderr}"


def test_install_llamacpp_accepts_job_key_and_writes_state():
    s = script_install_llamacpp(job_key="iid-x-q")
    assert "write_state" in s
    assert "/workspace/.vastai-app/jobs/iid-x-q.json" in s
    assert "write_state apt" in s
    assert "write_state clone" in s
    assert "write_state cmake" in s
    assert "write_state build" in s
    assert "write_state done 100" in s
    _bash_syntax_check(s)


def test_install_llamacpp_without_job_key_keeps_legacy_output():
    s = script_install_llamacpp()  # backward-compatible
    assert "INSTALL_LLAMACPP_DONE" in s
    _bash_syntax_check(s)


def test_download_model_accepts_job_key_and_writes_state():
    s = script_download_model(
        repo_id="bartowski/Meta-Llama-3-8B-Instruct-GGUF",
        filename="meta-llama-3-8b-instruct-Q4_K_M.gguf",
        job_key="iid-y-q",
    )
    assert "/workspace/.vastai-app/jobs/iid-y-q.json" in s
    assert "write_state download" in s
    assert "write_state done 100" in s
    _bash_syntax_check(s)
```

- [ ] **Step 9.2: Run — expect fail**

Run: `pytest tests/lab/services/test_remote_setup_jobs.py -v`
Expected: FAIL — functions don't accept `job_key`.

- [ ] **Step 9.3: Add the helper constant and update the two script builders**

At the top of `app/lab/services/remote_setup.py` (after the docstring):

```python
_WRITE_STATE_HELPER = r"""
JOB_STATE="$1"   # path to jobs/<key>.json
JOB_LOG="$2"     # path to /tmp/install-<key>.log
mkdir -p "$(dirname "$JOB_STATE")"
write_state() {
  local stage="$1"
  local pct="${2:-0}"
  local bytes="${3:-0}"
  python3 - "$JOB_STATE" "$stage" "$pct" "$bytes" <<'PYEOF'
import json, os, sys, time
path, stage, pct, bytes_d = sys.argv[1:5]
json.dump(
    {"pid": os.getpid(), "stage": stage,
     "percent": int(pct or 0),
     "bytes_downloaded": int(bytes_d or 0),
     "updated_at": int(time.time())},
    open(path, "w"),
)
PYEOF
}
"""
```

Replace `script_install_llamacpp` to optionally accept `job_key`:

```python
def script_install_llamacpp(job_key: str | None = None) -> str:
    if job_key is None:
        return _script_install_llamacpp_legacy()

    state = f"/workspace/.vastai-app/jobs/{job_key}.json"
    log = f"/tmp/install-{job_key}.log"
    return (
        "bash -c '\n"
        "set -o pipefail\n"
        f'bash -c "$(cat <<\\BOOT\n'
        f'STATE_PATH={state}\n'
        f'LOG_PATH={log}\n'
        + _WRITE_STATE_HELPER.replace('"$1"', '"$STATE_PATH"').replace('"$2"', '"$LOG_PATH"') +
        "exec > >(tee -a \"$LOG_PATH\") 2>&1\n"
        "write_state apt 0\n"
        "apt-get update -qq && apt-get install -y -qq cmake build-essential git 2>/dev/null\n"
        "\n"
        "write_state clone 10\n"
        "if [ -d /opt/llama.cpp ]; then\n"
        "  cd /opt/llama.cpp\n"
        "  PULL_OUT=$(git pull 2>&1)\n"
        "  if echo \"$PULL_OUT\" | grep -q 'Already up to date' && [ -f build/bin/llama-server ]; then\n"
        "    write_state done 100\n"
        "    echo INSTALL_LLAMACPP_DONE\n"
        "    exit 0\n"
        "  fi\n"
        "else\n"
        "  git clone https://github.com/ggerganov/llama.cpp /opt/llama.cpp\n"
        "fi\n"
        "\n"
        "write_state cmake 30\n"
        "cd /opt/llama.cpp\n"
        "cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=native 2>&1\n"
        "\n"
        "write_state build 60\n"
        "cmake --build build --config Release -j$(nproc) -- llama-server llama-cli 2>&1\n"
        "\n"
        "if [ -f /opt/llama.cpp/build/bin/llama-server ]; then\n"
        "  write_state done 100\n"
        "  echo INSTALL_LLAMACPP_DONE\n"
        "else\n"
        "  write_state failed 0\n"
        "  echo INSTALL_LLAMACPP_FAILED\n"
        "fi\n"
        "BOOT\n"
        ")\n"
        "'"
    )


def _script_install_llamacpp_legacy() -> str:
    """Original (non-job-aware) install script. Kept for backward compat."""
    return r"""
echo "Installing llama.cpp with CUDA..."
apt-get update -qq && apt-get install -y -qq cmake build-essential git 2>/dev/null

if [ -d /opt/llama.cpp ]; then
    cd /opt/llama.cpp
    PULL_OUT=$(git pull 2>&1)
    if echo "$PULL_OUT" | grep -q "Already up to date" && [ -f build/bin/llama-server ]; then
        echo "LLAMACPP_ALREADY_UP_TO_DATE"
        echo "INSTALL_LLAMACPP_DONE"
        exit 0
    fi
else
    git clone https://github.com/ggerganov/llama.cpp /opt/llama.cpp
fi

cd /opt/llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=native 2>&1
cmake --build build --config Release -j$(nproc) -- llama-server llama-cli 2>&1

if [ -f /opt/llama.cpp/build/bin/llama-server ]; then
    echo "INSTALL_LLAMACPP_DONE"
    /opt/llama.cpp/build/bin/llama-server --version 2>/dev/null || true
else
    echo "INSTALL_LLAMACPP_FAILED"
fi
"""
```

> **Pragmatic simplification:** the triple-layered heredoc above is error-prone. A cleaner alternative, which Task 9.3 actually lands, uses a single heredoc `<<'EOF'` with literal `$$` expanded by the remote shell. **Use this simpler form instead:**

```python
def script_install_llamacpp(job_key: str | None = None) -> str:
    if job_key is None:
        return _script_install_llamacpp_legacy()

    state = f"/workspace/.vastai-app/jobs/{job_key}.json"
    log = f"/tmp/install-{job_key}.log"
    return f"""
mkdir -p /workspace/.vastai-app/jobs
STATE_PATH={state}
LOG_PATH={log}
exec > >(tee -a "$LOG_PATH") 2>&1

write_state() {{
  python3 - "$STATE_PATH" "$1" "${{2:-0}}" "${{3:-0}}" <<'PYEOF'
import json, os, sys, time
path, stage, pct, bytes_d = sys.argv[1:5]
json.dump({{"pid": os.getpid(), "stage": stage,
           "percent": int(pct or 0),
           "bytes_downloaded": int(bytes_d or 0),
           "updated_at": int(time.time())}},
          open(path, "w"))
PYEOF
}}

write_state apt 0
apt-get update -qq && apt-get install -y -qq cmake build-essential git 2>/dev/null

write_state clone 10
if [ -d /opt/llama.cpp ]; then
    cd /opt/llama.cpp
    PULL_OUT=$(git pull 2>&1)
    if echo "$PULL_OUT" | grep -q "Already up to date" && [ -f build/bin/llama-server ]; then
        write_state done 100
        echo INSTALL_LLAMACPP_DONE
        exit 0
    fi
else
    git clone https://github.com/ggerganov/llama.cpp /opt/llama.cpp
fi

write_state cmake 30
cd /opt/llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=native 2>&1

write_state build 60
cmake --build build --config Release -j$(nproc) -- llama-server llama-cli 2>&1

if [ -f /opt/llama.cpp/build/bin/llama-server ]; then
    write_state done 100
    echo INSTALL_LLAMACPP_DONE
else
    write_state failed 0
    echo INSTALL_LLAMACPP_FAILED
fi
"""
```

Replace `script_download_model` similarly — make `job_key` optional:

```python
def script_download_model(
    repo_id: str,
    filename: str,
    dest_dir: str = "/workspace",
    job_key: str | None = None,
) -> str:
    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    dest = f"{dest_dir}/{filename}"

    if job_key is None:
        return f"""
echo "Downloading {filename} from HuggingFace..."
mkdir -p "{dest_dir}"
cd "{dest_dir}"
if command -v wget &>/dev/null; then
    wget -c --progress=dot:giga -O "{dest}" "{url}" 2>&1
elif command -v curl &>/dev/null; then
    curl -L -C - -o "{dest}" "{url}" 2>&1
fi

if [ -f "{dest}" ]; then
    SIZE=$(stat -c%s "{dest}" 2>/dev/null || echo 0)
    echo "DOWNLOAD_DONE|{dest}|$SIZE"
else
    echo "DOWNLOAD_FAILED"
fi
"""

    state = f"/workspace/.vastai-app/jobs/{job_key}.json"
    log = f"/tmp/install-{job_key}.log"
    return f"""
mkdir -p /workspace/.vastai-app/jobs
STATE_PATH={state}
LOG_PATH={log}
exec > >(tee -a "$LOG_PATH") 2>&1

write_state() {{
  python3 - "$STATE_PATH" "$1" "${{2:-0}}" "${{3:-0}}" <<'PYEOF'
import json, os, sys, time
path, stage, pct, bytes_d = sys.argv[1:5]
json.dump({{"pid": os.getpid(), "stage": stage,
           "percent": int(pct or 0),
           "bytes_downloaded": int(bytes_d or 0),
           "updated_at": int(time.time())}},
          open(path, "w"))
PYEOF
}}

write_state download 0
mkdir -p "{dest_dir}"
cd "{dest_dir}"
wget -c --progress=dot:giga -O "{dest}" "{url}" 2>&1

if [ -f "{dest}" ]; then
    SIZE=$(stat -c%s "{dest}" 2>/dev/null || echo 0)
    write_state done 100 "$SIZE"
    echo "DOWNLOAD_DONE|{dest}|$SIZE"
else
    write_state failed 0
    echo "DOWNLOAD_FAILED"
fi
"""
```

- [ ] **Step 9.4: Run — expect pass**

Run: `pytest tests/lab/services/test_remote_setup_jobs.py -v`
Expected: 3 passed (syntax check may SKIP on Windows without Git Bash — that's acceptable; CI or Linux will run it).

- [ ] **Step 9.5: Commit**

```bash
git add app/lab/services/remote_setup.py tests/lab/services/test_remote_setup_jobs.py
git commit -m "feat(remote): job-aware install + download scripts with state file

Both functions now accept an optional job_key; when provided, the
script writes /workspace/.vastai-app/jobs/<key>.json at each stage
and tees stdout+stderr to /tmp/install-<key>.log. Existing callers
that pass no job_key continue to use the original scripts."
```

---

### Task 10: `script_check_job` and `script_cancel_job`

**Files:**
- Modify: `app/lab/services/remote_setup.py`
- Test: extend `tests/lab/services/test_remote_setup_jobs.py`

- [ ] **Step 10.1: Extend the test**

Append to `tests/lab/services/test_remote_setup_jobs.py`:

```python
from app.lab.services.remote_setup import (
    script_check_job,
    script_cancel_job,
    parse_check_job_output,
)


def test_check_job_script_references_state_file_and_python_parser():
    s = script_check_job("iid-x-q")
    assert "/workspace/.vastai-app/jobs/iid-x-q.json" in s
    assert "python3" in s
    assert "MISSING" in s
    assert "RUNNING" in s
    assert "DONE" in s
    assert "STALE" in s


def test_parse_check_job_output_running():
    raw = 'RUNNING\n{"pid": 123, "stage": "download", "percent": 43, "bytes_downloaded": 2000000000, "updated_at": 1700000000}\n'
    status, state = parse_check_job_output(raw)
    assert status == "RUNNING"
    assert state["pid"] == 123
    assert state["percent"] == 43


def test_parse_check_job_output_missing():
    status, state = parse_check_job_output("MISSING\n")
    assert status == "MISSING"
    assert state == {}


def test_parse_check_job_output_garbage():
    status, state = parse_check_job_output("kzxjv nonsense\n")
    assert status == "MISSING"
    assert state == {}


def test_cancel_job_kills_pid_and_removes_state():
    s = script_cancel_job("iid-x-q")
    assert "/workspace/.vastai-app/jobs/iid-x-q.json" in s
    assert "kill" in s
    assert "rm -f" in s
```

- [ ] **Step 10.2: Run — expect fail**

Run: `pytest tests/lab/services/test_remote_setup_jobs.py -v`
Expected: FAIL — new symbols don't exist.

- [ ] **Step 10.3: Add the functions to `app/lab/services/remote_setup.py`**

Append:

```python
def script_check_job(job_key: str) -> str:
    state = f"/workspace/.vastai-app/jobs/{job_key}.json"
    return f"""
STATE={state}
if [ ! -f "$STATE" ]; then
    echo "MISSING"
    exit 0
fi
PID=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pid',''))" "$STATE" 2>/dev/null)
STAGE=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('stage',''))" "$STATE" 2>/dev/null)
if [ "$STAGE" = "done" ]; then
    echo "DONE"
    cat "$STATE"
    exit 0
fi
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "RUNNING"
    cat "$STATE"
    exit 0
fi
echo "STALE"
cat "$STATE"
"""


def script_cancel_job(job_key: str) -> str:
    state = f"/workspace/.vastai-app/jobs/{job_key}.json"
    return f"""
STATE={state}
if [ -f "$STATE" ]; then
    PID=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pid',''))" "$STATE" 2>/dev/null)
    if [ -n "$PID" ]; then kill -TERM "$PID" 2>/dev/null || true; fi
    rm -f "$STATE"
    echo "CANCEL_OK"
else
    echo "CANCEL_NOOP"
fi
"""


def parse_check_job_output(output: str) -> tuple[str, dict]:
    """Parse `script_check_job` output into (status, state_dict).

    Status is one of RUNNING|DONE|STALE|MISSING. state_dict is the
    parsed JSON from the state file, or {} if the file was missing
    or unparsable."""
    import json
    lines = output.strip().splitlines()
    if not lines:
        return ("MISSING", {})
    status = lines[0].strip()
    if status not in {"RUNNING", "DONE", "STALE", "MISSING"}:
        return ("MISSING", {})
    if len(lines) < 2:
        return (status, {})
    try:
        state = json.loads("\n".join(lines[1:]))
        return (status, state if isinstance(state, dict) else {})
    except Exception:
        return (status, {})
```

- [ ] **Step 10.4: Run — expect pass**

Run: `pytest tests/lab/services/test_remote_setup_jobs.py -v`
Expected: 8 passed.

- [ ] **Step 10.5: Commit**

```bash
git add app/lab/services/remote_setup.py tests/lab/services/test_remote_setup_jobs.py
git commit -m "feat(remote): script_check_job + script_cancel_job + parser

check_job returns RUNNING|DONE|STALE|MISSING + JSON state. cancel_job
reads the PID from the state file, sends SIGTERM, removes the state.
parse_check_job_output gives a (status, dict) tuple for callers."
```

---

## Phase 4 — Side panel

### Task 11: `InstallPanelSide` skeleton with `set_model` and Mode A idle

**Files:**
- Create: `app/lab/views/install_panel_side.py`
- Test: `tests/lab/views/test_install_panel_side.py` (new)

- [ ] **Step 11.1: Write the failing test**

Create `tests/lab/views/test_install_panel_side.py`:

```python
from app.lab.views.install_panel_side import InstallPanelSide
from app.lab.services.job_registry import JobRegistry
from app.lab.services.huggingface import HFModel, HFModelFile
from app.lab.state.store import LabStore


def _make_panel(qtbot):
    store = LabStore()
    registry = JobRegistry.in_memory()
    panel = InstallPanelSide(store, registry)
    qtbot.addWidget(panel)
    return panel, store, registry


def test_panel_starts_in_idle_mode(qtbot):
    panel, _, _ = _make_panel(qtbot)
    assert panel.mode == "idle"
    assert panel.isVisibleTo(panel) or True  # panel constructed


def test_set_model_switches_to_mode_b(qtbot):
    panel, _, _ = _make_panel(qtbot)
    m = HFModel(id="x/y", author="x", name="y", downloads=0, likes=0,
                tags=[], files=[HFModelFile("y-Q4_K_M.gguf", 1000, "Q4_K_M")])
    panel.set_model(m)
    assert panel.mode == "ready"
    assert panel.current_model.id == "x/y"


def test_clear_returns_to_idle(qtbot):
    panel, _, _ = _make_panel(qtbot)
    m = HFModel(id="x/y", author="x", name="y", downloads=0, likes=0, tags=[], files=[])
    panel.set_model(m)
    panel.clear()
    assert panel.mode == "idle"
    assert panel.current_model is None
```

- [ ] **Step 11.2: Run — expect fail**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: ImportError — module doesn't exist.

- [ ] **Step 11.3: Create the panel skeleton**

```python
# app/lab/views/install_panel_side.py
"""Right-side install panel embedded in DiscoverView.

Three modes:
    idle  — no model selected; placeholder
    ready — model selected, no active job for it; show deploy pipeline
    busy  — model selected and has active job on some instance; show progress
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QStackedWidget, QPushButton, QHBoxLayout,
)

from app import theme as t
from app.lab.services.huggingface import HFModel


class InstallPanelSide(QWidget):
    # Bubbles up to DiscoverView → AppShell
    install_requested = Signal(int, str, str)  # iid, repo_id, filename
    setup_requested   = Signal(int)            # iid (bare llama.cpp setup)
    cancel_requested  = Signal(str)            # job key
    close_requested   = Signal()

    MODE_IDLE = "idle"
    MODE_READY = "ready"
    MODE_BUSY = "busy"

    def __init__(self, store, job_registry, parent=None):
        super().__init__(parent)
        self.store = store
        self.registry = job_registry
        self.current_model: HFModel | None = None
        self.mode: str = self.MODE_IDLE

        self.setMinimumWidth(380)
        self.setObjectName("InstallPanelSide")
        self.setStyleSheet(f"QWidget#InstallPanelSide {{ background: {t.BG_DEEP}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header with close button
        header = QHBoxLayout()
        header.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        title = QLabel("Deployment Studio")
        title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;")
        header.addWidget(title)
        header.addStretch()
        self.close_btn = QPushButton("\u2715")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("border: none; background: transparent; color: #888; font-size: 14px;")
        self.close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(self.close_btn)
        root.addLayout(header)

        # Content stack: idle | ready | busy (built in later tasks)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self._idle = self._build_idle()
        self.stack.addWidget(self._idle)            # index 0

        # Placeholders for later tasks — real widgets injected in Tasks 12/14/16.
        self._ready_placeholder = QLabel("(ready mode — Task 12)")
        self._ready_placeholder.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self._ready_placeholder)  # index 1

        self._busy_placeholder = QLabel("(busy mode — Task 14)")
        self._busy_placeholder.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self._busy_placeholder)   # index 2

        self._set_mode(self.MODE_IDLE)

    # --- public API ---------------------------------------------------

    def set_model(self, model: HFModel) -> None:
        self.current_model = model
        self._refresh()

    def clear(self) -> None:
        self.current_model = None
        self._set_mode(self.MODE_IDLE)

    # --- internals ----------------------------------------------------

    def _refresh(self) -> None:
        if self.current_model is None:
            self._set_mode(self.MODE_IDLE)
            return
        # Mode C trigger (see spec §7.3): active job matching this model on any instance?
        active_on_this_model = False
        for _key, desc in self.registry.active_items():
            if (desc.repo_id == self.current_model.id and
                    self._selected_quant_matches(desc)):
                active_on_this_model = True
                break
        self._set_mode(self.MODE_BUSY if active_on_this_model else self.MODE_READY)

    def _selected_quant_matches(self, desc) -> bool:
        # Task 12 adds a real quant combo; for now, any quant matches.
        return True

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        idx = {self.MODE_IDLE: 0, self.MODE_READY: 1, self.MODE_BUSY: 2}[mode]
        self.stack.setCurrentIndex(idx)

    def _build_idle(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        icon = QLabel("\U0001F4E6")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        msg = QLabel("Select a model from the left\nto see deployment options")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 13px;")
        lay.addWidget(icon)
        lay.addWidget(msg)
        return w
```

- [ ] **Step 11.4: Run — expect pass**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: 3 passed.

- [ ] **Step 11.5: Commit**

```bash
git add app/lab/views/install_panel_side.py tests/lab/views/test_install_panel_side.py
git commit -m "feat(panel): scaffold InstallPanelSide with idle/ready/busy modes

Idle mode renders a placeholder illustration. Ready and busy modes
are placeholder labels filled in by subsequent tasks. Mode selection
uses JobRegistry.active_items() to decide."
```

---

### Task 12: Mode "ready" — hero + quant dropdown

**Files:**
- Modify: `app/lab/views/install_panel_side.py`
- Test: extend `tests/lab/views/test_install_panel_side.py`

- [ ] **Step 12.1: Extend the test**

Append to `tests/lab/views/test_install_panel_side.py`:

```python
def test_ready_mode_renders_hero_and_quant_combo(qtbot):
    panel, _, _ = _make_panel(qtbot)
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=10, likes=5,
                tags=["gguf"],
                files=[
                    HFModelFile("b-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M"),
                    HFModelFile("b-Q8_0.gguf", 8_500_000_000, "Q8_0"),
                ])
    panel.set_model(m)
    # Hero label exists and shows the model name
    assert panel._hero_name.text() == "b-gguf"
    # Quant combo has 2 entries and Q4_K_M is selected by default
    assert panel._quant_combo.count() == 2
    assert "Q4_K_M" in panel._quant_combo.currentText()
```

- [ ] **Step 12.2: Run — expect fail**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: FAIL — `_hero_name` and `_quant_combo` don't exist.

- [ ] **Step 12.3: Replace the `_ready_placeholder` with a real widget**

In `app/lab/views/install_panel_side.py`, add the import at the top:

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QStackedWidget, QPushButton, QHBoxLayout,
    QComboBox, QScrollArea, QFrame,
)
```

Replace the "Placeholders for later tasks" section in `__init__` with:

```python
        self._ready = self._build_ready()
        self.stack.addWidget(self._ready)            # index 1

        self._busy_placeholder = QLabel("(busy mode — Task 14)")
        self._busy_placeholder.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self._busy_placeholder)  # index 2
```

Add the builder at the bottom of the class:

```python
    def _build_ready(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(t.SPACE_5, t.SPACE_4, t.SPACE_5, t.SPACE_4)
        lay.setSpacing(t.SPACE_4)

        # Hero: name + by author + stats
        hero = QFrame()
        hero.setStyleSheet(f"background: {t.SURFACE_1}; border-radius: 8px;")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        self._hero_name = QLabel("")
        self._hero_name.setStyleSheet(f"color: {t.TEXT_HERO}; font-size: 18px; font-weight: 800;")
        self._hero_name.setWordWrap(True)
        self._hero_author = QLabel("")
        self._hero_author.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 12px;")
        self._hero_stats = QLabel("")
        self._hero_stats.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 11px;")
        hl.addWidget(self._hero_name)
        hl.addWidget(self._hero_author)
        hl.addWidget(self._hero_stats)
        lay.addWidget(hero)

        # Quant selector
        lbl = QLabel("TARGET CONFIGURATION")
        lbl.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        lay.addWidget(lbl)
        self._quant_combo = QComboBox()
        self._quant_combo.currentIndexChanged.connect(lambda _: self._render_instance_cards())
        lay.addWidget(self._quant_combo)

        # Pipeline header
        pipe = QLabel("DEPLOYMENT PIPELINE")
        pipe.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; margin-top: 4px;")
        lay.addWidget(pipe)

        # Scrollable instance cards — filled by Task 13
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._instance_host = QWidget()
        self._instance_lay = QVBoxLayout(self._instance_host)
        self._instance_lay.setContentsMargins(0, 0, 0, 0)
        self._instance_lay.setSpacing(t.SPACE_3)
        scroll.setWidget(self._instance_host)
        lay.addWidget(scroll, 1)

        return w
```

Update `_refresh` to populate hero + quant combo when entering ready mode:

```python
    def _refresh(self) -> None:
        if self.current_model is None:
            self._set_mode(self.MODE_IDLE)
            return
        active_on_this_model = False
        for _key, desc in self.registry.active_items():
            if desc.repo_id == self.current_model.id:
                active_on_this_model = True
                break

        if active_on_this_model:
            self._set_mode(self.MODE_BUSY)
        else:
            self._populate_hero()
            self._populate_quants()
            self._render_instance_cards()
            self._set_mode(self.MODE_READY)

    def _populate_hero(self) -> None:
        m = self.current_model
        self._hero_name.setText(m.name)
        self._hero_author.setText(f"by {m.author}")
        p = f" \u2022 {m.params_b:.1f}B" if m.params_b > 0 else ""
        self._hero_stats.setText(f"\u2764\ufe0f {m.likes:,}   \u2193 {m.downloads:,}{p}")

    def _populate_quants(self) -> None:
        self._quant_combo.blockSignals(True)
        self._quant_combo.clear()
        files = sorted(self.current_model.files, key=lambda f: f.size_bytes)
        default_idx = 0
        for i, f in enumerate(files):
            size_gb = f.size_bytes / (1024**3) if f.size_bytes else 0
            label = f"{f.quantization or 'Unknown'} ({size_gb:.1f} GB)" if size_gb else (f.quantization or 'Unknown')
            self._quant_combo.addItem(label, f)
            if "Q4_K_M" in (f.quantization or "").upper():
                default_idx = i
        if files:
            self._quant_combo.setCurrentIndex(default_idx)
        self._quant_combo.blockSignals(False)

    def _render_instance_cards(self) -> None:
        # Filled by Task 13 — clear existing children first.
        while self._instance_lay.count():
            item = self._instance_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
```

- [ ] **Step 12.4: Run — expect pass**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: 4 passed.

- [ ] **Step 12.5: Commit**

```bash
git add app/lab/views/install_panel_side.py tests/lab/views/test_install_panel_side.py
git commit -m "feat(panel): ready mode hero + quant selector

Migrates the hero+config bar from ModelDetailsDialog into the side
panel. Instance cards still empty (Task 13)."
```

---

### Task 13: Mode "ready" — per-instance deployment cards (Ready + Busy)

**Files:**
- Modify: `app/lab/views/install_panel_side.py`
- Test: extend `tests/lab/views/test_install_panel_side.py`

- [ ] **Step 13.1: Extend the test**

Append:

```python
from app.lab.state.models import JobDescriptor, RemoteSystem, SetupStatus
import time as _time


def test_ready_mode_renders_ready_card_for_free_instance(qtbot):
    panel, store, _ = _make_panel(qtbot)
    store.set_instance(1)
    st = store.get_state(1)
    st.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    st.setup = SetupStatus(llamacpp_installed=True, probed=True)
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=1, likes=1,
                tags=[], files=[HFModelFile("b-Q4_K_M.gguf", 4_000_000_000, "Q4_K_M")])
    panel.set_model(m)
    # Exactly one instance card created
    cards = panel._instance_cards
    assert len(cards) == 1
    assert cards[0].iid == 1
    assert cards[0].busy is False


def test_ready_mode_renders_busy_card_when_other_job_active(qtbot):
    panel, store, registry = _make_panel(qtbot)
    store.set_instance(1)
    st = store.get_state(1)
    st.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    st.setup = SetupStatus(llamacpp_installed=True, probed=True)
    # Active job on iid=1 for a different repo
    registry.start_job(JobDescriptor(
        key="1-other-q4", iid=1, repo_id="other/repo", filename="f", quant="Q4_K_M",
        size_bytes=1, needs_llamacpp=False,
        remote_state_path="/tmp/s", remote_log_path="/tmp/l",
        started_at=_time.time(),
    ))
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=1, likes=1, tags=[],
                files=[HFModelFile("b-Q4_K_M.gguf", 1, "Q4_K_M")])
    panel.set_model(m)
    assert len(panel._instance_cards) == 1
    assert panel._instance_cards[0].busy is True


def test_deploy_click_emits_install_requested(qtbot):
    panel, store, _ = _make_panel(qtbot)
    store.set_instance(1)
    st = store.get_state(1)
    st.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    st.setup = SetupStatus(llamacpp_installed=True, probed=True)
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=1, likes=1, tags=[],
                files=[HFModelFile("b-Q4_K_M.gguf", 4_000_000_000, "Q4_K_M")])
    panel.set_model(m)
    with qtbot.waitSignal(panel.install_requested, timeout=500) as blocker:
        # Shortcut past the confirm overlay for this test — Task 14 tests the overlay flow.
        panel._request_install_for(1)
    assert blocker.args == [1, "a/b", "b-Q4_K_M.gguf"]
```

- [ ] **Step 13.2: Run — expect fail**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: FAIL on the three new tests.

- [ ] **Step 13.3: Add an `_InstanceCard` private class + populate logic**

In `app/lab/views/install_panel_side.py`, at module level below imports:

```python
class _InstanceCard(QFrame):
    """Small deployment card rendered inside the panel for one instance."""
    def __init__(self, iid: int, busy: bool, parent=None):
        super().__init__(parent)
        self.iid = iid
        self.busy = busy
```

Replace `_render_instance_cards` with the full implementation:

```python
    def _render_instance_cards(self) -> None:
        while self._instance_lay.count():
            item = self._instance_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._instance_cards: list[_InstanceCard] = []
        ids = self.store.all_instance_ids()
        if not ids:
            empty = QLabel("Connect an instance via Instances to deploy.")
            empty.setStyleSheet(f"color: {t.TEXT_MID}; font-style: italic; padding: {t.SPACE_4}px;")
            empty.setAlignment(Qt.AlignCenter)
            self._instance_lay.addWidget(empty)
            return

        selected_file = self._quant_combo.currentData()
        for iid in ids:
            state = self.store.get_state(iid)
            if not state or not state.system:
                continue
            active = self.registry.active_for(iid)
            busy_other_model = (active is not None and active.repo_id != self.current_model.id)
            card = self._build_instance_card(iid, state, selected_file, busy_other_model, active)
            self._instance_cards.append(card)
            self._instance_lay.addWidget(card)

        self._instance_lay.addStretch()

    def _build_instance_card(self, iid, state, selected_file, busy: bool, active_job) -> _InstanceCard:
        card = _InstanceCard(iid, busy)
        card.setStyleSheet(f"background: {t.SURFACE_1}; border-radius: 8px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)

        # Header line: #id · GPU · VRAM
        head = QLabel(f"Instance #{iid}")
        head.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 700;")
        lay.addWidget(head)
        gpu = QLabel(f"{state.system.gpu_name or 'Unknown GPU'} \u2022 {(state.system.gpu_vram_gb or 0):.1f}GB VRAM")
        gpu.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 11px;")
        lay.addWidget(gpu)

        if busy:
            warn = QLabel(f"\u26A0 BUSY with {active_job.filename}")
            warn.setStyleSheet(f"color: {t.WARN}; font-size: 12px; font-weight: 600; margin-top: 4px;")
            lay.addWidget(warn)
            return card

        # Buttons row
        btn_row = QHBoxLayout()
        if not state.setup.llamacpp_installed:
            env = QPushButton("Setup Environment")
            env.setProperty("role", "primary")
            env.clicked.connect(lambda _=False, i=iid: self.setup_requested.emit(i))
            btn_row.addWidget(env)

        deploy = QPushButton("Deploy Model")
        deploy.setFixedHeight(32)
        deploy.setStyleSheet(
            f"background: {t.ACCENT}; color: white; font-weight: 700;"
            "border-radius: 6px; padding: 0 12px;"
            if state.setup.llamacpp_installed else
            f"background: rgba(255,255,255,0.04); color: {t.TEXT_LOW};"
            f"border: 1px dashed {t.BORDER_LOW}; border-radius: 6px;"
        )
        deploy.setEnabled(state.setup.llamacpp_installed and selected_file is not None)
        deploy.setToolTip("Set up the environment first." if not state.setup.llamacpp_installed else "")
        deploy.clicked.connect(lambda _=False, i=iid: self._request_install_for(i))
        btn_row.addWidget(deploy)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        return card

    def _request_install_for(self, iid: int) -> None:
        """In Task 14 this opens the confirm overlay first; for now emit directly."""
        selected_file = self._quant_combo.currentData()
        if selected_file is None or self.current_model is None:
            return
        if not self.registry.can_start(iid):
            return
        self.install_requested.emit(iid, self.current_model.id, selected_file.filename)
```

- [ ] **Step 13.4: Run — expect pass**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: 7 passed.

- [ ] **Step 13.5: Commit**

```bash
git add app/lab/views/install_panel_side.py tests/lab/views/test_install_panel_side.py
git commit -m "feat(panel): render Ready/Busy instance cards in the side panel

Busy cards appear when JobRegistry.active_for(iid) exists for another
model. Deploy button emits install_requested directly (confirm overlay
arrives in the next commit)."
```

---

### Task 14: Inline confirm overlay

**Files:**
- Modify: `app/lab/views/install_panel_side.py`
- Test: extend `tests/lab/views/test_install_panel_side.py`

- [ ] **Step 14.1: Extend the test**

Append:

```python
def test_request_install_shows_confirm_overlay(qtbot):
    panel, store, _ = _make_panel(qtbot)
    store.set_instance(1)
    st = store.get_state(1)
    st.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    st.setup = SetupStatus(llamacpp_installed=True, probed=True)
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=1, likes=1, tags=[],
                files=[HFModelFile("b-Q4_K_M.gguf", 4_000_000_000, "Q4_K_M")])
    panel.set_model(m)
    panel.show_confirm_overlay(iid=1)
    assert panel._confirm_overlay.isVisible()
    assert "a/b" in panel._confirm_summary.text() or "b-gguf" in panel._confirm_summary.text()


def test_confirm_click_emits_install_and_dismisses_overlay(qtbot):
    panel, store, _ = _make_panel(qtbot)
    store.set_instance(1)
    st = store.get_state(1)
    st.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    st.setup = SetupStatus(llamacpp_installed=True, probed=True)
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=1, likes=1, tags=[],
                files=[HFModelFile("b-Q4_K_M.gguf", 4_000_000_000, "Q4_K_M")])
    panel.set_model(m)
    panel.show_confirm_overlay(iid=1)
    with qtbot.waitSignal(panel.install_requested, timeout=500) as blocker:
        panel._confirm_btn.click()
    assert blocker.args == [1, "a/b", "b-Q4_K_M.gguf"]
    assert not panel._confirm_overlay.isVisible()
```

- [ ] **Step 14.2: Run — expect fail**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: FAIL — overlay doesn't exist.

- [ ] **Step 14.3: Implement the overlay**

In `app/lab/views/install_panel_side.py`, add to the end of `_build_ready`:

```python
        # Confirm overlay (hidden until show_confirm_overlay())
        self._confirm_overlay = QFrame(w)
        self._confirm_overlay.setObjectName("ConfirmOverlay")
        self._confirm_overlay.setStyleSheet(
            f"QFrame#ConfirmOverlay {{ background: rgba(0,0,0,200); }}"
        )
        self._confirm_overlay.hide()
        self._confirm_iid: int | None = None
        self._build_confirm_card(self._confirm_overlay)

        # keep overlay sized to parent
        w.installEventFilter(self)
        self._ready_host = w
        return w

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is getattr(self, "_ready_host", None) and event.type() == QEvent.Resize:
            self._confirm_overlay.setGeometry(0, 0, obj.width(), obj.height())
        return super().eventFilter(obj, event)

    def _build_confirm_card(self, host: QFrame) -> None:
        lay = QVBoxLayout(host)
        lay.setAlignment(Qt.AlignCenter)
        card = QFrame()
        card.setFixedWidth(340)
        card.setStyleSheet(f"background: {t.SURFACE_1}; border: 1px solid {t.BORDER_LOW}; border-radius: 10px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        cl.setSpacing(t.SPACE_3)

        title = QLabel("Confirm deployment")
        title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 15px; font-weight: 700;")
        cl.addWidget(title)

        self._confirm_summary = QLabel("")
        self._confirm_summary.setWordWrap(True)
        self._confirm_summary.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 12px;")
        cl.addWidget(self._confirm_summary)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._hide_confirm)
        btns.addWidget(cancel)
        self._confirm_btn = QPushButton("Confirm \u2192")
        self._confirm_btn.setStyleSheet(f"background: {t.ACCENT}; color: white; font-weight: 700; padding: 4px 10px; border-radius: 6px;")
        self._confirm_btn.clicked.connect(self._on_confirm_clicked)
        btns.addWidget(self._confirm_btn)
        cl.addLayout(btns)

        lay.addWidget(card)

    def show_confirm_overlay(self, iid: int) -> None:
        if self.current_model is None:
            return
        selected_file = self._quant_combo.currentData()
        if selected_file is None:
            return
        state = self.store.get_state(iid)
        needs = "• Install llama.cpp\n" if not state.setup.llamacpp_installed else ""
        size_gb = selected_file.size_bytes / (1024**3) if selected_file.size_bytes else 0
        self._confirm_summary.setText(
            f"Target: Instance #{iid}\n"
            f"GPU: {state.system.gpu_name or '?'} • {(state.system.gpu_vram_gb or 0):.1f} GB\n\n"
            f"Repo: {self.current_model.id}\n"
            f"File: {selected_file.filename} ({size_gb:.1f} GB)\n\n"
            f"Steps:\n{needs}• Download GGUF to /workspace/models/"
        )
        self._confirm_iid = iid
        self._confirm_overlay.setGeometry(0, 0, self._ready_host.width(), self._ready_host.height())
        self._confirm_overlay.raise_()
        self._confirm_overlay.show()

    def _hide_confirm(self) -> None:
        self._confirm_overlay.hide()
        self._confirm_iid = None

    def _on_confirm_clicked(self) -> None:
        iid = self._confirm_iid
        self._hide_confirm()
        if iid is None:
            return
        selected_file = self._quant_combo.currentData()
        if selected_file is None or self.current_model is None:
            return
        if not self.registry.can_start(iid):
            return
        self.install_requested.emit(iid, self.current_model.id, selected_file.filename)
```

Update `_request_install_for` to route through the overlay:

```python
    def _request_install_for(self, iid: int) -> None:
        self.show_confirm_overlay(iid)
```

Adjust the earlier Task-13 test (`test_deploy_click_emits_install_requested`) — it called `_request_install_for` directly and expected the signal. With the overlay now intercepting, update the test to use `show_confirm_overlay` + `_confirm_btn.click()` OR replace that specific test with the two new overlay tests. Keep the codebase green: **delete `test_deploy_click_emits_install_requested`** (superseded by `test_confirm_click_emits_install_and_dismisses_overlay`).

- [ ] **Step 14.4: Run — expect pass**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: 8 passed (7 previous − 1 deleted + 2 new).

- [ ] **Step 14.5: Commit**

```bash
git add app/lab/views/install_panel_side.py tests/lab/views/test_install_panel_side.py
git commit -m "feat(panel): inline confirm overlay before deploy

Overlay is a child of the ready-mode widget (not a QDialog) so it
shares the panel's visual hierarchy. Install_requested is emitted
only on confirm."
```

---

### Task 15: `InstallProgress` component — bar + stage checklist + collapsible log

**Files:**
- Create: `app/ui/components/install_progress.py`
- Test: `tests/lab/ui/test_install_progress.py` (new; create `tests/lab/ui/` if missing)

- [ ] **Step 15.1: Failing test**

```python
# tests/lab/ui/test_install_progress.py
from app.ui.components.install_progress import InstallProgress, STAGES


def test_stages_defined_in_expected_order():
    assert STAGES == ["apt", "clone", "cmake", "build", "download", "verify"]


def test_set_stage_marks_priors_done(qtbot):
    w = InstallProgress()
    qtbot.addWidget(w)
    w.set_stage("build", percent=45)
    # apt/clone/cmake → done; build → running; download/verify → pending
    assert w.stage_state("apt")     == "done"
    assert w.stage_state("clone")   == "done"
    assert w.stage_state("cmake")   == "done"
    assert w.stage_state("build")   == "running"
    assert w.stage_state("download")== "pending"
    assert w.stage_state("verify")  == "pending"
    assert w.percent() == 45


def test_set_stage_done_marks_all_complete(qtbot):
    w = InstallProgress()
    qtbot.addWidget(w)
    w.set_stage("done", percent=100)
    for s in STAGES:
        assert w.stage_state(s) == "done"
    assert w.percent() == 100


def test_set_stage_failed_marks_current_failed(qtbot):
    w = InstallProgress()
    qtbot.addWidget(w)
    w.set_stage("cmake", percent=25)
    w.set_stage("failed", percent=25)
    assert w.stage_state("cmake") == "failed"
```

- [ ] **Step 15.2: Run — expect fail**

Run: `pytest tests/lab/ui/test_install_progress.py -v`
Expected: ImportError.

- [ ] **Step 15.3: Implement the component**

Create `tests/lab/ui/__init__.py` (empty), then `app/ui/components/install_progress.py`:

```python
"""Install progress widget: large bar + vertical stage checklist + collapsible log."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QPlainTextEdit, QFrame,
)

from app import theme as t


STAGES = ["apt", "clone", "cmake", "build", "download", "verify"]
_STAGE_LABEL = {
    "apt": "apt deps",
    "clone": "clone llama.cpp",
    "cmake": "cmake config",
    "build": "build",
    "download": "download GGUF",
    "verify": "verify size",
}


class InstallProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict[str, str] = {s: "pending" for s in STAGES}
        self._percent: int = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_3)

        # Big bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFixedHeight(18)
        lay.addWidget(self._bar)

        # Stage list
        self._stage_lbls: dict[str, QLabel] = {}
        stage_box = QFrame()
        stage_box.setStyleSheet(f"background: {t.SURFACE_1}; border-radius: 6px;")
        sb_lay = QVBoxLayout(stage_box)
        sb_lay.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        sb_lay.setSpacing(4)
        for s in STAGES:
            lbl = QLabel("")
            lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 12px;")
            self._stage_lbls[s] = lbl
            sb_lay.addWidget(lbl)
        lay.addWidget(stage_box)

        # Collapsible log
        row = QHBoxLayout()
        self._toggle = QPushButton("\u25B8 Show live log")
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.setStyleSheet("border: none; background: transparent; color: #888; text-align: left;")
        self._toggle.clicked.connect(self._toggle_log)
        row.addWidget(self._toggle)
        row.addStretch()
        lay.addLayout(row)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(200)
        self._log.setFixedHeight(120)
        self._log.setStyleSheet(f"background: {t.BG_VOID}; color: {t.TEXT_MID}; font-family: Consolas, monospace; font-size: 10px; border: 1px solid {t.BORDER_LOW}; border-radius: 4px;")
        self._log.setVisible(False)
        lay.addWidget(self._log)

        self._refresh_labels()

    # --- public API ---------------------------------------------------

    def set_stage(self, stage: str, percent: int | None = None) -> None:
        if percent is not None:
            self._percent = max(0, min(100, int(percent)))
            self._bar.setValue(self._percent)

        if stage == "done":
            for s in STAGES:
                self._state[s] = "done"
        elif stage == "failed":
            # Mark the last running/pending as failed; others unchanged.
            for s in STAGES:
                if self._state[s] == "running":
                    self._state[s] = "failed"
                    break
            else:
                # No running stage; mark first pending as failed.
                for s in STAGES:
                    if self._state[s] == "pending":
                        self._state[s] = "failed"
                        break
        elif stage in STAGES:
            hit = False
            for s in STAGES:
                if s == stage:
                    self._state[s] = "running"
                    hit = True
                elif not hit:
                    self._state[s] = "done"
                else:
                    self._state[s] = "pending"
        self._refresh_labels()

    def stage_state(self, stage: str) -> str:
        return self._state[stage]

    def percent(self) -> int:
        return self._percent

    def append_log(self, line: str) -> None:
        self._log.appendPlainText(line.rstrip("\n"))

    # --- internals ----------------------------------------------------

    def _refresh_labels(self) -> None:
        icons = {"pending": "\u25CB", "running": "\u25CF", "done": "\u2713", "failed": "\u2717"}
        colors = {"pending": t.TEXT_LOW, "running": t.ACCENT, "done": t.OK, "failed": t.ERR}
        for s in STAGES:
            state = self._state[s]
            lbl = self._stage_lbls[s]
            lbl.setText(f"{icons[state]}  {_STAGE_LABEL[s]}")
            lbl.setStyleSheet(f"color: {colors[state]}; font-size: 12px;")

    def _toggle_log(self) -> None:
        vis = not self._log.isVisible()
        self._log.setVisible(vis)
        self._toggle.setText(("\u25BE Hide" if vis else "\u25B8 Show") + " live log")
```

- [ ] **Step 15.4: Run — expect pass**

Run: `pytest tests/lab/ui/test_install_progress.py -v`
Expected: 4 passed.

- [ ] **Step 15.5: Commit**

```bash
git add app/ui/components/install_progress.py tests/lab/ui/__init__.py tests/lab/ui/test_install_progress.py
git commit -m "feat(ui): InstallProgress component — bar + stage checklist + log"
```

---

### Task 16: Mode "busy" — wire `InstallProgress` to `JobRegistry.job_updated`

**Files:**
- Modify: `app/lab/views/install_panel_side.py`
- Test: extend `tests/lab/views/test_install_panel_side.py`

- [ ] **Step 16.1: Extend the test**

```python
def test_busy_mode_reflects_registry_updates(qtbot):
    panel, store, registry = _make_panel(qtbot)
    store.set_instance(1)
    st = store.get_state(1)
    st.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    st.setup = SetupStatus(llamacpp_installed=True, probed=True)
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=1, likes=1, tags=[],
                files=[HFModelFile("b-Q4_K_M.gguf", 4_000_000_000, "Q4_K_M")])
    panel.set_model(m)

    desc = JobDescriptor(
        key="1-a-b-q4_k_m", iid=1, repo_id="a/b",
        filename="b-Q4_K_M.gguf", quant="Q4_K_M",
        size_bytes=4_000_000_000, needs_llamacpp=False,
        remote_state_path="/tmp/s", remote_log_path="/tmp/l",
        started_at=_time.time(),
    )
    registry.start_job(desc)
    panel.set_model(m)  # triggers refresh → busy mode
    assert panel.mode == "busy"

    registry.update(desc.key, stage="download", percent=50)
    assert panel._progress.stage_state("download") == "running"
    assert panel._progress.percent() == 50


def test_busy_mode_cancel_emits_signal(qtbot):
    panel, store, registry = _make_panel(qtbot)
    store.set_instance(1)
    st = store.get_state(1)
    st.system = RemoteSystem(gpu_name="RTX 3090", gpu_vram_gb=24.0, has_gpu=True)
    st.setup = SetupStatus(llamacpp_installed=True, probed=True)
    m = HFModel(id="a/b", author="a", name="b-gguf", downloads=1, likes=1, tags=[],
                files=[HFModelFile("b-Q4_K_M.gguf", 1, "Q4_K_M")])
    desc = JobDescriptor(key="1-a-b-q4_k_m", iid=1, repo_id="a/b",
                         filename="b-Q4_K_M.gguf", quant="Q4_K_M", size_bytes=1,
                         needs_llamacpp=False,
                         remote_state_path="/tmp/s", remote_log_path="/tmp/l",
                         started_at=_time.time())
    registry.start_job(desc)
    panel.set_model(m)
    with qtbot.waitSignal(panel.cancel_requested, timeout=500) as blocker:
        panel._cancel_btn.click()
        # The cancel button shows a confirm → click Yes
        panel._cancel_confirm_yes.click()
    assert blocker.args == [desc.key]
```

- [ ] **Step 16.2: Run — expect fail**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: FAIL — busy mode placeholder still in place.

- [ ] **Step 16.3: Replace the busy placeholder with a real widget**

In `__init__`, replace the `_busy_placeholder` lines with:

```python
        self._busy = self._build_busy()
        self.stack.addWidget(self._busy)   # index 2
```

Add at the bottom of the class:

```python
    def _build_busy(self) -> QWidget:
        from app.ui.components.install_progress import InstallProgress

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(t.SPACE_5, t.SPACE_4, t.SPACE_5, t.SPACE_4)
        lay.setSpacing(t.SPACE_4)

        self._busy_title = QLabel("")
        self._busy_title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 15px; font-weight: 700;")
        lay.addWidget(self._busy_title)

        self._progress = InstallProgress()
        lay.addWidget(self._progress)

        # Cancel w/ inline confirmation
        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        self._cancel_btn = QPushButton("Cancel install")
        self._cancel_btn.setStyleSheet(f"background: transparent; color: {t.ERR}; border: 1px solid {t.BORDER_LOW}; padding: 4px 10px; border-radius: 6px;")
        self._cancel_btn.clicked.connect(self._show_cancel_confirm)
        cancel_row.addWidget(self._cancel_btn)
        lay.addLayout(cancel_row)

        # Hidden confirm strip
        self._cancel_strip = QFrame()
        self._cancel_strip.setStyleSheet(f"background: {t.SURFACE_1}; border: 1px solid {t.BORDER_LOW}; border-radius: 6px;")
        cs = QHBoxLayout(self._cancel_strip)
        cs.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        cs.addWidget(QLabel("Kill remote process and remove state?"))
        cs.addStretch()
        no = QPushButton("No")
        no.clicked.connect(lambda: self._cancel_strip.hide())
        cs.addWidget(no)
        self._cancel_confirm_yes = QPushButton("Yes, cancel")
        self._cancel_confirm_yes.setStyleSheet(f"color: {t.ERR}; font-weight: 700;")
        self._cancel_confirm_yes.clicked.connect(self._emit_cancel)
        cs.addWidget(self._cancel_confirm_yes)
        self._cancel_strip.hide()
        lay.addWidget(self._cancel_strip)

        lay.addStretch()

        # Wire registry signals once
        self.registry.job_updated.connect(self._on_registry_update)
        self.registry.job_finished.connect(self._on_registry_finished)
        return w

    def _show_cancel_confirm(self) -> None:
        self._cancel_strip.show()

    def _emit_cancel(self) -> None:
        self._cancel_strip.hide()
        active = self._current_active_job()
        if active is not None:
            self.cancel_requested.emit(active.key)

    def _current_active_job(self):
        if self.current_model is None:
            return None
        for _k, d in self.registry.active_items():
            if d.repo_id == self.current_model.id:
                return d
        return None

    def _on_registry_update(self, key: str) -> None:
        if self.mode != self.MODE_BUSY:
            return
        active = self._current_active_job()
        if active is None or active.key != key:
            return
        self._progress.set_stage(active.stage, percent=active.percent)
        if active.speed:
            self._progress.append_log(f"{active.percent}% — {active.speed}")

    def _on_registry_finished(self, key: str, ok: bool) -> None:
        if self.mode != self.MODE_BUSY:
            return
        if ok:
            self._progress.set_stage("done", percent=100)
        else:
            # Inspect most recent recent-job for error info (_recent is not exposed; use get)
            self._progress.set_stage("failed", percent=self._progress.percent())
        # Return to ready mode on finish so user can deploy again
        self._refresh()
```

In `_refresh`, when switching to BUSY, populate the title and sync progress:

```python
        if active_on_this_model:
            self._busy_title.setText(f"Installing on #{self._current_active_job().iid}")
            active = self._current_active_job()
            if active is not None:
                self._progress.set_stage(active.stage, percent=active.percent)
            self._set_mode(self.MODE_BUSY)
        else:
            ...
```

- [ ] **Step 16.4: Run — expect pass**

Run: `pytest tests/lab/views/test_install_panel_side.py -v`
Expected: all panel tests pass.

- [ ] **Step 16.5: Commit**

```bash
git add app/lab/views/install_panel_side.py tests/lab/views/test_install_panel_side.py
git commit -m "feat(panel): busy-mode progress wired to JobRegistry signals

Bar + stage checklist update on every job_updated. Cancel button
shows an inline confirm strip and emits cancel_requested(key)."
```

---

## Phase 5 — Split view and model card

### Task 17: Convert `DiscoverView` to `QSplitter` with `InstallPanelSide`

**Files:**
- Modify: `app/lab/views/discover_view.py`

- [ ] **Step 17.1: Replace the content-layout scroll with a QSplitter**

In `app/lab/views/discover_view.py`:

1. Add imports:
```python
from PySide6.QtWidgets import QSplitter
from app.lab.views.install_panel_side import InstallPanelSide
```

2. Change the constructor signature to accept `job_registry`:
```python
def __init__(self, store, job_registry, parent=None):
    ...
    self.registry = job_registry
    ...
```

3. Replace the content widget build (the part that adds `self.scroll` to `content_lay`) with a splitter:

```python
        # Replace: content_lay.addWidget(self.scroll, 1)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(True)
        splitter.addWidget(self.scroll)

        self.side_panel = InstallPanelSide(self.store, self.registry, self)
        splitter.addWidget(self.side_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([720, 480])
        self._splitter = splitter
        content_lay.addWidget(splitter, 1)

        self.side_panel.close_requested.connect(self._toggle_side_panel)
        self.side_panel.install_requested.connect(self.download_requested.emit)
        self.side_panel.setup_requested.connect(self.setup_requested.emit)
        # cancel_requested → forwarded in Task 19
        self.side_panel.hide()  # start hidden until a card is clicked
```

4. Wire card click to open the panel by updating `_show_details` to:

```python
    def _show_details(self, model: HFModel):
        self.side_panel.set_model(model)
        self.side_panel.show()
```

5. Toggle panel visibility:

```python
    def _toggle_side_panel(self) -> None:
        self.side_panel.setVisible(not self.side_panel.isVisible())
```

- [ ] **Step 17.2: Update `AppShell` to pass the registry**

In `app/ui/app_shell.py`, change the line that instantiates `DiscoverView`:

```python
        self.discover = DiscoverView(self.store, self.job_registry, self)
```

- [ ] **Step 17.3: Boot smoke check**

Run: `python -m app`. Open Discover (make sure an instance is connected), click a model card → the right side panel appears with hero + quant + instance card. Close with `✕` in the panel → splitter collapses. Close app.

- [ ] **Step 17.4: Commit**

```bash
git add app/lab/views/discover_view.py app/ui/app_shell.py
git commit -m "feat(discover): split view with InstallPanelSide on the right

Card clicks open the panel instead of a QDialog. Panel close button
hides it until the next card click. Old _show_details still exists
but now delegates to side_panel.set_model."
```

---

### Task 18: Persist splitter sizes in `~/.vastai-app/ui_state.json`

**Files:**
- Modify: `app/lab/views/discover_view.py`

- [ ] **Step 18.1: Add save/load helpers to `DiscoverView`**

At the top of the class (after `__init__` body, still in class):

```python
    def _ui_state_path(self):
        import pathlib
        return pathlib.Path.home() / ".vastai-app" / "ui_state.json"

    def _load_splitter_sizes(self) -> list[int] | None:
        import json
        p = self._ui_state_path()
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            sizes = data.get("discover_splitter")
            if isinstance(sizes, list) and all(isinstance(x, int) for x in sizes):
                return sizes
        except Exception:
            return None
        return None

    def _save_splitter_sizes(self, sizes: list[int]) -> None:
        import json, pathlib
        p = self._ui_state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(p.read_text()) if p.exists() else {}
        except Exception:
            data = {}
        data["discover_splitter"] = sizes
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        import os
        os.replace(str(tmp), str(p))
```

- [ ] **Step 18.2: Apply saved sizes at construction + hook `splitterMoved`**

Right after creating the splitter and before `content_lay.addWidget(splitter, 1)`:

```python
        saved = self._load_splitter_sizes()
        if saved and len(saved) == 2:
            splitter.setSizes(saved)
        splitter.splitterMoved.connect(lambda *_: self._save_splitter_sizes(splitter.sizes()))
```

- [ ] **Step 18.3: Manual smoke check**

Run the app, drag the splitter handle to a new position, close the app. Open `~/.vastai-app/ui_state.json` — verify `discover_splitter` holds two integers. Relaunch: splitter restores to the saved sizes.

- [ ] **Step 18.4: Commit**

```bash
git add app/lab/views/discover_view.py
git commit -m "feat(discover): persist splitter sizes across sessions

Stored under ~/.vastai-app/ui_state.json alongside other UI prefs."
```

---

### Task 19: Extract `ModelCard` component + replace inline card render

**Files:**
- Create: `app/ui/components/model_card.py`
- Modify: `app/lab/views/discover_view.py`
- Test: `tests/lab/ui/test_model_card.py` (new)

- [ ] **Step 19.1: Failing test**

```python
# tests/lab/ui/test_model_card.py
from app.ui.components.model_card import ModelCard
from app.lab.services.huggingface import HFModel


def _m(name="x-gguf", tags=None, params_tag=None):
    tags = list(tags or [])
    if params_tag:
        tags.append(params_tag)
    return HFModel(id=f"a/{name}", author="a", name=name,
                   downloads=1, likes=1, tags=tags, files=[])


def test_card_selection_state(qtbot):
    c = ModelCard(_m())
    qtbot.addWidget(c)
    assert c.is_selected() is False
    c.set_selected(True)
    assert c.is_selected() is True


def test_card_installed_chip_visible_when_set(qtbot):
    c = ModelCard(_m())
    qtbot.addWidget(c)
    assert c._installed_chip.isVisible() is False
    c.set_installed_on([42])
    assert c._installed_chip.isVisible() is True
    assert "42" in c._installed_chip.text()


def test_card_installing_overlay_progress(qtbot):
    c = ModelCard(_m())
    qtbot.addWidget(c)
    c.set_installing(iid=42, percent=37)
    assert c._install_stripe.isVisible() is True
    assert c._install_chip.text().startswith("\u2193 37%")


def test_card_click_emits_details_signal(qtbot):
    m = _m()
    c = ModelCard(m)
    qtbot.addWidget(c)
    with qtbot.waitSignal(c.details_clicked, timeout=500) as blocker:
        c._details_btn.click()
    assert blocker.args == [m]
```

- [ ] **Step 19.2: Run — expect fail**

Run: `pytest tests/lab/ui/test_model_card.py -v`
Expected: ImportError.

- [ ] **Step 19.3: Implement `ModelCard`**

```python
# app/ui/components/model_card.py
"""Reusable model card for the Discover view."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)

from app import theme as t
from app.lab.services.huggingface import HFModel


_SKIP_TAGS = {"gguf", "region:us", "transformers", "safetensors", "text-generation"}


class ModelCard(QFrame):
    details_clicked = Signal(HFModel)
    open_hf_clicked = Signal(str)   # model_id

    def __init__(self, model: HFModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._selected = False
        self.setObjectName("ModelCard")
        self.setStyleSheet(self._css(selected=False))
        self.setCursor(QCursor(Qt.PointingHandCursor))

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        root.setSpacing(t.SPACE_2)

        # Install stripe (hidden by default) — sits at the top of the card
        self._install_stripe = QProgressBar()
        self._install_stripe.setRange(0, 100)
        self._install_stripe.setFixedHeight(3)
        self._install_stripe.setTextVisible(False)
        self._install_stripe.setVisible(False)
        root.addWidget(self._install_stripe)

        header = QHBoxLayout()
        name = QLabel(model.name)
        name.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 15px; font-weight: 700;")
        name.setWordWrap(True)
        header.addWidget(name, 1)

        if model.params_b > 0:
            p = QLabel(f"{model.params_b:.1f}B")
            p.setStyleSheet(f"background: rgba(124,92,255,0.15); color: {t.ACCENT_HI};"
                             "border-radius: 6px; padding: 2px 6px; font-size: 11px; font-weight: 700;")
            header.addWidget(p)
        root.addLayout(header)

        auth = QLabel(f"by {model.author}")
        auth.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 11px;")
        root.addWidget(auth)

        # Tag chips
        chips = QHBoxLayout()
        chips.setSpacing(4)
        for tag in model.tags:
            if tag in _SKIP_TAGS or tag.startswith(("license:", "dataset:", "library:")):
                continue
            lbl = QLabel(tag)
            lbl.setStyleSheet("background: rgba(255,255,255,0.05); color: #aaa;"
                              "padding: 1px 6px; border-radius: 4px; font-size: 10px;")
            chips.addWidget(lbl)
            if chips.count() >= 4:
                break
        chips.addStretch()
        root.addLayout(chips)

        stats = QLabel(f"\u2764 {model.likes:,}   \u2193 {model.downloads:,}")
        stats.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 11px;")
        root.addWidget(stats)

        # State chips row (installed / installing)
        state_row = QHBoxLayout()
        self._installed_chip = QLabel("")
        self._installed_chip.setStyleSheet(f"color: {t.OK}; background: rgba(80,200,120,0.15);"
                                           "border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 600;")
        self._installed_chip.setVisible(False)
        state_row.addWidget(self._installed_chip)
        self._install_chip = QLabel("")
        self._install_chip.setStyleSheet(f"color: {t.ACCENT_HI}; background: rgba(124,92,255,0.15);"
                                          "border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 600;")
        self._install_chip.setVisible(False)
        state_row.addWidget(self._install_chip)
        state_row.addStretch()
        root.addLayout(state_row)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        hf = QPushButton("Open HF \u2197")
        hf.setCursor(Qt.PointingHandCursor)
        hf.setStyleSheet(f"color: {t.ACCENT_HI}; background: transparent; border: 1px solid {t.BORDER_LOW};"
                          "padding: 3px 8px; border-radius: 6px; font-size: 11px;")
        hf.clicked.connect(lambda _=False, mid=model.id: self.open_hf_clicked.emit(mid))
        btns.addWidget(hf)
        self._details_btn = QPushButton("Details \u2192")
        self._details_btn.setStyleSheet(f"background: {t.ACCENT}; color: white; font-weight: 700;"
                                         "padding: 3px 10px; border-radius: 6px; font-size: 11px;")
        self._details_btn.clicked.connect(lambda _=False: self.details_clicked.emit(self.model))
        btns.addWidget(self._details_btn)
        root.addLayout(btns)

    # --- state API ----------------------------------------------------

    def set_selected(self, flag: bool) -> None:
        self._selected = flag
        self.setStyleSheet(self._css(selected=flag))

    def is_selected(self) -> bool:
        return self._selected

    def set_installed_on(self, iids: list[int]) -> None:
        if iids:
            self._installed_chip.setText(f"\u2713 Installed on #{iids[0]}")
            self._installed_chip.setVisible(True)
        else:
            self._installed_chip.setVisible(False)

    def set_installing(self, iid: int, percent: int) -> None:
        self._install_stripe.setValue(max(0, min(100, percent)))
        self._install_stripe.setVisible(True)
        self._install_chip.setText(f"\u2193 {percent}% on #{iid}")
        self._install_chip.setVisible(True)

    def clear_installing(self) -> None:
        self._install_stripe.setVisible(False)
        self._install_chip.setVisible(False)

    # --- internals ----------------------------------------------------

    def _css(self, selected: bool) -> str:
        border = t.ACCENT if selected else "rgba(255,255,255,0.06)"
        return (f"QFrame#ModelCard {{ background: {t.SURFACE_1}; "
                f"border: 1px solid {border}; border-radius: 10px; }} "
                f"QFrame#ModelCard:hover {{ border-color: {t.ACCENT_HI}; }}")
```

- [ ] **Step 19.4: Run — expect pass**

Run: `pytest tests/lab/ui/test_model_card.py -v`
Expected: 4 passed.

- [ ] **Step 19.5: Replace the inline card rendering in `DiscoverView._render`**

Replace the `for model in display_models:` block in `_render` with:

```python
        # Precompute per-iid lookups for installed/installing state
        installed_by_model: dict[str, list[int]] = {}
        installing_by_model: dict[str, tuple[int, int]] = {}  # model_id → (iid, percent)
        for iid in instance_ids:
            st = self.store.get_state(iid)
            if not st:
                continue
            for g in (st.gguf or []):
                # Match GGUF filename prefix to repo name is imperfect; we skip this
                # for now and only use it via explicit "installed" signals from ModelCard.
                pass
        for _k, desc in self.registry.active_items():
            installing_by_model[desc.repo_id] = (desc.iid, desc.percent)

        from app.ui.components.model_card import ModelCard

        for model in display_models:
            card = ModelCard(model)
            if model.id in installing_by_model:
                iid, pct = installing_by_model[model.id]
                card.set_installing(iid, pct)
            card.details_clicked.connect(self._show_details)
            card.open_hf_clicked.connect(self._open_hf)
            self.list_lay.addWidget(card)
```

Remove the inline `title/meta/tags/chip_row/details_btn` block that used to live here.

Update `_show_details` to highlight the selected card (track the currently selected ModelCard):

```python
    def _show_details(self, model: HFModel):
        # Highlight the selected card
        for i in range(self.list_lay.count()):
            w = self.list_lay.itemAt(i).widget()
            if hasattr(w, "set_selected"):
                w.set_selected(getattr(w, "model", None) is model)
        self.side_panel.set_model(model)
        self.side_panel.show()
```

- [ ] **Step 19.6: Run manual smoke**

Run the app, search `llama`. Cards should appear with the new look — hover highlights the border; click Details → card shows selected border and panel opens. Close app.

- [ ] **Step 19.7: Commit**

```bash
git add app/ui/components/model_card.py app/lab/views/discover_view.py tests/lab/ui/test_model_card.py
git commit -m "refactor(discover): extract ModelCard with hover/selected/installing states

Cards now show a top progress stripe + chip when an install is
running for their repo on any instance. Selection state mirrors
which card is open in the side panel."
```

---

## Phase 6 — Install flow integration

### Task 20: Wire `JobRegistry` through `_download_model_by_name`

**Files:**
- Modify: `app/ui/app_shell.py`

- [ ] **Step 20.1: Adapt the method**

In `app/ui/app_shell.py`, replace `_download_model_by_name` with:

```python
    def _download_model_by_name(self, iid: int, model_name: str, quant: str):
        """`quant` parameter is actually the full filename (legacy naming)."""
        if not iid or not self._controller or not self._ssh:
            return

        if not self.job_registry.can_start(iid):
            if self._controller:
                self._controller.toast_requested.emit(
                    f"Install already running on #{iid}.", "warning", 2500
                )
            return

        self.store.set_instance(iid)
        self._install_retry_iid = iid
        self._install_retry_model = model_name
        self._install_retry_quant = quant

        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host:
            return

        repo = model_name
        filename = quant
        # Extract quant token from filename for the key.
        import re
        m = re.search(r'-(Q\d_[A-Z0-9_]+)\.gguf$', filename, re.I)
        quant_token = m.group(1).upper() if m else "UNKNOWN"

        from app.lab.state.models import JobDescriptor, build_job_key
        import time
        key = build_job_key(iid, repo, quant_token)
        state = self.store.get_state(iid)
        needs_install = not state.setup.llamacpp_installed
        size_bytes = 0  # filled in from HF client in Task 22 if desired

        desc = JobDescriptor(
            key=key, iid=iid, repo_id=repo, filename=filename, quant=quant_token,
            size_bytes=size_bytes, needs_llamacpp=needs_install,
            remote_state_path=f"/workspace/.vastai-app/jobs/{key}.json",
            remote_log_path=f"/tmp/install-{key}.log",
            started_at=time.time(),
        )
        self.job_registry.start_job(desc)

        from app.lab.services.remote_setup import script_download_model, script_install_llamacpp
        script_parts: list[str] = []
        if needs_install:
            script_parts.append(script_install_llamacpp(job_key=key))
        script_parts.append(script_download_model(repo, filename, job_key=key))
        full_script = "\n".join(script_parts)

        worker = StreamingRemoteWorker(
            self._ssh, inst.ssh_host, inst.ssh_port, full_script, self,
        )
        self._setup_workers[iid] = worker
        log_tail: list[str] = []
        progress_state = {"phase": "install" if needs_install else "download", "percent": 0}

        def on_line(line: str):
            log_tail.append(line)
            if len(log_tail) > 200:
                del log_tail[:100]

            if progress_state["phase"] == "install":
                event = parse_cmake_build_stage(line)
                if event.stage == "done":
                    self.job_registry.update(key, stage="done", percent=100)
                    progress_state["phase"] = "download"
                    return
                if event.stage != "unknown":
                    percent = event.percent if event.percent is not None else progress_state["percent"]
                    progress_state["percent"] = percent
                    self.job_registry.update(key, stage=event.stage, percent=percent)
                return

            event = parse_wget_progress(line)
            if event is not None:
                self.job_registry.update(key, stage="download", percent=event.percent, speed=event.speed)
            elif "DOWNLOAD_DONE" in line:
                self.job_registry.update(key, stage="done", percent=100)

        worker.line.connect(on_line)
        worker.finished.connect(lambda ok, out: self._on_install_done_registry(ok, out, key, iid))
        worker.start()

    def _on_install_done_registry(self, ok: bool, output: str, key: str, iid: int):
        self.job_registry.finish(key, ok=ok, error=(output[-200:] if not ok else None))
        self._probe_instance(iid)
```

- [ ] **Step 20.2: Remove the old `InstallPanel` creation block**

In `_download_model_by_name`, delete the block that builds `"install"` view dynamically:

```python
        if "install" not in self._views:
            panel = InstallPanel(self.store, self)
            ...
        self._go("install")
```

No replacement navigation is needed — the side panel is already in Discover. Remove the `from app.lab.views.install_panel import InstallPanel` import at the top of the file.

Also remove the old `_on_install_done` handler (superseded by `_on_install_done_registry`).

- [ ] **Step 20.3: Smoke-test**

Run the app with an instance connected. Search a small GGUF, click Details, Deploy, Confirm. Watch the panel show download progress. Verify that clicking another card while installing shows the BusyCard for that iid.

- [ ] **Step 20.4: Commit**

```bash
git add app/ui/app_shell.py
git commit -m "feat(shell): route install flow through JobRegistry

_download_model_by_name builds a JobDescriptor, acquires the
per-instance lock, and feeds progress into the registry. finish
releases the lock. Removes dependency on the legacy full-page
InstallPanel."
```

---

### Task 21: Forward `cancel_requested` from the panel; kill remote job

**Files:**
- Modify: `app/lab/views/discover_view.py`, `app/ui/app_shell.py`

- [ ] **Step 21.1: Forward `cancel_requested` from DiscoverView**

In `app/lab/views/discover_view.py`, add after the other `side_panel` signal connections:

```python
        self.side_panel.cancel_requested.connect(self.cancel_requested)
```

Declare the signal near the top of `DiscoverView`:

```python
    cancel_requested = Signal(str)  # job key
```

- [ ] **Step 21.2: Handle it in `AppShell`**

In `attach_controller` (or in the block that already wires `self.discover` signals), add:

```python
        self.discover.cancel_requested.connect(self._cancel_job)
```

Add the handler at class level:

```python
    def _cancel_job(self, key: str) -> None:
        desc = self.job_registry.get(key)
        if desc is None or self._ssh is None or self._controller is None:
            return
        inst = next((i for i in self._controller.last_instances if i.id == desc.iid), None)
        if not inst or not inst.ssh_host:
            return
        from app.lab.services.remote_setup import script_cancel_job
        self._ssh.run_script(inst.ssh_host, inst.ssh_port, script_cancel_job(key))
        self.job_registry.finish(key, ok=False, error="cancelled")
```

- [ ] **Step 21.3: Commit**

```bash
git add app/lab/views/discover_view.py app/ui/app_shell.py
git commit -m "feat(cancel): forward cancel_requested from panel to SSH kill

Runs script_cancel_job on the remote to kill the PID and clear the
state file, then releases the registry lock."
```

---

### Task 22: Remove legacy `ModelDetailsDialog` and `InstallPanel`

**Files:**
- Delete: `app/lab/views/model_details_dialog.py`, `app/lab/views/install_panel.py`
- Delete: `tests/lab/test_install_panel.py`
- Modify: `app/ui/app_shell.py` (remove imports), `app/ui/components/nav_rail.py` if it has an `install` entry, `app/lab/views/discover_view.py` (remove stale import)

- [ ] **Step 22.1: Find and remove references**

Run:
```bash
grep -rn "ModelDetailsDialog" app/ tests/
grep -rn "install_panel" app/ tests/
grep -rn "\"install\"" app/ui/components/nav_rail.py
```

- [ ] **Step 22.2: Delete the files**

```bash
git rm app/lab/views/model_details_dialog.py
git rm app/lab/views/install_panel.py
git rm tests/lab/test_install_panel.py
```

- [ ] **Step 22.3: Update imports**

- `app/lab/views/discover_view.py`: remove `from app.lab.views.model_details_dialog import ModelDetailsDialog`.
- `app/ui/app_shell.py`: remove `from app.lab.views.install_panel import InstallPanel` (already done in Task 20; re-verify).
- If `NavRail` had an `install` entry, remove it from `NAV_ITEMS` (inspect the file first — safe-to-remove only if found).

- [ ] **Step 22.4: Run the full suite**

Run: `pytest tests/lab -q`
Expected: all green. Any remaining failure should point to a forgotten import — fix and rerun.

- [ ] **Step 22.5: Commit**

```bash
git add -A
git commit -m "chore: remove legacy ModelDetailsDialog and full-page InstallPanel

Their responsibilities are now served by the right-side panel in
Discover and the JobRegistry."
```

---

## Phase 7 — Reattachment

### Task 23: `RemoteJobProbe` worker

**Files:**
- Create: `app/lab/workers/remote_job_probe.py`
- Test: `tests/lab/workers/test_remote_job_probe.py`

- [ ] **Step 23.1: Failing test**

```python
# tests/lab/workers/test_remote_job_probe.py
from unittest.mock import MagicMock
from app.lab.workers.remote_job_probe import RemoteJobProbe
from app.lab.state.models import JobDescriptor
import time


def _desc():
    return JobDescriptor(
        key="1-x-q4", iid=1, repo_id="x/y", filename="y-Q4_K_M.gguf", quant="Q4_K_M",
        size_bytes=1, needs_llamacpp=False,
        remote_state_path="/workspace/.vastai-app/jobs/1-x-q4.json",
        remote_log_path="/tmp/install-1-x-q4.log",
        started_at=time.time(),
    )


def test_probe_emits_running_with_state(qtbot):
    ssh = MagicMock()
    ssh.run_script.return_value = (True, 'RUNNING\n{"pid":123,"stage":"download","percent":42}\n')
    desc = _desc()
    probe = RemoteJobProbe(ssh, "host", 22, desc)
    with qtbot.waitSignal(probe.result, timeout=2000) as blocker:
        probe.run()
    status, state = blocker.args
    assert status == "RUNNING"
    assert state["percent"] == 42


def test_probe_emits_missing_on_ssh_failure(qtbot):
    ssh = MagicMock()
    ssh.run_script.return_value = (False, "ssh blew up")
    probe = RemoteJobProbe(ssh, "host", 22, _desc())
    with qtbot.waitSignal(probe.result, timeout=2000) as blocker:
        probe.run()
    status, state = blocker.args
    assert status == "MISSING"
```

- [ ] **Step 23.2: Run — expect fail**

Run: `pytest tests/lab/workers/test_remote_job_probe.py -v`
Expected: ImportError.

- [ ] **Step 23.3: Implement the worker**

```python
# app/lab/workers/remote_job_probe.py
"""Probe for one remote job — runs check_job and parses the result."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.lab.services.remote_setup import script_check_job, parse_check_job_output
from app.lab.state.models import JobDescriptor


class RemoteJobProbe(QThread):
    # (status: str, state: dict)
    result = Signal(str, dict)

    def __init__(self, ssh_service, host: str, port: int, desc: JobDescriptor, parent=None):
        super().__init__(parent)
        self.ssh = ssh_service
        self.host = host
        self.port = port
        self.desc = desc

    def run(self) -> None:
        try:
            ok, output = self.ssh.run_script(self.host, self.port, script_check_job(self.desc.key))
        except Exception:
            self.result.emit("MISSING", {})
            return
        if not ok:
            self.result.emit("MISSING", {})
            return
        status, state = parse_check_job_output(output)
        self.result.emit(status, state)
```

- [ ] **Step 23.4: Run — expect pass**

Run: `pytest tests/lab/workers/test_remote_job_probe.py -v`
Expected: 2 passed.

- [ ] **Step 23.5: Commit**

```bash
git add app/lab/workers/remote_job_probe.py tests/lab/workers/test_remote_job_probe.py
git commit -m "feat(workers): RemoteJobProbe — runs check_job over SSH

Emits (status, state_dict). Safe against SSH errors (falls back
to MISSING so the reattach path silently drops the entry)."
```

---

### Task 24: `AppShell._try_reattach_jobs_once` + reattach stream

**Files:**
- Modify: `app/ui/app_shell.py`

- [ ] **Step 24.1: Add the guard + dispatcher**

In `AppShell.attach_controller`, add once after the existing `controller.instances_refreshed.connect(...)` lines:

```python
        controller.instances_refreshed.connect(self._try_reattach_jobs_once)
```

Add the method to the class:

```python
    def _try_reattach_jobs_once(self, instances, _user=None):
        if getattr(self, "_reattach_done", False):
            return
        self._reattach_done = True

        from app.lab.workers.remote_job_probe import RemoteJobProbe

        self._probes: dict[str, RemoteJobProbe] = {}
        for key, desc in self.job_registry.active_items():
            inst = next((i for i in instances if i.id == desc.iid), None)
            if not inst or not inst.ssh_host:
                # Not online — leave in registry; we'll try again on next refresh?
                # For simplicity we only try once per session; users can relaunch.
                continue
            probe = RemoteJobProbe(self._ssh, inst.ssh_host, inst.ssh_port, desc, self)
            self._probes[key] = probe
            probe.result.connect(lambda status, state, d=desc: self._on_job_probe(d, status, state))
            probe.start()

    def _on_job_probe(self, desc, status: str, state: dict):
        if status == "DONE":
            self.job_registry.finish(desc.key, ok=True)
            if self._controller:
                self._controller.toast_requested.emit(
                    f"Install of {desc.filename} completed on #{desc.iid}.", "success", 3000
                )
            self._probe_instance(desc.iid)
        elif status == "MISSING":
            self.job_registry.drop(desc.key)
        elif status == "RUNNING":
            # Re-sync registry fields, then spawn a StreamingRemoteWorker on the log.
            self.job_registry.update(
                desc.key,
                stage=state.get("stage", desc.stage),
                percent=state.get("percent", desc.percent),
                bytes_downloaded=state.get("bytes_downloaded", desc.bytes_downloaded),
            )
            self._reattach_stream(desc)
            self.job_registry.mark_reattached(desc.key)
            if self._controller:
                self._controller.toast_requested.emit(
                    f"Reattached to install on #{desc.iid}.", "info", 3000
                )
        elif status == "STALE":
            # STALE banner is surfaced by DiscoverView (Task 25)
            self.discover.side_panel.show_stale(desc, state)

    def _reattach_stream(self, desc) -> None:
        """Open a new StreamingRemoteWorker that tails the remote log."""
        inst = next((i for i in self._controller.last_instances if i.id == desc.iid), None)
        if not inst or not inst.ssh_host:
            return
        tail_script = f"tail -n +1 -f {desc.remote_log_path}"
        worker = StreamingRemoteWorker(self._ssh, inst.ssh_host, inst.ssh_port, tail_script, self)
        self._setup_workers[desc.iid] = worker
        key = desc.key

        def on_line(line: str):
            event = parse_wget_progress(line)
            if event is not None:
                self.job_registry.update(key, stage="download", percent=event.percent, speed=event.speed)
                return
            if "DOWNLOAD_DONE" in line:
                self.job_registry.update(key, stage="done", percent=100)
                self.job_registry.finish(key, ok=True)
                worker.requestInterruption()

        worker.line.connect(on_line)
        worker.start()
```

- [ ] **Step 24.2: Smoke-test**

Manual test (requires a live Vast instance):
1. Start a large download.
2. Watch panel reach ~15% on one instance.
3. Kill the Python app with the task manager.
4. Restart the app. After it reconnects, a toast should say "Reattached to install on #X" and the side panel, when opened to the same repo, shows Mode C with progress advancing.

If you can't reproduce on a real VM, mock by writing a synthetic `jobs.json` to `~/.vastai-app/` pointing at an existing running process, then relaunch.

- [ ] **Step 24.3: Commit**

```bash
git add app/ui/app_shell.py
git commit -m "feat(shell): reattach to live remote jobs on startup

After the first instances_refreshed, RemoteJobProbe classifies each
persisted job and acts: RUNNING → tail -f the log; DONE → close out;
STALE → surface banner; MISSING → drop silently."
```

---

### Task 25: STALE banner with Resume / Discard in the side panel

**Files:**
- Modify: `app/lab/views/install_panel_side.py`

- [ ] **Step 25.1: Add public API + banner UI**

In `install_panel_side.py`, add to `__init__` after the stack:

```python
        # Stale banner (overlays the stack when shown)
        self._stale_banner = QFrame(self)
        self._stale_banner.setStyleSheet(
            f"background: {t.WARN}; color: {t.BG_VOID}; padding: 6px 10px;"
        )
        sbl = QHBoxLayout(self._stale_banner)
        sbl.setContentsMargins(8, 4, 8, 4)
        self._stale_label = QLabel("")
        sbl.addWidget(self._stale_label, 1)
        resume_btn = QPushButton("Resume")
        resume_btn.clicked.connect(self._on_stale_resume)
        sbl.addWidget(resume_btn)
        discard_btn = QPushButton("Discard")
        discard_btn.clicked.connect(self._on_stale_discard)
        sbl.addWidget(discard_btn)
        self._stale_banner.hide()
        root.insertWidget(0, self._stale_banner)
        self._stale_desc = None
```

Add signals:

```python
    resume_requested  = Signal(str)   # job key
    discard_requested = Signal(str)   # job key
```

Add methods:

```python
    def show_stale(self, desc, state: dict) -> None:
        pct = state.get("percent", desc.percent) or 0
        stage = state.get("stage", desc.stage) or "?"
        self._stale_label.setText(
            f"Previous install of {desc.filename} on #{desc.iid} died at {stage} ({pct}%)."
        )
        self._stale_desc = desc
        self._stale_banner.show()

    def _on_stale_resume(self) -> None:
        if self._stale_desc is None:
            return
        self.resume_requested.emit(self._stale_desc.key)
        self._stale_banner.hide()
        self._stale_desc = None

    def _on_stale_discard(self) -> None:
        if self._stale_desc is None:
            return
        self.discard_requested.emit(self._stale_desc.key)
        self._stale_banner.hide()
        self._stale_desc = None
```

Forward from `DiscoverView`:

```python
    resume_requested  = Signal(str)
    discard_requested = Signal(str)
    ...
    self.side_panel.resume_requested.connect(self.resume_requested)
    self.side_panel.discard_requested.connect(self.discard_requested)
```

Wire in `AppShell.attach_controller`:

```python
        self.discover.resume_requested.connect(self._resume_job)
        self.discover.discard_requested.connect(self._discard_job)

    def _resume_job(self, key: str) -> None:
        desc = self.job_registry.get(key)
        if desc is None:
            return
        # Re-use _download_model_by_name — wget -c handles partial continuation.
        self.job_registry.drop(key)  # drop the stale descriptor so start_job succeeds
        self._download_model_by_name(desc.iid, desc.repo_id, desc.filename)

    def _discard_job(self, key: str) -> None:
        desc = self.job_registry.get(key)
        if desc is None:
            return
        if self._ssh and self._controller:
            inst = next((i for i in self._controller.last_instances if i.id == desc.iid), None)
            if inst and inst.ssh_host:
                from app.lab.services.remote_setup import script_cancel_job
                self._ssh.run_script(inst.ssh_host, inst.ssh_port, script_cancel_job(key))
        self.job_registry.drop(key)
```

- [ ] **Step 25.2: Manual smoke**

Write a synthetic `~/.vastai-app/jobs.json` pointing at a non-existent PID on an online instance. Start the app. The probe classifies the job STALE. Open the Discover panel — the yellow banner appears. Click **Discard** — banner closes, registry no longer holds the job.

- [ ] **Step 25.3: Commit**

```bash
git add app/lab/views/install_panel_side.py app/lab/views/discover_view.py app/ui/app_shell.py
git commit -m "feat(panel): STALE banner with Resume / Discard

Resume re-invokes the install (wget -c picks up the partial file).
Discard runs script_cancel_job to clean the remote state and drops
the registry entry."
```

---

## Phase 8 — Polish and smoke

### Task 26: Theme / visual polish

**Files:**
- Modify: `app/ui/styles.qss` (or equivalent — search the repo) + any inline styles that need tweaking

- [ ] **Step 26.1: Locate the global QSS**

Run:
```bash
grep -rn "QPushButton" app/ui/ --include="*.qss" --include="*.py" | head -20
```

Identify where global button styles live (expect `app/ui/styles.qss` or `app/theme.py`).

- [ ] **Step 26.2: Add/override styles for the Model Store buttons**

Add the following QSS block to the global stylesheet (or inside `app/theme.py` if styles are generated from Python):

```css
QPushButton[role="primary"] {
    background: #7C5CFF;                    /* t.ACCENT */
    color: #ffffff;
    font-weight: 700;
    padding: 6px 14px;
    border: none;
    border-radius: 6px;
}
QPushButton[role="primary"]:hover {
    background: #9B82FF;                    /* t.ACCENT_HI */
}
QPushButton[role="primary"]:disabled {
    background: rgba(255,255,255,0.04);
    color: #666;
    border: 1px dashed rgba(255,255,255,0.1);
}
QLabel[size="lg"] {
    font-size: 16px;
    font-weight: 800;
}
```

- [ ] **Step 26.3: Confirm the Deploy/Setup buttons render correctly**

Run the app. Open Discover → select a model → check: the Deploy button is filled violet with white bold text; Setup Environment has the same weight; disabled Deploy shows dashed border + muted text.

- [ ] **Step 26.4: Commit**

```bash
git add app/ui/styles.qss  # or app/theme.py
git commit -m "style: strengthen primary button + disabled state in Discover panel"
```

---

### Task 27: Manual integration smoke + update revamp plan supersede note

**Files:**
- Modify: `docs/superpowers/plans/2026-04-19-ai-lab-studio-revamp.md` (add supersede note at the top of Tasks 12/13/14)
- Update: the checklist in the spec file if anything was deferred

- [ ] **Step 27.1: Run the full test suite**

Run: `pytest tests/lab -q`
Expected: all green.

- [ ] **Step 27.2: Manual integration checklist**

Tick each as you verify against a live Vast.ai instance (or with mocked SSH):

- [ ] Split view opens, splitter sizes persist across restart.
- [ ] Cards render with hover, selected, installing states.
- [ ] Filter "Coding" narrows to coder-flavored repos; "Multimodal" returns `image-text-to-text`.
- [ ] Load more appends without clearing.
- [ ] Deploy → confirm overlay → install → panel progresses through stages → GGUF appears in Studio.
- [ ] Cancel install during download → remote state cleared → card returns to Mode B.
- [ ] Kill the Python app mid-download → relaunch → toast "Reattached…" → panel shows current %.
- [ ] Two instances downloading two different models in parallel — both progress.
- [ ] Busy card shows when an install is active on one instance and the user opens a different model.
- [ ] Disk full on remote → red state, registry finish(ok=False, error="disk_full") (if your parser detects it; otherwise accept generic "failed" text).

- [ ] **Step 27.3: Add supersede note to the revamp plan**

In `docs/superpowers/plans/2026-04-19-ai-lab-studio-revamp.md`, insert at the top of each of Tasks 12, 13, 14:

```markdown
> **Superseded:** by `docs/superpowers/plans/2026-04-19-model-store-side-panel.md`.
> Keep this section for history; do not implement from here.
```

- [ ] **Step 27.4: Commit**

```bash
git add docs/superpowers/plans/2026-04-19-ai-lab-studio-revamp.md
git commit -m "docs: mark install/download tasks superseded by side-panel plan"
```

---

## Self-review checklist (after all tasks)

- [ ] All tests in `tests/lab/` pass.
- [ ] `ModelDetailsDialog` and legacy `InstallPanel` are deleted (grep returns no hits).
- [ ] `jobs.json` round-trips under `~/.vastai-app/`.
- [ ] `NavRail` no longer exposes an `install` entry.
- [ ] Splitter sizes persist.
- [ ] No `jq` invocation in any remote script (grep `app/lab/services/remote_setup.py`).
- [ ] Confirm overlay renders inside the panel (not a standalone `QDialog`).
- [ ] `JobRegistry.can_start` enforces the lock in both the UI render path and the pre-start guard inside `AppShell._download_model_by_name`.
