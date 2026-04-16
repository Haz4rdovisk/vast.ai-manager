# Local AI Lab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a premium, self-contained workspace inside the Vast.ai Manager app for managing **local** LLMs with llama.cpp — hardware detection, runtime management, curated catalog, library, benchmarking, diagnostics.

**Architecture:** New isolated module `app/lab/` with its own design system, shell, nav rail, views, services, workers, and state store. Integrates into `MainWindow` via a top-bar toggle that swaps a `QStackedWidget` between the existing Cloud UI and the new Lab shell. No refactor of the Cloud side. Services are pure Python (Qt-free) for unit-testability; workers are thin QThread wrappers.

**Tech Stack:** Python 3.10+, PySide6, psutil (new dep), subprocess (nvidia-smi / llama.cpp binaries), urllib (HF downloads). No extra heavyweight deps — we keep the bundle lean.

**Testing approach:** Unit tests for pure logic — nvidia-smi parser, GGUF header parser, capacity estimator, recommendation engine, benchmark output parser, runtime version parser, diagnostics classifier. Qt components smoke-tested manually per existing project convention.

**Audit of existing code:**
- `app/theme.py` — global stylesheet; the Lab will ship its own stylesheet fragment that layers on top without disturbing Cloud.
- `app/ui/main_window.py` — central widget is currently a single `QWidget`. Task 5 wraps the whole body (excluding top bar/billing) in a `QStackedWidget` and adds the "Cloud | Lab" pill switcher.
- `app/workers/llama_probe.py`, `app/workers/model_watcher.py` — already probe `/v1/models`; we'll reuse the `_extract_model_id` helper shape for local benchmarking.
- `app/services/ssh_service.py` — unchanged by this work.
- `app/models.py` — unchanged; Lab has its own dataclasses in `app/lab/state/models.py`.

**What is explicitly NOT in this plan:**
- No integration of Lab benchmark results with remote Vast instances (can bridge later).
- No auth-gated model downloads (HF token optional, not required for MVP).
- No quantization *conversion* — library only scans/imports existing GGUF.

---

## Task 1: Dependencies + module scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `app/lab/__init__.py`
- Create: `app/lab/components/__init__.py`
- Create: `app/lab/services/__init__.py`
- Create: `app/lab/workers/__init__.py`
- Create: `app/lab/state/__init__.py`
- Create: `app/lab/views/__init__.py`
- Create: `app/lab/assets/__init__.py`

- [ ] **Step 1: Add psutil to requirements**

Edit `requirements.txt`:
```
PySide6>=6.6
vastai>=0.3
qtawesome>=1.2
pytest>=7.4
psutil>=5.9
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: psutil installed, no other changes.

- [ ] **Step 3: Create package skeleton**

Create all eight `__init__.py` files above, empty except `app/lab/__init__.py` which contains:
```python
"""Local AI Lab — premium in-app workspace for managing local llama.cpp models.
Self-contained; integrates via a top-bar toggle in MainWindow."""
```

- [ ] **Step 4: Sanity import check**

Run: `python -c "import app.lab, app.lab.components, app.lab.services, app.lab.workers, app.lab.state, app.lab.views"`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt app/lab/
git commit -m "lab: scaffold module + add psutil dep"
```

---

## Task 2: Design tokens

The Lab gets its own palette and spacing scale — deliberately darker and more saturated than the Cloud side, with layered surfaces.

**Files:**
- Create: `app/lab/theme.py`

- [ ] **Step 1: Write tokens + stylesheet fragment**

Create `app/lab/theme.py`:
```python
"""Local design tokens + QSS fragment for the Lab workspace.
Deliberately separate from app/theme.py — different visual language."""
from __future__ import annotations

# Deep charcoals with a blue undertone; surfaces layer via lightness, not hue.
BG_DEEP     = "#07090D"   # shell background
BG_BASE     = "#0C1016"   # content area
SURFACE_1   = "#141922"   # cards
SURFACE_2   = "#1C2330"   # elevated / hover
SURFACE_3   = "#262F3F"   # pressed / inputs
BORDER_LOW  = "#1B2230"
BORDER_MED  = "#2A3345"
BORDER_HI   = "#3B4662"

TEXT_HI     = "#F1F4FA"
TEXT        = "#C7CEDC"
TEXT_MID    = "#8891A6"
TEXT_LOW    = "#5A6277"

ACCENT      = "#7C5CFF"   # iris
ACCENT_HI   = "#9B83FF"
ACCENT_GLOW = "rgba(124, 92, 255, 0.35)"

OK          = "#3BD488"
WARN        = "#F4B740"
ERR         = "#F0556A"
INFO        = "#4EA8FF"

RADIUS_SM   = 6
RADIUS_MD   = 10
RADIUS_LG   = 14
RADIUS_XL   = 20

SPACE_1     = 4
SPACE_2     = 8
SPACE_3     = 12
SPACE_4     = 16
SPACE_5     = 24
SPACE_6     = 32
SPACE_7     = 48

FONT_DISPLAY = "Inter, 'Segoe UI Variable', 'Segoe UI', sans-serif"
FONT_MONO    = "'JetBrains Mono', Consolas, 'Courier New', monospace"


def health_color(level: str) -> str:
    return {"ok": OK, "warn": WARN, "err": ERR, "info": INFO}.get(level, TEXT_MID)


# Scoped to widgets with objectName starting with "lab-". Won't leak into Cloud.
STYLESHEET = f"""
#lab-shell {{
    background-color: {BG_DEEP};
    color: {TEXT};
    font-family: {FONT_DISPLAY};
    font-size: 10pt;
}}
#lab-shell QLabel {{ background: transparent; color: {TEXT}; }}
#lab-shell QLabel[role="display"] {{
    color: {TEXT_HI};
    font-size: 22pt;
    font-weight: 700;
    letter-spacing: -0.5px;
}}
#lab-shell QLabel[role="title"] {{
    color: {TEXT_HI};
    font-size: 14pt;
    font-weight: 600;
}}
#lab-shell QLabel[role="section"] {{
    color: {TEXT_MID};
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}
#lab-shell QLabel[role="mono"] {{
    font-family: {FONT_MONO};
    color: {TEXT};
}}
#lab-shell QLabel[role="muted"] {{ color: {TEXT_MID}; }}

#lab-shell QFrame[role="card"] {{
    background-color: {SURFACE_1};
    border: 1px solid {BORDER_LOW};
    border-radius: {RADIUS_LG}px;
}}
#lab-shell QFrame[role="card-raised"] {{
    background-color: {SURFACE_2};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_LG}px;
}}

#lab-shell QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: 10px 18px;
    font-weight: 600;
}}
#lab-shell QPushButton:hover {{ background-color: {ACCENT_HI}; }}
#lab-shell QPushButton:disabled {{
    background-color: {SURFACE_3}; color: {TEXT_LOW};
}}
#lab-shell QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {TEXT};
    border: 1px solid {BORDER_MED};
}}
#lab-shell QPushButton[variant="ghost"]:hover {{
    background-color: {SURFACE_2}; border-color: {BORDER_HI};
}}
#lab-shell QPushButton[variant="danger"] {{ background-color: {ERR}; }}

#lab-shell QLineEdit, #lab-shell QComboBox, #lab-shell QSpinBox {{
    background-color: {SURFACE_3};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_MD}px;
    padding: 8px 12px;
}}
#lab-shell QLineEdit:focus, #lab-shell QComboBox:focus {{ border-color: {ACCENT}; }}

#lab-nav-rail {{
    background-color: {BG_BASE};
    border-right: 1px solid {BORDER_LOW};
}}
#lab-nav-rail QPushButton[role="nav-item"] {{
    background-color: transparent;
    color: {TEXT_MID};
    text-align: left;
    padding: 12px 18px;
    border: none;
    border-radius: {RADIUS_MD}px;
    font-weight: 500;
}}
#lab-nav-rail QPushButton[role="nav-item"]:hover {{
    color: {TEXT_HI};
    background-color: {SURFACE_1};
}}
#lab-nav-rail QPushButton[role="nav-item"][active="true"] {{
    color: {TEXT_HI};
    background-color: {SURFACE_2};
    border-left: 2px solid {ACCENT};
}}

#lab-shell QScrollArea {{ border: none; background: transparent; }}
#lab-shell QScrollBar:vertical {{ background: transparent; width: 8px; }}
#lab-shell QScrollBar::handle:vertical {{
    background: {BORDER_MED}; border-radius: 4px; min-height: 28px;
}}
#lab-shell QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
#lab-shell QScrollBar::add-line, #lab-shell QScrollBar::sub-line {{ height: 0; }}
"""
```

- [ ] **Step 2: Import sanity**

Run: `python -c "from app.lab.theme import STYLESHEET, ACCENT; assert '#7C5CFF' in ACCENT"`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add app/lab/theme.py
git commit -m "lab: design tokens + scoped QSS fragment"
```

---

## Task 3: Core design primitives

**Files:**
- Create: `app/lab/components/primitives.py`

- [ ] **Step 1: Write primitives**

Create `app/lab/components/primitives.py`:
```python
"""Shared visual primitives for the Lab. Every widget sets objectName/role
properties so the scoped stylesheet can target them. No business logic here."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget
from PySide6.QtCore import Qt
from app.lab import theme as t


class GlassCard(QFrame):
    """Primary surface. Rounded, bordered, layered over the shell bg."""
    def __init__(self, raised: bool = False, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card-raised" if raised else "card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        self._lay.setSpacing(t.SPACE_3)

    def body(self) -> QVBoxLayout:
        return self._lay


class SectionHeader(QWidget):
    """Eyebrow + title pair. Used at the top of every view and in cards."""
    def __init__(self, eyebrow: str, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        e = QLabel(eyebrow)
        e.setProperty("role", "section")
        tl = QLabel(title)
        tl.setProperty("role", "title")
        lay.addWidget(e)
        lay.addWidget(tl)


class StatusPill(QLabel):
    """Small colored chip. `level` controls dot + text color."""
    def __init__(self, text: str, level: str = "info", parent=None):
        super().__init__(parent)
        self.set_status(text, level)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def set_status(self, text: str, level: str):
        color = t.health_color(level)
        self.setText(f"●  {text}")
        self.setStyleSheet(
            f"QLabel {{ color: {color}; background: {t.SURFACE_2};"
            f" border: 1px solid {t.BORDER_MED};"
            f" border-radius: 999px; padding: 4px 10px;"
            f" font-size: 9pt; font-weight: 600; }}"
        )


class HealthDot(QLabel):
    """Tiny colored dot — inline health signal, no label."""
    def __init__(self, level: str = "info", parent=None):
        super().__init__(parent)
        self.set_level(level)

    def set_level(self, level: str):
        color = t.health_color(level)
        self.setFixedSize(10, 10)
        self.setStyleSheet(
            f"QLabel {{ background: {color}; border-radius: 5px; }}"
        )


class MetricTile(GlassCard):
    """Single big number + label + optional delta line. For Machine + Overview."""
    def __init__(self, label: str, value: str = "—", hint: str = "", parent=None):
        super().__init__(parent=parent)
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        self._lay.setSpacing(2)
        self._label = QLabel(label)
        self._label.setProperty("role", "section")
        self._value = QLabel(value)
        self._value.setProperty("role", "display")
        self._hint = QLabel(hint)
        self._hint.setProperty("role", "muted")
        self._hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID};")
        self._lay.addWidget(self._label)
        self._lay.addWidget(self._value)
        self._lay.addWidget(self._hint)

    def set_value(self, value: str, hint: str = ""):
        self._value.setText(value)
        self._hint.setText(hint)


class KeyValueRow(QWidget):
    """Two-column row — key on the left, value monospace on the right."""
    def __init__(self, key: str, value: str = "—", mono: bool = True, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._k = QLabel(key)
        self._k.setProperty("role", "muted")
        self._v = QLabel(value)
        if mono:
            self._v.setProperty("role", "mono")
        lay.addWidget(self._k)
        lay.addStretch()
        lay.addWidget(self._v)

    def set_value(self, value: str):
        self._v.setText(value)
```

- [ ] **Step 2: Import sanity**

Run: `python -c "from app.lab.components.primitives import GlassCard, MetricTile, StatusPill"`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add app/lab/components/primitives.py
git commit -m "lab: core visual primitives (GlassCard, MetricTile, StatusPill, etc.)"
```

---

## Task 4: State store

Centralized reactive store so views don't have to thread signals through each other.

**Files:**
- Create: `app/lab/state/models.py`
- Create: `app/lab/state/store.py`
- Create: `tests/lab/__init__.py`
- Create: `tests/lab/test_store.py`

- [ ] **Step 1: Write dataclasses**

Create `app/lab/state/models.py`:
```python
"""Plain dataclasses for the Lab state tree. No Qt. Serializable via asdict."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

HealthLevel = Literal["ok", "warn", "err", "info", "unknown"]


@dataclass
class GPUInfo:
    name: str
    vram_total_gb: float
    driver: str | None = None
    cuda_capable: bool = False


@dataclass
class HardwareSpec:
    os_name: str = ""
    os_version: str = ""
    cpu_name: str = ""
    cpu_cores_physical: int = 0
    cpu_cores_logical: int = 0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    gpus: list[GPUInfo] = field(default_factory=list)
    # Best-guess backend label: "cuda", "rocm", "metal", "cpu".
    best_backend: str = "cpu"


@dataclass
class RuntimeStatus:
    installed: bool = False
    version: str | None = None
    binary_path: str | None = None
    backend: str | None = None     # "cuda"|"cpu"|...
    validated: bool = False
    error: str | None = None


@dataclass
class ModelFile:
    path: str
    name: str               # display name ("Qwen2.5-7B-Instruct-Q4_K_M")
    size_bytes: int
    architecture: str = ""  # from GGUF header ("llama", "qwen2", ...)
    param_count_b: float = 0.0
    context_length: int = 0
    quant: str = ""         # "Q4_K_M", "Q8_0", ...
    valid: bool = True
    error: str | None = None


@dataclass
class CatalogEntry:
    id: str                   # stable key, e.g. "qwen2.5-7b-instruct-q4km"
    family: str               # "Qwen2.5"
    display_name: str
    params_b: float
    quant: str
    repo_id: str              # HF repo
    filename: str             # GGUF filename in repo
    approx_size_gb: float
    approx_vram_gb: float     # full GPU offload
    approx_ram_gb: float      # full CPU
    context_length: int
    use_cases: list[str] = field(default_factory=list)  # ["coding","chat","long_context"]
    quality_tier: int = 3     # 1..5
    notes: str = ""


@dataclass
class Recommendation:
    entry: CatalogEntry
    fit: Literal["excellent", "good", "tight", "not_recommended"]
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    model_name: str
    timestamp: float
    tokens_per_sec: float
    ttft_ms: float
    prompt_eval_tok_per_sec: float
    ram_peak_gb: float | None = None
    vram_peak_gb: float | None = None


@dataclass
class DiagnosticsItem:
    id: str
    level: HealthLevel
    title: str
    detail: str
    fix_action: str | None = None   # handler key, e.g. "install_runtime"
```

- [ ] **Step 2: Write the store**

Create `app/lab/state/store.py`:
```python
"""Single source of truth for the Lab. Qt signals notify views of changes.
Views subscribe; services/workers push."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal
from app.lab.state.models import (
    HardwareSpec, RuntimeStatus, ModelFile, CatalogEntry,
    Recommendation, BenchmarkResult, DiagnosticsItem,
)


class LabStore(QObject):
    hardware_changed = Signal(object)          # HardwareSpec
    runtime_changed = Signal(object)           # RuntimeStatus
    library_changed = Signal(list)             # list[ModelFile]
    catalog_changed = Signal(list)             # list[CatalogEntry]
    recommendations_changed = Signal(list)     # list[Recommendation]
    benchmarks_changed = Signal(list)          # list[BenchmarkResult]
    diagnostics_changed = Signal(list)         # list[DiagnosticsItem]
    busy_changed = Signal(str, bool)           # (key, is_busy)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hardware = HardwareSpec()
        self.runtime = RuntimeStatus()
        self.library: list[ModelFile] = []
        self.catalog: list[CatalogEntry] = []
        self.recommendations: list[Recommendation] = []
        self.benchmarks: list[BenchmarkResult] = []
        self.diagnostics: list[DiagnosticsItem] = []
        self._busy: dict[str, bool] = {}

    def set_hardware(self, spec: HardwareSpec):
        self.hardware = spec
        self.hardware_changed.emit(spec)

    def set_runtime(self, rs: RuntimeStatus):
        self.runtime = rs
        self.runtime_changed.emit(rs)

    def set_library(self, items: list[ModelFile]):
        self.library = items
        self.library_changed.emit(items)

    def set_catalog(self, items: list[CatalogEntry]):
        self.catalog = items
        self.catalog_changed.emit(items)

    def set_recommendations(self, items: list[Recommendation]):
        self.recommendations = items
        self.recommendations_changed.emit(items)

    def add_benchmark(self, item: BenchmarkResult):
        self.benchmarks.append(item)
        self.benchmarks_changed.emit(list(self.benchmarks))

    def set_diagnostics(self, items: list[DiagnosticsItem]):
        self.diagnostics = items
        self.diagnostics_changed.emit(items)

    def set_busy(self, key: str, busy: bool):
        self._busy[key] = busy
        self.busy_changed.emit(key, busy)

    def is_busy(self, key: str) -> bool:
        return self._busy.get(key, False)
```

- [ ] **Step 3: Write failing test**

Create `tests/lab/__init__.py` (empty) and `tests/lab/test_store.py`:
```python
from app.lab.state.store import LabStore
from app.lab.state.models import HardwareSpec, BenchmarkResult


def test_store_emits_on_hardware_set(qtbot=None):
    # No pytest-qt — use a plain holder to prove the signal fired.
    store = LabStore()
    received = []
    store.hardware_changed.connect(lambda s: received.append(s))
    spec = HardwareSpec(cpu_name="Ryzen 9", ram_total_gb=64.0)
    store.set_hardware(spec)
    assert len(received) == 1
    assert received[0].cpu_name == "Ryzen 9"


def test_store_benchmarks_accumulate():
    store = LabStore()
    store.add_benchmark(BenchmarkResult("a", 1.0, 10.0, 100.0, 20.0))
    store.add_benchmark(BenchmarkResult("b", 2.0, 15.0, 80.0, 25.0))
    assert len(store.benchmarks) == 2
    assert store.benchmarks[-1].model_name == "b"


def test_store_busy_flag():
    store = LabStore()
    assert not store.is_busy("download")
    store.set_busy("download", True)
    assert store.is_busy("download")
```

Note: this requires a `QCoreApplication` for signal dispatch. If pytest run has no Qt app, the signal emits synchronously on direct connection anyway, but to be safe add a fixture:

Create `tests/lab/conftest.py`:
```python
import pytest
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/lab/test_store.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/lab/state/ tests/lab/
git commit -m "lab: state store + dataclasses + tests"
```

---

## Task 5: Shell + nav rail + MainWindow toggle

**Files:**
- Create: `app/lab/components/nav_rail.py`
- Create: `app/lab/shell.py`
- Modify: `app/ui/main_window.py`
- Modify: `main.py`

- [ ] **Step 1: Write nav rail**

Create `app/lab/components/nav_rail.py`:
```python
"""Left nav rail for the Lab. Emits `selected(key)` on button click."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QWidget
from PySide6.QtCore import Signal, Qt
from app.lab import theme as t


NAV_ITEMS = [
    ("overview",    "Overview",    "◈"),
    ("machine",     "Machine",     "▣"),
    ("runtime",     "Runtime",     "◧"),
    ("discover",    "Discover",    "✦"),
    ("library",     "Library",     "▤"),
    ("benchmark",   "Benchmark",   "◴"),
    ("diagnostics", "Diagnostics", "◉"),
]


class NavRail(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lab-nav-rail")
        self.setFixedWidth(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_4, t.SPACE_5, t.SPACE_3, t.SPACE_4)
        lay.setSpacing(2)

        brand = QLabel("LOCAL AI LAB")
        brand.setStyleSheet(
            f"color: {t.TEXT_HI}; font-weight: 800; letter-spacing: 2px;"
            f" font-size: 10pt; padding: 4px 8px 20px 8px;"
        )
        lay.addWidget(brand)

        self._buttons: dict[str, QPushButton] = {}
        for key, label, glyph in NAV_ITEMS:
            btn = QPushButton(f"  {glyph}   {label}")
            btn.setProperty("role", "nav-item")
            btn.setProperty("active", "false")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
            lay.addWidget(btn)
            self._buttons[key] = btn

        lay.addStretch()

        foot = QLabel("llama.cpp • local inference")
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 8pt; padding: 8px;")
        lay.addWidget(foot)

        self.set_active("overview")

    def _on_click(self, key: str):
        self.set_active(key)
        self.selected.emit(key)

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
```

- [ ] **Step 2: Write shell with placeholder views**

Create `app/lab/shell.py`:
```python
"""LabShell — top-level widget for the Local AI Lab workspace.
Hosts the nav rail + a QStackedWidget of views. Owns the LabStore."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QStackedWidget, QLabel, QVBoxLayout,
)
from PySide6.QtCore import Qt
from app.lab import theme as t
from app.lab.components.nav_rail import NavRail, NAV_ITEMS
from app.lab.state.store import LabStore


class _Placeholder(QWidget):
    """Temporary view stub — replaced by real views in later tasks."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        lbl = QLabel(title)
        lbl.setProperty("role", "display")
        hint = QLabel("Coming online…")
        hint.setProperty("role", "muted")
        lay.addWidget(lbl)
        lay.addWidget(hint)
        lay.addStretch()


class LabShell(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lab-shell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.store = LabStore(self)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavRail(self)
        self.nav.selected.connect(self._switch)
        root.addWidget(self.nav)

        self.stack = QStackedWidget(self)
        self._views: dict[str, QWidget] = {}
        for key, label, _ in NAV_ITEMS:
            v = _Placeholder(label, self)
            self.stack.addWidget(v)
            self._views[key] = v
        root.addWidget(self.stack, 1)

        self._switch("overview")

    def _switch(self, key: str):
        v = self._views.get(key)
        if v is not None:
            self.stack.setCurrentWidget(v)

    def replace_view(self, key: str, widget: QWidget):
        """Called by later tasks to swap a placeholder for the real view."""
        old = self._views.get(key)
        if old is not None:
            idx = self.stack.indexOf(old)
            self.stack.removeWidget(old)
            old.deleteLater()
        self._views[key] = widget
        self.stack.insertWidget(idx if old else self.stack.count(), widget)
```

- [ ] **Step 3: Wire the toggle into MainWindow**

Modify `app/ui/main_window.py` — add top-level Cloud/Lab toggle. Near the imports add:
```python
from PySide6.QtWidgets import QStackedWidget
from app.lab.shell import LabShell
from app.lab import theme as lab_theme
```

Find the `_build_ui` method. At the **beginning of the method** (right after `central = QWidget(); self.setCentralWidget(central)`), replace the body so that:
1. A thin top strip hosts the Cloud/Lab pill.
2. A `QStackedWidget` hosts the existing Cloud body (current content moved into a wrapper widget) and the LabShell.

Concretely, the current body (from `root = QVBoxLayout(central)` onward) becomes the Cloud body — wrap it in a dedicated `self.cloud_body = QWidget()` and construct `root = QVBoxLayout(self.cloud_body)`. Then add:

```python
        # Top-level shell around the existing Cloud UI + the new Lab.
        shell_root = QVBoxLayout(central)
        shell_root.setContentsMargins(0, 0, 0, 0)
        shell_root.setSpacing(0)

        toggle_bar = QWidget()
        toggle_bar.setFixedHeight(44)
        tb = QHBoxLayout(toggle_bar)
        tb.setContentsMargins(16, 6, 16, 6)
        self.toggle_cloud_btn = QPushButton("☁  Cloud")
        self.toggle_lab_btn = QPushButton("✦  Lab")
        for b in (self.toggle_cloud_btn, self.toggle_lab_btn):
            b.setObjectName("secondary")
            b.setCheckable(True)
            b.setFixedHeight(30)
        self.toggle_cloud_btn.setChecked(True)
        self.toggle_cloud_btn.clicked.connect(lambda: self._switch_workspace("cloud"))
        self.toggle_lab_btn.clicked.connect(lambda: self._switch_workspace("lab"))
        tb.addStretch()
        tb.addWidget(self.toggle_cloud_btn)
        tb.addWidget(self.toggle_lab_btn)
        tb.addStretch()
        shell_root.addWidget(toggle_bar)

        self.workspace_stack = QStackedWidget()
        self.cloud_body = QWidget()
        shell_root.addWidget(self.workspace_stack, 1)

        root = QVBoxLayout(self.cloud_body)
        # ... (rest of the existing _build_ui body stays exactly as it is,
        # still using `root` as the layout it writes into) ...
```

At the **end of `_build_ui`**, after all the existing widgets are appended to `root`, add:
```python
        self.workspace_stack.addWidget(self.cloud_body)
        self.lab_shell = LabShell()
        self.workspace_stack.addWidget(self.lab_shell)
        self.workspace_stack.setCurrentWidget(self.cloud_body)
```

Add the switch method anywhere in the class:
```python
    def _switch_workspace(self, key: str):
        if key == "cloud":
            self.workspace_stack.setCurrentWidget(self.cloud_body)
            self.toggle_cloud_btn.setChecked(True)
            self.toggle_lab_btn.setChecked(False)
        else:
            self.workspace_stack.setCurrentWidget(self.lab_shell)
            self.toggle_cloud_btn.setChecked(False)
            self.toggle_lab_btn.setChecked(True)
```

- [ ] **Step 4: Append the Lab stylesheet**

Modify `main.py`:
```python
from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from app.config import ConfigStore
from app import theme
from app.lab import theme as lab_theme
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Vast.ai Manager")
    # Cloud + Lab stylesheets concatenated — Lab rules are scoped under #lab-shell.
    app.setStyleSheet(theme.STYLESHEET + "\n" + lab_theme.STYLESHEET)

    store = ConfigStore()
    win = MainWindow(store)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Smoke run**

Run: `python main.py`
Expected: app opens on Cloud view as before; clicking "Lab" swaps to the new shell with a left nav rail and 7 placeholder views; clicking "Cloud" returns.

- [ ] **Step 6: Commit**

```bash
git add app/lab/shell.py app/lab/components/nav_rail.py app/ui/main_window.py main.py
git commit -m "lab: shell + nav rail + MainWindow workspace toggle"
```

---

## Task 6: nvidia-smi parser (pure, testable)

**Files:**
- Create: `app/lab/services/nvidia.py`
- Create: `tests/lab/test_nvidia_parser.py`

- [ ] **Step 1: Write failing test**

Create `tests/lab/test_nvidia_parser.py`:
```python
from app.lab.services.nvidia import parse_nvidia_smi_csv


def test_parse_single_gpu():
    csv = "NVIDIA GeForce RTX 4090, 24564, 555.85, 8.9"
    gpus = parse_nvidia_smi_csv(csv)
    assert len(gpus) == 1
    g = gpus[0]
    assert g.name == "NVIDIA GeForce RTX 4090"
    assert g.vram_total_gb == 24564 / 1024
    assert g.driver == "555.85"
    assert g.cuda_capable is True


def test_parse_multi_gpu():
    csv = (
        "NVIDIA GeForce RTX 4090, 24564, 555.85, 8.9\n"
        "NVIDIA GeForce RTX 3090, 24576, 555.85, 8.6\n"
    )
    gpus = parse_nvidia_smi_csv(csv)
    assert len(gpus) == 2
    assert gpus[1].name == "NVIDIA GeForce RTX 3090"


def test_parse_empty_returns_empty():
    assert parse_nvidia_smi_csv("") == []
    assert parse_nvidia_smi_csv("\n\n  \n") == []


def test_parse_malformed_row_skipped():
    csv = "NVIDIA RTX 3080, 10240\nNVIDIA RTX 4090, 24564, 555.85, 8.9"
    gpus = parse_nvidia_smi_csv(csv)
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA RTX 4090"
```

- [ ] **Step 2: Run — should fail**

Run: `pytest tests/lab/test_nvidia_parser.py -v`
Expected: ModuleNotFoundError or ImportError.

- [ ] **Step 3: Implement**

Create `app/lab/services/nvidia.py`:
```python
"""Thin wrapper around `nvidia-smi`. Keeps parsing pure so it's unit-testable."""
from __future__ import annotations
import subprocess
import sys
from app.lab.state.models import GPUInfo


def parse_nvidia_smi_csv(text: str) -> list[GPUInfo]:
    """Parse `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap
    --format=csv,noheader,nounits` output. Returns one GPUInfo per row.
    Malformed rows are silently skipped — the query above should always be
    well-formed, but drivers occasionally emit a blank first line."""
    gpus: list[GPUInfo] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        name, mem_mb, driver, compute = parts[0], parts[1], parts[2], parts[3]
        try:
            vram_gb = float(mem_mb) / 1024.0
        except ValueError:
            continue
        try:
            cc = float(compute)
            cuda_capable = cc >= 3.5
        except ValueError:
            cuda_capable = True  # NVIDIA GPU responded → assume CUDA OK
        gpus.append(GPUInfo(
            name=name, vram_total_gb=vram_gb, driver=driver,
            cuda_capable=cuda_capable,
        ))
    return gpus


def query_nvidia_smi(timeout_s: float = 3.0) -> list[GPUInfo]:
    """Invoke nvidia-smi; return [] if the binary is missing or fails."""
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,driver_version,compute_cap",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout_s,
            creationflags=creationflags,
        )
        if res.returncode != 0:
            return []
        return parse_nvidia_smi_csv(res.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
```

- [ ] **Step 4: Run — should pass**

Run: `pytest tests/lab/test_nvidia_parser.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/lab/services/nvidia.py tests/lab/test_nvidia_parser.py
git commit -m "lab: nvidia-smi query + pure parser with tests"
```

---

## Task 7: Hardware detector + probe worker

**Files:**
- Create: `app/lab/services/hardware.py`
- Create: `app/lab/workers/hw_probe.py`
- Create: `tests/lab/test_hardware_detector.py`

- [ ] **Step 1: Write failing test for os+cpu+ram aggregator**

Create `tests/lab/test_hardware_detector.py`:
```python
from app.lab.services.hardware import pick_best_backend
from app.lab.state.models import GPUInfo


def test_pick_best_backend_cuda():
    gpus = [GPUInfo("RTX 4090", 24.0, "555", True)]
    assert pick_best_backend("Windows", gpus) == "cuda"


def test_pick_best_backend_cpu_when_no_gpu():
    assert pick_best_backend("Windows", []) == "cpu"


def test_pick_best_backend_metal_on_mac():
    assert pick_best_backend("Darwin", []) == "metal"


def test_pick_best_backend_cuda_wins_on_multi_gpu():
    gpus = [GPUInfo("RTX 3090", 24.0, "555", True),
            GPUInfo("RTX 4090", 24.0, "555", True)]
    assert pick_best_backend("Linux", gpus) == "cuda"
```

- [ ] **Step 2: Implement**

Create `app/lab/services/hardware.py`:
```python
"""Local hardware detection. psutil for CPU/RAM/disk; nvidia-smi for GPUs;
pure helpers below are Qt-free for testing."""
from __future__ import annotations
import platform
import shutil
from app.lab.services.nvidia import query_nvidia_smi
from app.lab.state.models import HardwareSpec, GPUInfo


def pick_best_backend(os_name: str, gpus: list[GPUInfo]) -> str:
    if any(g.cuda_capable for g in gpus):
        return "cuda"
    if os_name == "Darwin":
        return "metal"
    return "cpu"


def detect_hardware() -> HardwareSpec:
    """Blocking detection. Safe to call from a worker thread."""
    import psutil
    os_name = platform.system() or "Unknown"
    os_version = platform.version() or platform.release() or ""
    cpu_name = platform.processor() or platform.machine() or "CPU"
    cores_phys = psutil.cpu_count(logical=False) or 0
    cores_log = psutil.cpu_count(logical=True) or 0
    vm = psutil.virtual_memory()
    ram_total = vm.total / (1024 ** 3)
    ram_avail = vm.available / (1024 ** 3)
    # Disk: root of the current drive — good enough; users can refine later.
    disk_root = "/" if os_name != "Windows" else "C:\\"
    try:
        du = psutil.disk_usage(disk_root)
        disk_total = du.total / (1024 ** 3)
        disk_free = du.free / (1024 ** 3)
    except OSError:
        disk_total = disk_free = 0.0

    gpus = query_nvidia_smi()
    return HardwareSpec(
        os_name=os_name,
        os_version=os_version,
        cpu_name=cpu_name.strip(),
        cpu_cores_physical=cores_phys,
        cpu_cores_logical=cores_log,
        ram_total_gb=ram_total,
        ram_available_gb=ram_avail,
        disk_total_gb=disk_total,
        disk_free_gb=disk_free,
        gpus=gpus,
        best_backend=pick_best_backend(os_name, gpus),
    )
```

- [ ] **Step 3: Write worker**

Create `app/lab/workers/hw_probe.py`:
```python
"""Hardware probe as a QThread — keeps the UI responsive during psutil/nvidia-smi."""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.hardware import detect_hardware


class HardwareProbeWorker(QThread):
    detected = Signal(object)   # HardwareSpec
    failed = Signal(str)

    def run(self):
        try:
            spec = detect_hardware()
            self.detected.emit(spec)
        except Exception as e:
            self.failed.emit(str(e))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/lab/test_hardware_detector.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/lab/services/hardware.py app/lab/workers/hw_probe.py tests/lab/test_hardware_detector.py
git commit -m "lab: hardware detection service + probe worker"
```

---

## Task 8: Capacity estimator (pure)

**Files:**
- Create: `app/lab/services/capacity.py`
- Create: `tests/lab/test_capacity.py`

- [ ] **Step 1: Write failing tests**

Create `tests/lab/test_capacity.py`:
```python
from app.lab.services.capacity import estimate_capacity, fit_for_model
from app.lab.state.models import HardwareSpec, GPUInfo


def _hw(ram=32.0, vram=24.0, cuda=True, cores=16):
    gpus = [GPUInfo("RTX 4090", vram, "555", cuda)] if vram else []
    return HardwareSpec(
        os_name="Windows", cpu_name="x", cpu_cores_physical=cores,
        cpu_cores_logical=cores*2, ram_total_gb=ram, ram_available_gb=ram-4,
        disk_total_gb=1000.0, disk_free_gb=500.0, gpus=gpus,
        best_backend="cuda" if cuda and vram else "cpu",
    )


def test_capacity_notes_for_big_gpu():
    caps = estimate_capacity(_hw(ram=64, vram=24))
    assert "7B" in " ".join(caps.notes)
    assert caps.tier in ("excellent", "strong", "good")


def test_capacity_notes_for_small_gpu():
    caps = estimate_capacity(_hw(ram=16, vram=8))
    assert any("7B" in n or "small" in n.lower() for n in caps.notes)


def test_fit_excellent_when_vram_fits_with_headroom():
    hw = _hw(ram=64, vram=24)
    fit = fit_for_model(hw, approx_vram_gb=14.0, approx_ram_gb=20.0)
    assert fit == "excellent"


def test_fit_tight_when_vram_barely_fits():
    hw = _hw(ram=32, vram=12)
    fit = fit_for_model(hw, approx_vram_gb=11.5, approx_ram_gb=16.0)
    assert fit == "tight"


def test_fit_not_recommended_when_vram_exceeds():
    hw = _hw(ram=16, vram=8)
    fit = fit_for_model(hw, approx_vram_gb=18.0, approx_ram_gb=12.0)
    assert fit == "not_recommended"


def test_fit_cpu_fallback_when_no_gpu():
    hw = _hw(ram=32, vram=0, cuda=False)
    # model fits in RAM even without GPU
    fit = fit_for_model(hw, approx_vram_gb=14.0, approx_ram_gb=18.0)
    assert fit in ("good", "tight")  # CPU-only always has penalty
```

- [ ] **Step 2: Implement**

Create `app/lab/services/capacity.py`:
```python
"""Heuristic capacity analysis. Output strings are UX-ready (short, professional)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from app.lab.state.models import HardwareSpec


Tier = Literal["excellent", "strong", "good", "limited", "weak"]
Fit  = Literal["excellent", "good", "tight", "not_recommended"]


@dataclass
class CapacityReport:
    tier: Tier
    headline: str
    notes: list[str]


def _total_vram(hw: HardwareSpec) -> float:
    return sum(g.vram_total_gb for g in hw.gpus)


def estimate_capacity(hw: HardwareSpec) -> CapacityReport:
    vram = _total_vram(hw)
    ram = hw.ram_total_gb
    notes: list[str] = []

    if vram >= 48:
        tier: Tier = "excellent"
        headline = "Workstation-class GPU — runs any mainstream open model."
        notes.append("70B at 4-bit fits with headroom")
        notes.append("Long-context 32B comfortable")
    elif vram >= 24:
        tier = "strong"
        headline = "Excellent for 7B–14B; 32B viable with partial offload."
        notes.append("14B at 4-bit fits fully in VRAM")
        notes.append("32B at 4-bit needs partial CPU offload")
    elif vram >= 12:
        tier = "good"
        headline = "Great for 7B; 13B tight."
        notes.append("7B at 4-bit fits fully")
        notes.append("13B at 4-bit needs reduced context")
    elif vram >= 6:
        tier = "limited"
        headline = "Designed for small models up to 7B at reduced quality."
        notes.append("7B at Q4 with offload only")
        notes.append("Larger models will fall back to CPU")
    elif vram > 0:
        tier = "weak"
        headline = "Small GPU — CPU inference recommended for quality."
        notes.append("Only 3B-class or smaller fits fully on GPU")
    else:
        tier = "limited" if ram >= 32 else "weak"
        headline = "No CUDA GPU detected — CPU-only inference."
        if ram >= 64:
            notes.append("CPU can run 13B at reduced speed")
        elif ram >= 32:
            notes.append("7B at Q4 is comfortable on CPU")
        else:
            notes.append("Stick to 3B or lower for usable speed")

    if ram < 16:
        notes.append("Low system RAM — context >8k will struggle")
    if hw.disk_free_gb < 20:
        notes.append("Low free disk — GGUF files typically 4–30 GB each")

    return CapacityReport(tier=tier, headline=headline, notes=notes)


def fit_for_model(hw: HardwareSpec, approx_vram_gb: float,
                  approx_ram_gb: float) -> Fit:
    """Score a single candidate against the current hardware.
    Preference order: GPU offload → CPU fallback. Excellent/good/tight/not."""
    vram = _total_vram(hw)
    avail_ram = hw.ram_available_gb or (hw.ram_total_gb * 0.8)

    if vram >= approx_vram_gb * 1.25:
        return "excellent"
    if vram >= approx_vram_gb * 1.05:
        return "good"
    if vram >= approx_vram_gb * 0.9:
        return "tight"

    # GPU too small — can CPU carry it?
    if avail_ram >= approx_ram_gb * 1.2:
        return "good" if hw.best_backend == "cuda" else "tight"
    if avail_ram >= approx_ram_gb:
        return "tight"
    return "not_recommended"
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/lab/test_capacity.py -v`
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add app/lab/services/capacity.py tests/lab/test_capacity.py
git commit -m "lab: capacity estimator + model fit heuristic with tests"
```

---

## Task 9: Machine view

**Files:**
- Create: `app/lab/views/machine_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Write the view**

Create `app/lab/views/machine_view.py`:

```python
"""Machine view — hardware spec tiles + capacity notes."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QHBoxLayout
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, MetricTile, SectionHeader, StatusPill, KeyValueRow,
)
from app.lab.services.capacity import estimate_capacity
from app.lab.state.models import HardwareSpec
from app.lab.state.store import LabStore


class MachineView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        root.addWidget(SectionHeader("SYSTEM", "Machine"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(t.SPACE_4)
        grid.setVerticalSpacing(t.SPACE_4)
        self.cpu_tile = MetricTile("CPU", "—")
        self.ram_tile = MetricTile("Memory", "—")
        self.gpu_tile = MetricTile("GPU", "—")
        self.vram_tile = MetricTile("VRAM", "—")
        self.disk_tile = MetricTile("Disk Free", "—")
        self.backend_tile = MetricTile("Backend", "—")
        for i, tile in enumerate([self.cpu_tile, self.ram_tile, self.gpu_tile,
                                  self.vram_tile, self.disk_tile, self.backend_tile]):
            grid.addWidget(tile, i // 3, i % 3)
        root.addLayout(grid)

        self.cap_card = GlassCard()
        header_row = QHBoxLayout()
        self.cap_header = QLabel("Capacity")
        self.cap_header.setProperty("role", "title")
        self.cap_pill = StatusPill("—", "info")
        header_row.addWidget(self.cap_header)
        header_row.addStretch()
        header_row.addWidget(self.cap_pill)
        self.cap_card.body().addLayout(header_row)
        self.cap_headline = QLabel("Detecting…")
        self.cap_headline.setWordWrap(True)
        self.cap_card.body().addWidget(self.cap_headline)
        self.cap_notes = QVBoxLayout()
        self.cap_notes.setSpacing(4)
        self.cap_card.body().addLayout(self.cap_notes)
        root.addWidget(self.cap_card)

        self.det_card = GlassCard()
        det_header = QLabel("HARDWARE DETAILS")
        det_header.setProperty("role", "section")
        self.det_card.body().addWidget(det_header)
        self.row_os = KeyValueRow("OS", "—", mono=False)
        self.row_cpu_cores = KeyValueRow("CPU cores", "—")
        self.row_gpu_list = KeyValueRow("GPU(s)", "—")
        self.row_driver = KeyValueRow("NVIDIA driver", "—")
        for r in [self.row_os, self.row_cpu_cores, self.row_gpu_list, self.row_driver]:
            self.det_card.body().addWidget(r)
        root.addWidget(self.det_card)

        root.addStretch()

        self.store.hardware_changed.connect(self.render)
        self.render(self.store.hardware)

    def render(self, hw: HardwareSpec):
        self.cpu_tile.set_value(hw.cpu_name or "—",
                                f"{hw.cpu_cores_physical}c / {hw.cpu_cores_logical}t")
        self.ram_tile.set_value(f"{hw.ram_total_gb:.0f} GB",
                                f"{hw.ram_available_gb:.0f} GB available")
        if hw.gpus:
            names = ", ".join(g.name.replace("NVIDIA GeForce ", "") for g in hw.gpus)
            self.gpu_tile.set_value(names, f"{len(hw.gpus)}x detected")
            total_vram = sum(g.vram_total_gb for g in hw.gpus)
            cuda_label = "CUDA-capable" if any(g.cuda_capable for g in hw.gpus) else "no CUDA"
            self.vram_tile.set_value(f"{total_vram:.0f} GB", cuda_label)
        else:
            self.gpu_tile.set_value("None detected", "CPU-only mode")
            self.vram_tile.set_value("—", "—")
        self.disk_tile.set_value(f"{hw.disk_free_gb:.0f} GB",
                                 f"of {hw.disk_total_gb:.0f} GB")
        self.backend_tile.set_value(hw.best_backend.upper(),
                                    "recommended for this box")

        cap = estimate_capacity(hw)
        tier_to_level = {"excellent": "ok", "strong": "ok", "good": "info",
                         "limited": "warn", "weak": "err"}
        self.cap_pill.set_status(cap.tier.upper(), tier_to_level.get(cap.tier, "info"))
        self.cap_headline.setText(cap.headline)
        while self.cap_notes.count():
            w = self.cap_notes.takeAt(0).widget()
            if w:
                w.deleteLater()
        for n in cap.notes:
            row = QLabel(f"->  {n}")
            row.setProperty("role", "muted")
            self.cap_notes.addWidget(row)

        self.row_os.set_value(f"{hw.os_name} {hw.os_version}")
        self.row_cpu_cores.set_value(
            f"{hw.cpu_cores_physical} physical / {hw.cpu_cores_logical} logical")
        self.row_gpu_list.set_value(
            ", ".join(g.name for g in hw.gpus) if hw.gpus else "none")
        drivers = {g.driver for g in hw.gpus if g.driver}
        self.row_driver.set_value(", ".join(sorted(drivers)) if drivers else "—")
```

- [ ] **Step 2: Wire view + probe into shell**

Modify `app/lab/shell.py`. Add these imports at the top with the others:

```python
from app.lab.views.machine_view import MachineView
from app.lab.workers.hw_probe import HardwareProbeWorker
```

In `LabShell.__init__`, after `self._switch("overview")`:

```python
        self.replace_view("machine", MachineView(self.store, self))
        self._hw_worker = HardwareProbeWorker(self)
        self._hw_worker.detected.connect(self.store.set_hardware)
        self._hw_worker.start()
```

- [ ] **Step 3: Smoke run**

Run: `python main.py`, click "Lab", then "Machine".
Expected: tiles populate within 1–2 seconds with real data; capacity pill shows a tier.

- [ ] **Step 4: Commit**

```bash
git add app/lab/views/machine_view.py app/lab/shell.py
git commit -m "lab: Machine view — tiles + capacity card + details"
```

---

## Task 10: Runtime manager + version parser

**Files:**
- Create: `app/lab/services/runtime.py`
- Create: `tests/lab/test_runtime_parser.py`

- [ ] **Step 1: Write failing test**

Create `tests/lab/test_runtime_parser.py`:

```python
from app.lab.services.runtime import parse_version_output, detect_backend


def test_parse_version_new_format():
    out = "version: 3456 (abcd1234)\nbuilt with MSVC 19"
    assert parse_version_output(out) == "b3456"


def test_parse_version_commit_only():
    out = "version 0 (7f8e9d0)\nbuilt ..."
    assert parse_version_output(out) == "7f8e9d0"


def test_parse_version_missing():
    assert parse_version_output("") is None
    assert parse_version_output("nonsense") is None


def test_detect_backend_cuda_in_help_text():
    assert detect_backend("CUDA: yes\nGPU offload: enabled") == "cuda"


def test_detect_backend_fallback_cpu():
    assert detect_backend("no gpu mentioned") == "cpu"
```

- [ ] **Step 2: Implement**

Create `app/lab/services/runtime.py`:

```python
"""llama.cpp runtime detection. Works across common install shapes:
- `llama-server` / `llama-cli` on PATH
- user-configured path
- Windows binaries with .exe
Parsing is pure so it's testable; detection functions call subprocess."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
from app.lab.state.models import RuntimeStatus


BINARY_CANDIDATES = ["llama-server", "llama-cli", "main", "server"]


def parse_version_output(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"version[:\s]+(\d+)\s*\(([0-9a-f]+)\)", text)
    if m:
        build = int(m.group(1))
        commit = m.group(2)
        return f"b{build}" if build > 0 else commit
    m = re.search(r"version[:\s]+([0-9a-f]{7,})", text)
    if m:
        return m.group(1)
    return None


def detect_backend(help_text: str) -> str:
    lower = (help_text or "").lower()
    if "cuda" in lower:
        return "cuda"
    if "metal" in lower:
        return "metal"
    if "rocm" in lower or "hipblas" in lower:
        return "rocm"
    if "vulkan" in lower:
        return "vulkan"
    return "cpu"


def _resolve_binary(configured_path: str | None = None) -> str | None:
    if configured_path and os.path.isfile(configured_path):
        return configured_path
    for name in BINARY_CANDIDATES:
        exe = name + (".exe" if sys.platform == "win32" else "")
        p = shutil.which(exe)
        if p:
            return p
    return None


def detect_runtime(configured_path: str | None = None) -> RuntimeStatus:
    binary = _resolve_binary(configured_path)
    if not binary:
        return RuntimeStatus(installed=False, error="llama.cpp binary not found on PATH")

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        res = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=5,
            creationflags=creationflags,
        )
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        version = parse_version_output(combined)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return RuntimeStatus(installed=False, binary_path=binary, error=str(e))

    try:
        help_res = subprocess.run(
            [binary, "--help"],
            capture_output=True, text=True, timeout=5,
            creationflags=creationflags,
        )
        backend = detect_backend((help_res.stdout or "") + (help_res.stderr or ""))
    except Exception:
        backend = "cpu"

    return RuntimeStatus(
        installed=True, version=version, binary_path=binary,
        backend=backend, validated=version is not None, error=None,
    )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/lab/test_runtime_parser.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add app/lab/services/runtime.py tests/lab/test_runtime_parser.py
git commit -m "lab: runtime manager + version/backend parsers with tests"
```

---

## Task 11: Runtime probe worker + Runtime view

**Files:**
- Create: `app/lab/workers/runtime_probe.py`
- Create: `app/lab/views/runtime_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Worker**

Create `app/lab/workers/runtime_probe.py`:

```python
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.runtime import detect_runtime


class RuntimeProbeWorker(QThread):
    detected = Signal(object)

    def __init__(self, configured_path: str | None = None, parent=None):
        super().__init__(parent)
        self.configured_path = configured_path

    def run(self):
        self.detected.emit(detect_runtime(self.configured_path))
```

- [ ] **Step 2: Runtime view**

Create `app/lab/views/runtime_view.py`:

```python
"""Runtime view — llama.cpp status + install/validate actions."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
)
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, StatusPill, KeyValueRow,
)
from app.lab.state.models import RuntimeStatus
from app.lab.state.store import LabStore
from app.lab.workers.runtime_probe import RuntimeProbeWorker


INSTALL_INSTRUCTIONS = (
    "Download a prebuilt llama.cpp binary from "
    "https://github.com/ggerganov/llama.cpp/releases — pick a build "
    "matching your GPU (e.g. llama-bin-win-cuda-x64). Extract and "
    "either add the folder to PATH or point Runtime at llama-server.exe."
)


class RuntimeView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._worker: RuntimeProbeWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)
        root.addWidget(SectionHeader("INFERENCE", "Runtime"))

        self.card = GlassCard(raised=True)
        status_row = QHBoxLayout()
        title = QLabel("llama.cpp")
        title.setProperty("role", "title")
        status_row.addWidget(title)
        status_row.addStretch()
        self.pill = StatusPill("Detecting…", "info")
        status_row.addWidget(self.pill)
        self.card.body().addLayout(status_row)

        self.summary = QLabel("Looking for the llama.cpp runtime on your system.")
        self.summary.setWordWrap(True)
        self.summary.setProperty("role", "muted")
        self.card.body().addWidget(self.summary)

        self.row_version = KeyValueRow("Version", "—")
        self.row_backend = KeyValueRow("Backend", "—")
        self.row_path = KeyValueRow("Binary", "—")
        for r in [self.row_version, self.row_backend, self.row_path]:
            self.card.body().addWidget(r)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(t.SPACE_3)
        self.revalidate_btn = QPushButton("Revalidate")
        self.revalidate_btn.setProperty("variant", "ghost")
        self.revalidate_btn.clicked.connect(lambda: self.kick_probe())
        self.locate_btn = QPushButton("Locate binary…")
        self.locate_btn.setProperty("variant", "ghost")
        self.locate_btn.clicked.connect(self._pick_binary)
        self.install_btn = QPushButton("Install guide")
        self.install_btn.clicked.connect(self._show_install)
        btn_row.addWidget(self.revalidate_btn)
        btn_row.addWidget(self.locate_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.install_btn)
        self.card.body().addLayout(btn_row)
        root.addWidget(self.card)

        self.install_panel = GlassCard()
        self.install_panel.body().addWidget(SectionHeader("SETUP", "Install llama.cpp"))
        guide = QLabel(INSTALL_INSTRUCTIONS)
        guide.setWordWrap(True)
        self.install_panel.body().addWidget(guide)
        self.install_panel.setVisible(False)
        root.addWidget(self.install_panel)

        root.addStretch()
        self.store.runtime_changed.connect(self.render)

    def kick_probe(self, configured_path: str | None = None):
        if self._worker and self._worker.isRunning():
            return
        self._worker = RuntimeProbeWorker(configured_path, self)
        self._worker.detected.connect(self.store.set_runtime)
        self._worker.start()

    def render(self, rs: RuntimeStatus):
        if rs.installed and rs.validated:
            self.pill.set_status("READY", "ok")
            self.summary.setText("Runtime detected and validated.")
        elif rs.installed:
            self.pill.set_status("PARTIAL", "warn")
            self.summary.setText("Binary found but version could not be confirmed.")
        else:
            self.pill.set_status("MISSING", "err")
            self.summary.setText(rs.error or "llama.cpp not found.")
        self.row_version.set_value(rs.version or "—")
        self.row_backend.set_value((rs.backend or "—").upper())
        self.row_path.set_value(rs.binary_path or "—")

    def _pick_binary(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate llama.cpp binary", "",
            "Executables (*.exe);;All files (*)",
        )
        if path:
            self.kick_probe(path)

    def _show_install(self):
        self.install_panel.setVisible(not self.install_panel.isVisible())
```

- [ ] **Step 3: Wire into shell**

Modify `app/lab/shell.py`. Add import:

```python
from app.lab.views.runtime_view import RuntimeView
```

After the Machine view wiring:

```python
        self.runtime_view = RuntimeView(self.store, self)
        self.replace_view("runtime", self.runtime_view)
        self.runtime_view.kick_probe()
```

- [ ] **Step 4: Smoke run**

Run: `python main.py` → Lab → Runtime.
Expected: pill goes from "Detecting…" to "READY" (if llama.cpp is on PATH) or "MISSING"; "Locate binary…" opens file picker; "Install guide" toggles the install card.

- [ ] **Step 5: Commit**

```bash
git add app/lab/workers/runtime_probe.py app/lab/views/runtime_view.py app/lab/shell.py
git commit -m "lab: Runtime view + probe worker"
```

---

## Task 12: GGUF header parser

**Files:**
- Create: `app/lab/services/gguf.py`
- Create: `tests/lab/test_gguf_parser.py`

- [ ] **Step 1: Write failing tests**

Create `tests/lab/test_gguf_parser.py`:

```python
import struct
from app.lab.services.gguf import parse_gguf_header, _infer_quant_from_name


def _s(v: str) -> bytes:
    b = v.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def _pack_kv_string(key: str, value: str) -> bytes:
    # type id 8 = STRING
    return _s(key) + struct.pack("<I", 8) + _s(value)


def _pack_kv_u32(key: str, value: int) -> bytes:
    # type id 4 = UINT32
    return _s(key) + struct.pack("<I", 4) + struct.pack("<I", value)


def test_parse_minimal_gguf_header(tmp_path):
    path = tmp_path / "tiny.gguf"
    kvs = _pack_kv_string("general.architecture", "llama")
    kvs += _pack_kv_u32("llama.context_length", 8192)
    header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 2) + kvs
    path.write_bytes(header + b"\x00" * 64)
    meta = parse_gguf_header(str(path))
    assert meta is not None
    assert meta["architecture"] == "llama"
    assert meta["context_length"] == 8192


def test_parse_rejects_bad_magic(tmp_path):
    path = tmp_path / "bad.gguf"
    path.write_bytes(b"NOPE" + b"\x00" * 128)
    assert parse_gguf_header(str(path)) is None


def test_infer_quant_from_name():
    assert _infer_quant_from_name("Qwen2.5-7B-Instruct-Q4_K_M.gguf") == "Q4_K_M"
    assert _infer_quant_from_name("llama-3-8b.Q8_0.gguf") == "Q8_0"
    assert _infer_quant_from_name("model.bf16.gguf") == "BF16"
    assert _infer_quant_from_name("random.gguf") == ""
```

- [ ] **Step 2: Implement**

Create `app/lab/services/gguf.py`:

```python
"""Bounded GGUF v3 header reader. Reads only enough to extract architecture,
context length, and param count. Safe against arbitrary files — bails out on
bad magic, unknown types, or an unreasonable KV count."""
from __future__ import annotations
import os
import re
import struct


_T_UINT8, _T_INT8 = 0, 1
_T_UINT16, _T_INT16 = 2, 3
_T_UINT32, _T_INT32 = 4, 5
_T_FLOAT32, _T_BOOL = 6, 7
_T_STRING, _T_ARRAY = 8, 9
_T_UINT64, _T_INT64 = 10, 11
_T_FLOAT64 = 12

_SCALAR_FMT = {
    _T_UINT8: "<B", _T_INT8: "<b",
    _T_UINT16: "<H", _T_INT16: "<h",
    _T_UINT32: "<I", _T_INT32: "<i",
    _T_FLOAT32: "<f", _T_BOOL: "<?",
    _T_UINT64: "<Q", _T_INT64: "<q",
    _T_FLOAT64: "<d",
}

_MAX_KVS = 4096
_MAX_BYTES = 2 * 1024 * 1024


def _infer_quant_from_name(filename: str) -> str:
    m = re.search(r"[.\-_]([QIq]\d[a-zA-Z0-9_]+|BF16|F16|F32|bf16|f16|f32)", filename)
    return m.group(1).upper() if m else ""


def _read_string(buf: memoryview, off: int) -> tuple[str, int]:
    (ln,) = struct.unpack_from("<Q", buf, off); off += 8
    s = bytes(buf[off:off + ln]).decode("utf-8", errors="replace")
    return s, off + ln


def _skip_value(buf: memoryview, off: int, type_id: int) -> int:
    if type_id in _SCALAR_FMT:
        return off + struct.calcsize(_SCALAR_FMT[type_id])
    if type_id == _T_STRING:
        _, off = _read_string(buf, off)
        return off
    if type_id == _T_ARRAY:
        (inner,) = struct.unpack_from("<I", buf, off); off += 4
        (count,) = struct.unpack_from("<Q", buf, off); off += 8
        for _ in range(count):
            off = _skip_value(buf, off, inner)
        return off
    raise ValueError(f"unknown gguf type id {type_id}")


def _read_value(buf: memoryview, off: int, type_id: int):
    if type_id in _SCALAR_FMT:
        fmt = _SCALAR_FMT[type_id]
        (v,) = struct.unpack_from(fmt, buf, off)
        return v, off + struct.calcsize(fmt)
    if type_id == _T_STRING:
        return _read_string(buf, off)
    return None, _skip_value(buf, off, type_id)


def parse_gguf_header(path: str) -> dict | None:
    """Return a dict with any of: architecture, context_length, param_count_b,
    block_count, embedding_length, quant. None on invalid/unreadable files."""
    try:
        size = os.path.getsize(path)
        read_n = min(_MAX_BYTES, size)
        with open(path, "rb") as f:
            raw = f.read(read_n)
    except OSError:
        return None
    if len(raw) < 24 or raw[:4] != b"GGUF":
        return None
    buf = memoryview(raw)
    (version,) = struct.unpack_from("<I", buf, 4)
    (kv_count,) = struct.unpack_from("<Q", buf, 16)
    if kv_count > _MAX_KVS:
        return None
    off = 24

    meta: dict = {"_version": version}
    for _ in range(kv_count):
        try:
            key, off = _read_string(buf, off)
            (type_id,) = struct.unpack_from("<I", buf, off); off += 4
            val, off = _read_value(buf, off, type_id)
        except (struct.error, ValueError, UnicodeDecodeError):
            break
        if key == "general.architecture":
            meta["architecture"] = val
        elif key.endswith(".context_length"):
            meta["context_length"] = int(val) if val is not None else 0
        elif key.endswith(".block_count"):
            meta["block_count"] = int(val) if val is not None else 0
        elif key.endswith(".embedding_length"):
            meta["embedding_length"] = int(val) if val is not None else 0
        elif key == "general.name":
            meta["name"] = val
        elif key == "general.parameter_count":
            try:
                meta["param_count_b"] = int(val) / 1e9
            except (TypeError, ValueError):
                pass

    meta["quant"] = _infer_quant_from_name(os.path.basename(path))
    return meta
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/lab/test_gguf_parser.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add app/lab/services/gguf.py tests/lab/test_gguf_parser.py
git commit -m "lab: bounded GGUF header parser with tests"
```

---

## Task 13: Model library service + scanner worker

**Files:**
- Create: `app/lab/services/library.py`
- Create: `app/lab/workers/library_scanner.py`
- Create: `tests/lab/test_library.py`

- [ ] **Step 1: Config — model directory lives in AppConfig**

Modify `app/models.py` — add a field to `AppConfig`:

```python
    models_dir: str = ""   # user-configurable folder containing .gguf files
```

(Put it next to `ssh_key_path`. Existing configs load fine — dataclass default handles missing keys.)

- [ ] **Step 2: Write failing test for library scan**

Create `tests/lab/test_library.py`:

```python
import struct
from app.lab.services.library import scan_directory
from app.lab.services.gguf import _infer_quant_from_name


def _write_fake_gguf(path, arch="llama", ctx=8192):
    def s(v):
        b = v.encode("utf-8")
        return struct.pack("<Q", len(b)) + b
    kvs = s("general.architecture") + struct.pack("<I", 8) + s(arch)
    kvs += s("llama.context_length") + struct.pack("<I", 4) + struct.pack("<I", ctx)
    header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 2) + kvs
    path.write_bytes(header + b"\x00" * 1024)


def test_scan_empty_dir(tmp_path):
    assert scan_directory(str(tmp_path)) == []


def test_scan_finds_gguf_only(tmp_path):
    (tmp_path / "readme.txt").write_text("hi")
    a = tmp_path / "Qwen2.5-7B-Q4_K_M.gguf"
    _write_fake_gguf(a, "qwen2", 32768)
    items = scan_directory(str(tmp_path))
    assert len(items) == 1
    m = items[0]
    assert m.name == "Qwen2.5-7B-Q4_K_M"
    assert m.architecture == "qwen2"
    assert m.context_length == 32768
    assert m.quant == "Q4_K_M"
    assert m.size_bytes > 0
    assert m.valid is True


def test_scan_marks_invalid_gguf(tmp_path):
    bad = tmp_path / "broken.gguf"
    bad.write_bytes(b"NOPE" + b"\x00" * 128)
    items = scan_directory(str(tmp_path))
    assert len(items) == 1
    assert items[0].valid is False
    assert items[0].error is not None


def test_scan_handles_missing_dir():
    assert scan_directory("/nonexistent/path/xyz") == []
```

- [ ] **Step 3: Implement**

Create `app/lab/services/library.py`:

```python
"""Local model library. Scans a directory for .gguf files, reads their
headers, and returns ModelFile records."""
from __future__ import annotations
import os
from app.lab.services.gguf import parse_gguf_header
from app.lab.state.models import ModelFile


def scan_directory(path: str) -> list[ModelFile]:
    if not path or not os.path.isdir(path):
        return []
    out: list[ModelFile] = []
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        return []
    for name in entries:
        if not name.lower().endswith(".gguf"):
            continue
        full = os.path.join(path, name)
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        display = os.path.splitext(name)[0]
        meta = parse_gguf_header(full)
        if meta is None:
            out.append(ModelFile(
                path=full, name=display, size_bytes=size,
                valid=False, error="invalid or unreadable GGUF header",
            ))
            continue
        out.append(ModelFile(
            path=full, name=display, size_bytes=size,
            architecture=meta.get("architecture", ""),
            param_count_b=float(meta.get("param_count_b", 0.0) or 0.0),
            context_length=int(meta.get("context_length", 0) or 0),
            quant=meta.get("quant", ""),
            valid=True,
        ))
    return out
```

- [ ] **Step 4: Scanner worker**

Create `app/lab/workers/library_scanner.py`:

```python
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.library import scan_directory


class LibraryScannerWorker(QThread):
    scanned = Signal(list)   # list[ModelFile]

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        self.scanned.emit(scan_directory(self.path))
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/lab/test_library.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/lab/services/library.py app/lab/workers/library_scanner.py tests/lab/test_library.py
git commit -m "lab: library scanner + ModelFile parsing + tests"
```

---

## Task 14: Library view

**Files:**
- Create: `app/lab/components/model_card.py`
- Create: `app/lab/views/library_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Model card component**

Create `app/lab/components/model_card.py`:

```python
"""ModelCard — premium card for a local model file."""
from __future__ import annotations
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import GlassCard, StatusPill
from app.lab.state.models import ModelFile


def _fmt_size(n: int) -> str:
    gb = n / (1024 ** 3)
    return f"{gb:.1f} GB" if gb >= 1 else f"{n / (1024**2):.0f} MB"


class ModelCard(GlassCard):
    open_requested = Signal(str)     # emits model path
    benchmark_requested = Signal(str)

    def __init__(self, model: ModelFile, parent=None):
        super().__init__(parent=parent)
        self.model = model

        header = QHBoxLayout()
        name = QLabel(model.name)
        name.setProperty("role", "title")
        header.addWidget(name)
        header.addStretch()
        pill = StatusPill(model.quant or "GGUF", "info" if model.valid else "err")
        header.addWidget(pill)
        self.body().addLayout(header)

        meta_line = []
        if model.architecture:
            meta_line.append(model.architecture.upper())
        if model.context_length:
            meta_line.append(f"ctx {model.context_length:,}")
        if model.param_count_b > 0:
            meta_line.append(f"{model.param_count_b:.1f}B params")
        meta_line.append(_fmt_size(model.size_bytes))
        meta = QLabel("  ·  ".join(meta_line))
        meta.setProperty("role", "muted")
        self.body().addWidget(meta)

        if not model.valid:
            err = QLabel(f"⚠  {model.error or 'invalid file'}")
            err.setStyleSheet(f"color: {t.ERR};")
            err.setWordWrap(True)
            self.body().addWidget(err)

        path_lbl = QLabel(model.path)
        path_lbl.setProperty("role", "mono")
        path_lbl.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 8pt;")
        self.body().addWidget(path_lbl)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_3)
        self.open_btn = QPushButton("Details")
        self.open_btn.setProperty("variant", "ghost")
        self.open_btn.clicked.connect(lambda: self.open_requested.emit(model.path))
        self.bench_btn = QPushButton("Benchmark")
        self.bench_btn.clicked.connect(lambda: self.benchmark_requested.emit(model.path))
        self.bench_btn.setEnabled(model.valid)
        actions.addWidget(self.open_btn)
        actions.addStretch()
        actions.addWidget(self.bench_btn)
        self.body().addLayout(actions)
```

- [ ] **Step 2: Library view**

Create `app/lab/views/library_view.py`:

```python
"""Library view — grid of installed GGUF models + import/scan controls."""
from __future__ import annotations
import os
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QScrollArea, QGridLayout, QMessageBox,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import SectionHeader, GlassCard
from app.lab.components.model_card import ModelCard
from app.lab.state.store import LabStore
from app.lab.workers.library_scanner import LibraryScannerWorker


class LibraryView(QWidget):
    model_detail_requested = Signal(str)
    benchmark_requested = Signal(str)

    def __init__(self, store: LabStore, models_dir: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.models_dir = models_dir
        self._worker: LibraryScannerWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        head.addWidget(SectionHeader("MODELS", "Library"))
        head.addStretch()
        self.dir_lbl = QLabel(self.models_dir or "No directory configured")
        self.dir_lbl.setProperty("role", "muted")
        head.addWidget(self.dir_lbl)
        self.pick_btn = QPushButton("Change folder…")
        self.pick_btn.setProperty("variant", "ghost")
        self.pick_btn.clicked.connect(self._pick_folder)
        head.addWidget(self.pick_btn)
        self.import_btn = QPushButton("Import GGUF")
        self.import_btn.clicked.connect(self._import_file)
        head.addWidget(self.import_btn)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(t.SPACE_4)
        self.grid.setVerticalSpacing(t.SPACE_4)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        self.empty = GlassCard()
        e_title = QLabel("No models yet")
        e_title.setProperty("role", "title")
        e_body = QLabel("Point the Library at a folder containing .gguf files "
                        "or import a file to get started.")
        e_body.setWordWrap(True)
        e_body.setProperty("role", "muted")
        self.empty.body().addWidget(e_title)
        self.empty.body().addWidget(e_body)
        root.addWidget(self.empty)

        self.store.library_changed.connect(self._render)

    def set_models_dir(self, path: str):
        self.models_dir = path
        self.dir_lbl.setText(path or "No directory configured")
        self.rescan()

    def rescan(self):
        if not self.models_dir:
            self.store.set_library([])
            return
        if self._worker and self._worker.isRunning():
            return
        self._worker = LibraryScannerWorker(self.models_dir, self)
        self._worker.scanned.connect(self.store.set_library)
        self._worker.start()

    def _render(self, items: list):
        # clear
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not items:
            self.empty.setVisible(True)
            return
        self.empty.setVisible(False)
        for i, m in enumerate(items):
            card = ModelCard(m)
            card.open_requested.connect(self.model_detail_requested.emit)
            card.benchmark_requested.connect(self.benchmark_requested.emit)
            self.grid.addWidget(card, i // 2, i % 2)

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose models folder", self.models_dir)
        if path:
            self.set_models_dir(path)

    def _import_file(self):
        if not self.models_dir:
            QMessageBox.warning(self, "Choose a folder first",
                                "Pick a models folder before importing.")
            return
        src, _ = QFileDialog.getOpenFileName(
            self, "Import GGUF file", "", "GGUF files (*.gguf)",
        )
        if not src:
            return
        dst = os.path.join(self.models_dir, os.path.basename(src))
        if os.path.exists(dst):
            QMessageBox.warning(self, "Already exists",
                                f"{os.path.basename(src)} is already in the library.")
            return
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        self.rescan()
```

- [ ] **Step 3: Wire into shell**

Modify `app/lab/shell.py`. Constructor needs access to config to know the models dir. Change signature to accept a config:

```python
class LabShell(QWidget):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        ...
        self._config = config
```

At the end of `__init__`, after Runtime view:

```python
        models_dir = getattr(self._config, "models_dir", "") if self._config else ""
        self.library_view = LibraryView(self.store, models_dir, self)
        self.replace_view("library", self.library_view)
        self.library_view.rescan()
```

Add import:

```python
from app.lab.views.library_view import LibraryView
```

Modify `app/ui/main_window.py` where `LabShell()` is instantiated — pass the config:

```python
        self.lab_shell = LabShell(self.config)
```

- [ ] **Step 4: Smoke run**

Run: `python main.py` → Lab → Library.
Expected: empty state renders initially; "Change folder…" opens a picker; after picking a folder with .gguf files, cards appear in a 2-column grid.

- [ ] **Step 5: Commit**

```bash
git add app/lab/components/model_card.py app/lab/views/library_view.py app/lab/shell.py app/ui/main_window.py
git commit -m "lab: Library view + ModelCard + import flow"
```

---

## Task 15: Curated catalog + recommendation engine

**Files:**
- Create: `app/lab/assets/catalog.json`
- Create: `app/lab/services/catalog.py`
- Create: `app/lab/services/recommender.py`
- Create: `tests/lab/test_recommender.py`

- [ ] **Step 1: Catalog JSON (curated starter set)**

Create `app/lab/assets/catalog.json`:

```json
[
  {
    "id": "qwen2.5-7b-instruct-q4km",
    "family": "Qwen2.5",
    "display_name": "Qwen2.5 7B Instruct",
    "params_b": 7.6,
    "quant": "Q4_K_M",
    "repo_id": "bartowski/Qwen2.5-7B-Instruct-GGUF",
    "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    "approx_size_gb": 4.7,
    "approx_vram_gb": 6.5,
    "approx_ram_gb": 8.0,
    "context_length": 32768,
    "use_cases": ["chat", "balanced"],
    "quality_tier": 4,
    "notes": "Strong general-purpose chat with long context support."
  },
  {
    "id": "qwen2.5-coder-7b-q4km",
    "family": "Qwen2.5-Coder",
    "display_name": "Qwen2.5-Coder 7B",
    "params_b": 7.6,
    "quant": "Q4_K_M",
    "repo_id": "bartowski/Qwen2.5-Coder-7B-Instruct-GGUF",
    "filename": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
    "approx_size_gb": 4.7,
    "approx_vram_gb": 6.5,
    "approx_ram_gb": 8.0,
    "context_length": 32768,
    "use_cases": ["coding"],
    "quality_tier": 5,
    "notes": "Top open coding model in its size class."
  },
  {
    "id": "qwen2.5-14b-instruct-q4km",
    "family": "Qwen2.5",
    "display_name": "Qwen2.5 14B Instruct",
    "params_b": 14.0,
    "quant": "Q4_K_M",
    "repo_id": "bartowski/Qwen2.5-14B-Instruct-GGUF",
    "filename": "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
    "approx_size_gb": 8.9,
    "approx_vram_gb": 11.5,
    "approx_ram_gb": 14.0,
    "context_length": 32768,
    "use_cases": ["chat", "quality"],
    "quality_tier": 5,
    "notes": "Best mid-size general model — noticeably sharper than 7B."
  },
  {
    "id": "llama-3.1-8b-instruct-q4km",
    "family": "Llama 3.1",
    "display_name": "Llama 3.1 8B Instruct",
    "params_b": 8.0,
    "quant": "Q4_K_M",
    "repo_id": "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
    "filename": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    "approx_size_gb": 4.9,
    "approx_vram_gb": 7.0,
    "approx_ram_gb": 8.5,
    "context_length": 131072,
    "use_cases": ["chat", "long_context"],
    "quality_tier": 4,
    "notes": "128k context window — great for large document tasks."
  },
  {
    "id": "phi-3.5-mini-q4km",
    "family": "Phi-3.5",
    "display_name": "Phi-3.5 Mini",
    "params_b": 3.8,
    "quant": "Q4_K_M",
    "repo_id": "bartowski/Phi-3.5-mini-instruct-GGUF",
    "filename": "Phi-3.5-mini-instruct-Q4_K_M.gguf",
    "approx_size_gb": 2.4,
    "approx_vram_gb": 3.5,
    "approx_ram_gb": 5.0,
    "context_length": 131072,
    "use_cases": ["fast", "low_ram"],
    "quality_tier": 3,
    "notes": "Runs comfortably on modest hardware with long context."
  },
  {
    "id": "gemma-2-9b-it-q4km",
    "family": "Gemma 2",
    "display_name": "Gemma 2 9B Instruct",
    "params_b": 9.2,
    "quant": "Q4_K_M",
    "repo_id": "bartowski/gemma-2-9b-it-GGUF",
    "filename": "gemma-2-9b-it-Q4_K_M.gguf",
    "approx_size_gb": 5.8,
    "approx_vram_gb": 8.0,
    "approx_ram_gb": 10.0,
    "context_length": 8192,
    "use_cases": ["chat"],
    "quality_tier": 4,
    "notes": "Polished, safety-tuned assistant from Google."
  },
  {
    "id": "qwen2.5-32b-instruct-q4km",
    "family": "Qwen2.5",
    "display_name": "Qwen2.5 32B Instruct",
    "params_b": 32.0,
    "quant": "Q4_K_M",
    "repo_id": "bartowski/Qwen2.5-32B-Instruct-GGUF",
    "filename": "Qwen2.5-32B-Instruct-Q4_K_M.gguf",
    "approx_size_gb": 19.8,
    "approx_vram_gb": 22.0,
    "approx_ram_gb": 26.0,
    "context_length": 32768,
    "use_cases": ["quality", "long_context"],
    "quality_tier": 5,
    "notes": "Flagship quality at home — needs a 24 GB GPU for pure offload."
  },
  {
    "id": "tinyllama-1.1b-chat-q8",
    "family": "TinyLlama",
    "display_name": "TinyLlama 1.1B Chat",
    "params_b": 1.1,
    "quant": "Q8_0",
    "repo_id": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",
    "filename": "tinyllama-1.1b-chat-v1.0.Q8_0.gguf",
    "approx_size_gb": 1.2,
    "approx_vram_gb": 2.0,
    "approx_ram_gb": 2.5,
    "context_length": 2048,
    "use_cases": ["fast", "low_ram"],
    "quality_tier": 2,
    "notes": "Smoke-test model. Answers are limited; loads anywhere."
  }
]
```

- [ ] **Step 2: Catalog loader**

Create `app/lab/services/catalog.py`:

```python
"""Loads the bundled curated model catalog."""
from __future__ import annotations
import json
import os
from app.lab.state.models import CatalogEntry


_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "assets", "catalog.json",
)


def load_catalog() -> list[CatalogEntry]:
    try:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    out: list[CatalogEntry] = []
    for item in raw:
        try:
            out.append(CatalogEntry(**item))
        except TypeError:
            continue
    return out
```

- [ ] **Step 3: Recommender tests**

Create `tests/lab/test_recommender.py`:

```python
from app.lab.services.recommender import recommend
from app.lab.state.models import CatalogEntry, HardwareSpec, GPUInfo


def _hw(vram=24.0, ram=32.0):
    gpus = [GPUInfo("RTX 4090", vram, "555", True)] if vram else []
    return HardwareSpec(
        os_name="Windows", cpu_name="x", cpu_cores_physical=16,
        cpu_cores_logical=32, ram_total_gb=ram, ram_available_gb=ram-4,
        disk_total_gb=1000.0, disk_free_gb=500.0, gpus=gpus,
        best_backend="cuda" if vram else "cpu",
    )


def _cat(**kwargs):
    base = dict(
        id="x", family="x", display_name="x", params_b=7.0, quant="Q4_K_M",
        repo_id="x", filename="x.gguf",
        approx_size_gb=4.0, approx_vram_gb=7.0, approx_ram_gb=8.0,
        context_length=8192, use_cases=["chat"], quality_tier=4, notes="",
    )
    base.update(kwargs)
    return CatalogEntry(**base)


def test_recommend_ranks_higher_quality_first():
    cat = [
        _cat(id="a", params_b=7, quality_tier=3, approx_vram_gb=6),
        _cat(id="b", params_b=7, quality_tier=5, approx_vram_gb=6),
        _cat(id="c", params_b=7, quality_tier=4, approx_vram_gb=6),
    ]
    recs = recommend(_hw(), cat)
    assert [r.entry.id for r in recs[:3]] == ["b", "c", "a"]


def test_recommend_filters_by_use_case():
    cat = [
        _cat(id="c1", use_cases=["coding"]),
        _cat(id="c2", use_cases=["chat"]),
    ]
    recs = recommend(_hw(), cat, use_case="coding")
    assert [r.entry.id for r in recs] == ["c1"]


def test_recommend_marks_not_recommended_for_oversized():
    cat = [_cat(id="big", params_b=70, approx_vram_gb=50, approx_ram_gb=64)]
    recs = recommend(_hw(vram=12, ram=32), cat)
    assert recs[0].fit == "not_recommended"


def test_recommend_explains_reasons():
    cat = [_cat(id="a", params_b=7, approx_vram_gb=6)]
    recs = recommend(_hw(vram=24), cat)
    assert any("fits" in r.lower() or "excellent" in r.lower()
               for r in recs[0].reasons)
```

- [ ] **Step 4: Implement recommender**

Create `app/lab/services/recommender.py`:

```python
"""Ranks curated catalog entries against the current hardware and optional
use-case filter. Deterministic, pure, testable."""
from __future__ import annotations
from app.lab.services.capacity import fit_for_model
from app.lab.state.models import CatalogEntry, HardwareSpec, Recommendation


_FIT_SCORE = {"excellent": 100, "good": 70, "tight": 40, "not_recommended": 0}


def _reasons(hw: HardwareSpec, e: CatalogEntry, fit: str) -> list[str]:
    vram = sum(g.vram_total_gb for g in hw.gpus)
    out: list[str] = []
    if fit == "excellent":
        out.append("Fits entirely in VRAM with headroom.")
    elif fit == "good":
        out.append("Good fit — runs smoothly on this machine.")
    elif fit == "tight":
        out.append("Will run but with limited context / slower speed.")
    else:
        out.append("Exceeds available memory — not recommended.")
    if vram and e.approx_vram_gb <= vram:
        out.append(f"Needs ~{e.approx_vram_gb:.0f} GB VRAM (you have {vram:.0f} GB).")
    elif not vram:
        out.append(f"CPU-only path: needs ~{e.approx_ram_gb:.0f} GB RAM.")
    if e.context_length >= 32768:
        out.append(f"Long context ({e.context_length:,} tokens).")
    return out


def recommend(hw: HardwareSpec, catalog: list[CatalogEntry],
              use_case: str | None = None) -> list[Recommendation]:
    items = catalog
    if use_case:
        items = [e for e in catalog if use_case in e.use_cases]
    scored: list[Recommendation] = []
    for e in items:
        fit = fit_for_model(hw, e.approx_vram_gb, e.approx_ram_gb)
        base = _FIT_SCORE[fit]
        # Reward quality, mildly penalize unused size (bigger isn't always better
        # on modest hardware).
        score = base + e.quality_tier * 10
        if fit == "not_recommended":
            score = -e.params_b   # keep them present but last
        scored.append(Recommendation(
            entry=e, fit=fit, score=score, reasons=_reasons(hw, e, fit),
        ))
    scored.sort(key=lambda r: r.score, reverse=True)
    return scored
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/lab/test_recommender.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app/lab/assets/catalog.json app/lab/services/catalog.py app/lab/services/recommender.py tests/lab/test_recommender.py
git commit -m "lab: curated catalog + recommendation engine with tests"
```

---

## Task 16: Discover view

**Files:**
- Create: `app/lab/components/recommendation_card.py`
- Create: `app/lab/views/discover_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Recommendation card**

Create `app/lab/components/recommendation_card.py`:

```python
"""RecommendationCard — used in Discover view. One per catalog entry."""
from __future__ import annotations
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import GlassCard, StatusPill
from app.lab.state.models import Recommendation


_FIT_LEVEL = {"excellent": "ok", "good": "info", "tight": "warn", "not_recommended": "err"}


class RecommendationCard(GlassCard):
    install_requested = Signal(str)   # emits catalog entry id

    def __init__(self, rec: Recommendation, parent=None):
        super().__init__(parent=parent)
        self.rec = rec

        header = QHBoxLayout()
        title = QLabel(rec.entry.display_name)
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(StatusPill(rec.fit.replace("_", " ").upper(),
                                    _FIT_LEVEL[rec.fit]))
        self.body().addLayout(header)

        meta = QLabel(
            f"{rec.entry.family}  ·  {rec.entry.params_b:.1f}B  ·  "
            f"{rec.entry.quant}  ·  ctx {rec.entry.context_length:,}  ·  "
            f"~{rec.entry.approx_size_gb:.1f} GB"
        )
        meta.setProperty("role", "muted")
        self.body().addWidget(meta)

        if rec.entry.notes:
            note = QLabel(rec.entry.notes)
            note.setWordWrap(True)
            self.body().addWidget(note)

        if rec.reasons:
            reasons = QVBoxLayout()
            reasons.setSpacing(2)
            for r in rec.reasons:
                lbl = QLabel(f"->  {r}")
                lbl.setProperty("role", "muted")
                reasons.addWidget(lbl)
            self.body().addLayout(reasons)

        actions = QHBoxLayout()
        stars = "★" * rec.entry.quality_tier + "☆" * (5 - rec.entry.quality_tier)
        quality = QLabel(stars)
        quality.setStyleSheet(f"color: {t.ACCENT}; font-size: 11pt;")
        actions.addWidget(quality)
        actions.addStretch()
        self.install_btn = QPushButton("Install")
        self.install_btn.setEnabled(rec.fit != "not_recommended")
        self.install_btn.clicked.connect(
            lambda: self.install_requested.emit(rec.entry.id))
        actions.addWidget(self.install_btn)
        self.body().addLayout(actions)
```

- [ ] **Step 2: Discover view**

Create `app/lab/views/discover_view.py`:

```python
"""Discover view — filterable list of catalog recommendations ranked for the
current hardware. Drives the Download flow in Task 17."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea, QPushButton,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import SectionHeader
from app.lab.components.recommendation_card import RecommendationCard
from app.lab.services.catalog import load_catalog
from app.lab.services.recommender import recommend
from app.lab.state.store import LabStore


USE_CASES = [
    ("all", "All models"),
    ("chat", "Chat"),
    ("coding", "Coding"),
    ("quality", "Best quality"),
    ("fast", "Fastest"),
    ("long_context", "Long context"),
    ("low_ram", "Low RAM"),
]


class DiscoverView(QWidget):
    install_requested = Signal(str)   # catalog entry id

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.store.set_catalog(load_catalog())

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        head.addWidget(SectionHeader("CATALOG", "Discover"))
        head.addStretch()
        self.filter = QComboBox()
        for key, label in USE_CASES:
            self.filter.addItem(label, key)
        self.filter.currentIndexChanged.connect(lambda _: self._rerank())
        head.addWidget(self.filter)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(t.SPACE_4)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.store.hardware_changed.connect(lambda _: self._rerank())
        self.store.catalog_changed.connect(lambda _: self._rerank())
        self._rerank()

    def _rerank(self):
        use_case = self.filter.currentData()
        uc = None if use_case == "all" else use_case
        recs = recommend(self.store.hardware, self.store.catalog, uc)
        self.store.set_recommendations(recs)

        while self.list_lay.count():
            w = self.list_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for r in recs:
            card = RecommendationCard(r)
            card.install_requested.connect(self.install_requested.emit)
            self.list_lay.addWidget(card)
        self.list_lay.addStretch()
```

- [ ] **Step 3: Wire into shell**

Modify `app/lab/shell.py`. Import:

```python
from app.lab.views.discover_view import DiscoverView
```

After Library view wiring:

```python
        self.discover_view = DiscoverView(self.store, self)
        self.replace_view("discover", self.discover_view)
```

- [ ] **Step 4: Smoke run**

Run: `python main.py` → Lab → Discover.
Expected: cards render ranked by fit, filter dropdown reorders.

- [ ] **Step 5: Commit**

```bash
git add app/lab/components/recommendation_card.py app/lab/views/discover_view.py app/lab/shell.py
git commit -m "lab: Discover view + recommendation cards + filter"
```

---

## Task 17: Download manager + worker

**Files:**
- Create: `app/lab/services/downloader.py`
- Create: `app/lab/workers/download_worker.py`
- Create: `tests/lab/test_downloader.py`

HuggingFace exposes each file at `https://huggingface.co/{repo_id}/resolve/main/{filename}`. We stream with `urllib.request` + range header for resume.

- [ ] **Step 1: Write failing tests (URL builder only — no network)**

Create `tests/lab/test_downloader.py`:

```python
from app.lab.services.downloader import build_hf_url, humanize_speed


def test_build_hf_url_default():
    url = build_hf_url("bartowski/Qwen2.5-7B-Instruct-GGUF",
                       "Qwen2.5-7B-Instruct-Q4_K_M.gguf")
    assert url == ("https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
                   "/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf")


def test_build_hf_url_with_revision():
    url = build_hf_url("foo/bar", "x.gguf", revision="v1")
    assert "/resolve/v1/" in url


def test_humanize_speed():
    assert humanize_speed(0) == "0 B/s"
    assert humanize_speed(2048).endswith("KB/s")
    assert humanize_speed(10 * 1024 * 1024).endswith("MB/s")
```

- [ ] **Step 2: Implement**

Create `app/lab/services/downloader.py`:

```python
"""HuggingFace GGUF downloader — raw urllib, resumable via HTTP Range."""
from __future__ import annotations
import os
import urllib.request


def build_hf_url(repo_id: str, filename: str, revision: str = "main") -> str:
    return f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}"


def humanize_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec <= 0:
        return "0 B/s"
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    if bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    if bytes_per_sec < 1024 ** 3:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
    return f"{bytes_per_sec / (1024 ** 3):.2f} GB/s"


def download(url: str, dest_path: str, hf_token: str | None = None,
             chunk_size: int = 1024 * 1024,
             progress_cb=None, cancel_cb=None) -> None:
    """Stream to dest_path. Resumes if dest_path exists. Raises on hard failure.
    progress_cb(downloaded, total, speed) called every chunk.
    cancel_cb() -> bool: truthy return aborts cleanly."""
    headers = {"User-Agent": "vastai-app/lab"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
    existing = 0
    if os.path.exists(dest_path):
        existing = os.path.getsize(dest_path)
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

    req = urllib.request.Request(url, headers=headers)
    import time
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length") or 0) + existing
        mode = "ab" if existing > 0 and resp.status in (206, 200) else "wb"
        if resp.status == 200:
            existing = 0   # server ignored Range — restart
            mode = "wb"
        with open(dest_path, mode) as f:
            downloaded = existing
            t_start = time.time()
            while True:
                if cancel_cb and cancel_cb():
                    return
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = max(1e-3, time.time() - t_start)
                speed = (downloaded - existing) / elapsed
                if progress_cb:
                    progress_cb(downloaded, total, speed)
```

- [ ] **Step 3: Worker**

Create `app/lab/workers/download_worker.py`:

```python
from __future__ import annotations
import os
from PySide6.QtCore import QThread, Signal
from app.lab.services.downloader import build_hf_url, download


class DownloadWorker(QThread):
    progress = Signal(int, int, float)   # downloaded, total, speed
    finished_ok = Signal(str)            # final path
    failed = Signal(str)

    def __init__(self, entry_id: str, repo_id: str, filename: str,
                 dest_dir: str, hf_token: str | None = None, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id
        self.repo_id = repo_id
        self.filename = filename
        self.dest_dir = dest_dir
        self.hf_token = hf_token
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        if not os.path.isdir(self.dest_dir):
            try:
                os.makedirs(self.dest_dir, exist_ok=True)
            except OSError as e:
                self.failed.emit(f"Cannot create {self.dest_dir}: {e}")
                return
        dest = os.path.join(self.dest_dir, self.filename)
        url = build_hf_url(self.repo_id, self.filename)
        try:
            download(
                url, dest, hf_token=self.hf_token,
                progress_cb=lambda d, t, s: self.progress.emit(d, t, s),
                cancel_cb=lambda: self._cancel,
            )
        except Exception as e:
            self.failed.emit(str(e))
            return
        if self._cancel:
            self.failed.emit("Cancelled.")
            return
        self.finished_ok.emit(dest)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/lab/test_downloader.py -v`
Expected: 3 passed.

- [ ] **Step 5: Wire install into Discover + Library refresh**

Modify `app/lab/shell.py`. Add imports:

```python
from app.lab.workers.download_worker import DownloadWorker
from PySide6.QtWidgets import QMessageBox
```

Add a download manager method inside `LabShell`:

```python
    def _on_install_requested(self, entry_id: str):
        entry = next((e for e in self.store.catalog if e.id == entry_id), None)
        if entry is None:
            return
        models_dir = getattr(self._config, "models_dir", "") if self._config else ""
        if not models_dir:
            QMessageBox.warning(
                self, "Models folder not configured",
                "Pick a models folder in the Library tab before installing.")
            self._switch("library")
            self.nav.set_active("library")
            return
        if self.store.is_busy(f"download:{entry_id}"):
            return
        self.store.set_busy(f"download:{entry_id}", True)
        worker = DownloadWorker(entry_id, entry.repo_id, entry.filename,
                                models_dir, parent=self)
        worker.finished_ok.connect(
            lambda _p, e=entry_id: self._on_download_done(e, ok=True))
        worker.failed.connect(
            lambda msg, e=entry_id: self._on_download_done(e, ok=False, msg=msg))
        worker.start()
        self._downloads = getattr(self, "_downloads", {})
        self._downloads[entry_id] = worker

    def _on_download_done(self, entry_id: str, ok: bool, msg: str = ""):
        self.store.set_busy(f"download:{entry_id}", False)
        if ok and hasattr(self, "library_view"):
            self.library_view.rescan()
        elif not ok:
            QMessageBox.critical(self, "Download failed", msg or "Unknown error")
```

Connect Discover's signal at the end of `__init__`:

```python
        self.discover_view.install_requested.connect(self._on_install_requested)
```

- [ ] **Step 6: Smoke run**

Run: `python main.py` → Lab → Discover → click "Install" on a small model (e.g. TinyLlama).
Expected: download begins in background; on success, Library tab shows the file after rescan.

- [ ] **Step 7: Commit**

```bash
git add app/lab/services/downloader.py app/lab/workers/download_worker.py tests/lab/test_downloader.py app/lab/shell.py
git commit -m "lab: HF downloader + install flow from Discover to Library"
```

---

## Task 18: Benchmark output parser + service

**Files:**
- Create: `app/lab/services/benchmark.py`
- Create: `tests/lab/test_benchmark_parser.py`

`llama-cli` prints timings like:

```
llama_print_timings: prompt eval time = 123.45 ms / 10 tokens ( 12.34 ms per token, 81.00 tokens per second)
llama_print_timings:        eval time =  1000.00 ms / 50 tokens (  20.00 ms per token, 50.00 tokens per second)
llama_print_timings:       total time =  1234.56 ms / 60 tokens
```

- [ ] **Step 1: Write failing tests**

Create `tests/lab/test_benchmark_parser.py`:

```python
from app.lab.services.benchmark import parse_llama_timings


SAMPLE = """
...
llama_print_timings: prompt eval time = 240.00 ms /   12 tokens ( 20.00 ms per token,  50.00 tokens per second)
llama_print_timings:        eval time = 2000.00 ms /  100 tokens ( 20.00 ms per token,  50.00 tokens per second)
llama_print_timings:       total time = 2500.00 ms /  112 tokens
"""


def test_parse_valid_timings():
    r = parse_llama_timings(SAMPLE)
    assert r is not None
    assert abs(r.tokens_per_sec - 50.00) < 0.01
    assert abs(r.prompt_eval_tok_per_sec - 50.00) < 0.01
    assert abs(r.ttft_ms - 240.00) < 0.01


def test_parse_missing_returns_none():
    assert parse_llama_timings("nothing interesting") is None
```

- [ ] **Step 2: Implement**

Create `app/lab/services/benchmark.py`:

```python
"""Run a short generation with llama-cli and parse its timing output."""
from __future__ import annotations
import os
import re
import subprocess
import sys
import time
from app.lab.state.models import BenchmarkResult, RuntimeStatus


_EVAL_RE = re.compile(
    r"eval time\s*=\s*[\d.]+ ms /\s*\d+ tokens \([^,]+,\s*([\d.]+) tokens per second\)"
)
_PROMPT_RE = re.compile(
    r"prompt eval time\s*=\s*([\d.]+) ms /\s*\d+ tokens \([^,]+,\s*([\d.]+) tokens per second\)"
)


def parse_llama_timings(text: str) -> BenchmarkResult | None:
    prompt_m = _PROMPT_RE.search(text or "")
    eval_lines = list(_EVAL_RE.finditer(text or ""))
    if not prompt_m or not eval_lines:
        return None
    gen = float(eval_lines[-1].group(1))   # last "eval time" = generation
    ttft = float(prompt_m.group(1))
    prompt_tps = float(prompt_m.group(2))
    return BenchmarkResult(
        model_name="", timestamp=time.time(),
        tokens_per_sec=gen, ttft_ms=ttft,
        prompt_eval_tok_per_sec=prompt_tps,
    )


def run_benchmark(runtime: RuntimeStatus, model_path: str,
                  prompt: str = "Hello, write a haiku about oceans.",
                  n_predict: int = 64, ctx: int = 2048,
                  timeout_s: float = 120.0) -> BenchmarkResult:
    """Spawn llama-cli, return parsed timings.
    Raises RuntimeError on subprocess/parse failure."""
    if not runtime.installed or not runtime.binary_path:
        raise RuntimeError("Runtime not available")
    # Prefer llama-cli for one-shot; fall back to configured binary.
    bin_dir = os.path.dirname(runtime.binary_path)
    cli_name = "llama-cli" + (".exe" if sys.platform == "win32" else "")
    cli_candidate = os.path.join(bin_dir, cli_name)
    bin_path = cli_candidate if os.path.isfile(cli_candidate) else runtime.binary_path

    cmd = [
        bin_path, "-m", model_path, "-p", prompt,
        "-n", str(n_predict), "-c", str(ctx),
        "--no-warmup", "-ngl", "99",
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
            creationflags=creationflags,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise RuntimeError(f"llama-cli failed: {e}") from e
    combined = (res.stdout or "") + "\n" + (res.stderr or "")
    result = parse_llama_timings(combined)
    if result is None:
        tail = "\n".join(combined.splitlines()[-12:])
        raise RuntimeError(f"Could not parse timings. Tail:\n{tail}")
    result.model_name = os.path.basename(model_path)
    return result
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/lab/test_benchmark_parser.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add app/lab/services/benchmark.py tests/lab/test_benchmark_parser.py
git commit -m "lab: benchmark parser + runner with tests"
```

---

## Task 19: Benchmark worker + Benchmark view

**Files:**
- Create: `app/lab/workers/bench_worker.py`
- Create: `app/lab/views/benchmark_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Worker**

Create `app/lab/workers/bench_worker.py`:

```python
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from app.lab.services.benchmark import run_benchmark
from app.lab.state.models import RuntimeStatus


class BenchmarkWorker(QThread):
    done = Signal(object)   # BenchmarkResult
    failed = Signal(str)

    def __init__(self, runtime: RuntimeStatus, model_path: str, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.model_path = model_path

    def run(self):
        try:
            r = run_benchmark(self.runtime, self.model_path)
            self.done.emit(r)
        except Exception as e:
            self.failed.emit(str(e))
```

- [ ] **Step 2: Benchmark view**

Create `app/lab/views/benchmark_view.py`:

```python
"""Benchmark view — pick a model, run a short generation, record tokens/s."""
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QScrollArea,
)
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, MetricTile, StatusPill,
)
from app.lab.state.models import BenchmarkResult
from app.lab.state.store import LabStore
from app.lab.workers.bench_worker import BenchmarkWorker


class BenchmarkView(QWidget):
    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._worker: BenchmarkWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)
        root.addWidget(SectionHeader("PERFORMANCE", "Benchmark"))

        controls = GlassCard()
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(t.SPACE_3)
        self.model_pick = QComboBox()
        self.model_pick.setMinimumWidth(300)
        self.run_btn = QPushButton("Run benchmark")
        self.run_btn.clicked.connect(self._run)
        self.pill = StatusPill("Idle", "info")
        ctrl_row.addWidget(QLabel("Model:"))
        ctrl_row.addWidget(self.model_pick, 1)
        ctrl_row.addWidget(self.run_btn)
        ctrl_row.addWidget(self.pill)
        controls.body().addLayout(ctrl_row)
        root.addWidget(controls)

        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(t.SPACE_4)
        self.tps_tile = MetricTile("Tokens / sec", "—", "generation")
        self.ttft_tile = MetricTile("TTFT", "—", "ms to first token")
        self.prompt_tile = MetricTile("Prompt eval", "—", "tokens / sec")
        tiles_row.addWidget(self.tps_tile)
        tiles_row.addWidget(self.ttft_tile)
        tiles_row.addWidget(self.prompt_tile)
        root.addLayout(tiles_row)

        self.history_card = GlassCard()
        self.history_card.body().addWidget(SectionHeader("HISTORY", "Past runs"))
        self.history_lay = QVBoxLayout()
        self.history_lay.setSpacing(4)
        self.history_card.body().addLayout(self.history_lay)
        root.addWidget(self.history_card)
        root.addStretch()

        self.store.library_changed.connect(self._refresh_models)
        self.store.benchmarks_changed.connect(self._render_history)
        self._refresh_models(self.store.library)

    def select_model(self, path: str):
        idx = self.model_pick.findData(path)
        if idx >= 0:
            self.model_pick.setCurrentIndex(idx)

    def _refresh_models(self, items):
        self.model_pick.clear()
        for m in items:
            if m.valid:
                self.model_pick.addItem(m.name, m.path)
        self.run_btn.setEnabled(self.model_pick.count() > 0)

    def _run(self):
        path = self.model_pick.currentData()
        if not path:
            return
        if self._worker and self._worker.isRunning():
            return
        if not self.store.runtime.installed:
            self.pill.set_status("Runtime missing", "err")
            return
        self.pill.set_status("Running…", "warn")
        self.run_btn.setEnabled(False)
        self._worker = BenchmarkWorker(self.store.runtime, path, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, r: BenchmarkResult):
        self.tps_tile.set_value(f"{r.tokens_per_sec:.1f}", "generation")
        self.ttft_tile.set_value(f"{r.ttft_ms:.0f} ms", "prompt eval time")
        self.prompt_tile.set_value(f"{r.prompt_eval_tok_per_sec:.1f}", "tokens / sec")
        self.pill.set_status("Done", "ok")
        self.run_btn.setEnabled(True)
        self.store.add_benchmark(r)

    def _on_failed(self, msg: str):
        self.pill.set_status("Failed", "err")
        self.run_btn.setEnabled(True)
        err = QLabel(f"! {msg}")
        err.setStyleSheet(f"color: {t.ERR};")
        err.setWordWrap(True)
        self.history_lay.insertWidget(0, err)

    def _render_history(self, items):
        while self.history_lay.count():
            w = self.history_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for r in reversed(items[-10:]):
            ts = datetime.fromtimestamp(r.timestamp).strftime("%H:%M:%S")
            row = QLabel(
                f"[{ts}]  {r.model_name}  —  {r.tokens_per_sec:.1f} tok/s  "
                f"·  TTFT {r.ttft_ms:.0f} ms"
            )
            row.setProperty("role", "mono")
            self.history_lay.addWidget(row)
```

- [ ] **Step 3: Wire into shell**

Modify `app/lab/shell.py`. Add import:

```python
from app.lab.views.benchmark_view import BenchmarkView
```

After Discover view wiring:

```python
        self.benchmark_view = BenchmarkView(self.store, self)
        self.replace_view("benchmark", self.benchmark_view)
```

Also: in `LibraryView`, the `benchmark_requested` signal is already emitted. Connect it in shell:

```python
        def _bench_from_library(path: str):
            self.benchmark_view.select_model(path)
            self.nav.set_active("benchmark")
            self._switch("benchmark")
        self.library_view.benchmark_requested.connect(_bench_from_library)
```

- [ ] **Step 4: Smoke run**

Run: `python main.py` → Lab → Benchmark → pick model → Run.
Expected: pill goes Running → Done; 3 tiles fill in with numbers; history row appears.

- [ ] **Step 5: Commit**

```bash
git add app/lab/workers/bench_worker.py app/lab/views/benchmark_view.py app/lab/shell.py
git commit -m "lab: Benchmark view + worker + library cross-link"
```

---

## Task 20: Diagnostics service + view

**Files:**
- Create: `app/lab/services/diagnostics.py`
- Create: `app/lab/views/diagnostics_view.py`
- Create: `tests/lab/test_diagnostics.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Write failing tests**

Create `tests/lab/test_diagnostics.py`:

```python
from app.lab.services.diagnostics import collect_diagnostics
from app.lab.state.models import (
    HardwareSpec, RuntimeStatus, ModelFile, GPUInfo,
)


def test_diag_flags_missing_runtime():
    items = collect_diagnostics(
        HardwareSpec(ram_total_gb=32), RuntimeStatus(installed=False), [],
    )
    ids = [i.id for i in items]
    assert "runtime_missing" in ids


def test_diag_flags_no_gpu_when_large_ram_fine():
    items = collect_diagnostics(
        HardwareSpec(ram_total_gb=64), RuntimeStatus(installed=True, validated=True), [],
    )
    ids = [i.id for i in items]
    assert "no_gpu" in ids
    # but with 64GB RAM it's only "info", not "err"
    no_gpu = next(i for i in items if i.id == "no_gpu")
    assert no_gpu.level in ("info", "warn")


def test_diag_flags_invalid_models():
    lib = [
        ModelFile(path="/a", name="a", size_bytes=100, valid=True),
        ModelFile(path="/b", name="b", size_bytes=100, valid=False, error="bad"),
    ]
    items = collect_diagnostics(
        HardwareSpec(ram_total_gb=32), RuntimeStatus(installed=True, validated=True), lib,
    )
    assert any(i.id == "invalid_models" for i in items)


def test_diag_empty_when_all_ok():
    hw = HardwareSpec(
        ram_total_gb=64,
        gpus=[GPUInfo("RTX 4090", 24, "555", True)],
        best_backend="cuda",
    )
    rt = RuntimeStatus(installed=True, validated=True, backend="cuda")
    items = collect_diagnostics(hw, rt, [])
    errs = [i for i in items if i.level == "err"]
    assert errs == []
```

- [ ] **Step 2: Implement**

Create `app/lab/services/diagnostics.py`:

```python
"""Aggregates known health problems across hardware/runtime/library into a
single list of DiagnosticsItem. UX-ready messages."""
from __future__ import annotations
from app.lab.state.models import (
    DiagnosticsItem, HardwareSpec, ModelFile, RuntimeStatus,
)


def collect_diagnostics(hw: HardwareSpec, runtime: RuntimeStatus,
                        library: list[ModelFile]) -> list[DiagnosticsItem]:
    out: list[DiagnosticsItem] = []

    if not runtime.installed:
        out.append(DiagnosticsItem(
            id="runtime_missing", level="err",
            title="llama.cpp runtime not found",
            detail="Download and install a prebuilt binary, or point the Runtime "
                   "view at an existing install.",
            fix_action="open_runtime",
        ))
    elif not runtime.validated:
        out.append(DiagnosticsItem(
            id="runtime_unverified", level="warn",
            title="Runtime binary found but version unknown",
            detail="The binary didn't report a version — it may be outdated or "
                   "incompatible.",
            fix_action="open_runtime",
        ))

    if not hw.gpus:
        level = "info" if hw.ram_total_gb >= 32 else "warn"
        out.append(DiagnosticsItem(
            id="no_gpu", level=level,
            title="No CUDA GPU detected",
            detail="Inference will run on CPU. Fine for small models; "
                   "bigger models will be slow.",
        ))
    elif runtime.installed and runtime.backend == "cpu" and hw.gpus:
        out.append(DiagnosticsItem(
            id="runtime_cpu_only", level="warn",
            title="Runtime compiled without GPU support",
            detail="You have a CUDA GPU, but the llama.cpp binary only supports CPU. "
                   "Install a CUDA-enabled build to unlock offload.",
            fix_action="open_runtime",
        ))

    if hw.disk_free_gb and hw.disk_free_gb < 20:
        out.append(DiagnosticsItem(
            id="low_disk", level="warn",
            title="Low free disk space",
            detail=f"Only {hw.disk_free_gb:.0f} GB free. Most GGUF files are 4–30 GB.",
        ))

    if hw.ram_total_gb and hw.ram_total_gb < 16:
        out.append(DiagnosticsItem(
            id="low_ram", level="warn",
            title="Low system RAM",
            detail="Under 16 GB — large contexts and bigger models will struggle.",
        ))

    bad = [m for m in library if not m.valid]
    if bad:
        sample = ", ".join(m.name for m in bad[:3])
        out.append(DiagnosticsItem(
            id="invalid_models", level="warn",
            title=f"{len(bad)} model file(s) unreadable",
            detail=f"Failed to parse: {sample}. "
                   f"Files may be incomplete or corrupted.",
            fix_action="rescan_library",
        ))

    return out
```

- [ ] **Step 3: Diagnostics view**

Create `app/lab/views/diagnostics_view.py`:

```python
"""Diagnostics view — lists all current issues with severity, detail, and fix."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, HealthDot,
)
from app.lab.services.diagnostics import collect_diagnostics
from app.lab.state.store import LabStore


class DiagnosticsView(QWidget):
    navigate_requested = Signal(str)     # nav key, e.g. "runtime"
    rescan_library_requested = Signal()

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)
        root.addWidget(SectionHeader("HEALTH", "Diagnostics"))

        self.body_lay = QVBoxLayout()
        self.body_lay.setSpacing(t.SPACE_3)
        root.addLayout(self.body_lay)
        root.addStretch()

        for sig in (self.store.hardware_changed, self.store.runtime_changed,
                    self.store.library_changed):
            sig.connect(lambda *_: self._refresh())
        self._refresh()

    def _refresh(self):
        items = collect_diagnostics(
            self.store.hardware, self.store.runtime, self.store.library,
        )
        self.store.set_diagnostics(items)

        while self.body_lay.count():
            w = self.body_lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        if not items:
            card = GlassCard()
            lbl = QLabel("All clear. Nothing to fix right now.")
            lbl.setProperty("role", "title")
            card.body().addWidget(lbl)
            self.body_lay.addWidget(card)
            return

        for it in items:
            card = GlassCard()
            head = QHBoxLayout()
            head.setSpacing(t.SPACE_3)
            head.addWidget(HealthDot(it.level))
            title = QLabel(it.title)
            title.setProperty("role", "title")
            head.addWidget(title)
            head.addStretch()
            card.body().addLayout(head)
            det = QLabel(it.detail)
            det.setWordWrap(True)
            det.setProperty("role", "muted")
            card.body().addWidget(det)
            if it.fix_action:
                actions = QHBoxLayout()
                actions.addStretch()
                btn = QPushButton(self._label_for(it.fix_action))
                btn.clicked.connect(lambda _=False, a=it.fix_action: self._run_fix(a))
                actions.addWidget(btn)
                card.body().addLayout(actions)
            self.body_lay.addWidget(card)

    def _label_for(self, action: str) -> str:
        return {
            "open_runtime": "Open Runtime",
            "rescan_library": "Rescan Library",
        }.get(action, "Fix")

    def _run_fix(self, action: str):
        if action == "open_runtime":
            self.navigate_requested.emit("runtime")
        elif action == "rescan_library":
            self.rescan_library_requested.emit()
```

- [ ] **Step 4: Wire into shell**

Modify `app/lab/shell.py`. Import:

```python
from app.lab.views.diagnostics_view import DiagnosticsView
```

After Benchmark view wiring:

```python
        self.diag_view = DiagnosticsView(self.store, self)
        self.replace_view("diagnostics", self.diag_view)
        self.diag_view.navigate_requested.connect(
            lambda k: (self.nav.set_active(k), self._switch(k)))
        self.diag_view.rescan_library_requested.connect(
            lambda: self.library_view.rescan())
```

- [ ] **Step 5: Run tests + smoke**

Run: `pytest tests/lab/test_diagnostics.py -v`
Expected: 4 passed.

Then: `python main.py` → Lab → Diagnostics.
Expected: cards for each current issue; clicking "Open Runtime" jumps to that tab; "Rescan Library" reruns the scan.

- [ ] **Step 6: Commit**

```bash
git add app/lab/services/diagnostics.py app/lab/views/diagnostics_view.py tests/lab/test_diagnostics.py app/lab/shell.py
git commit -m "lab: Diagnostics service + view with autofix navigation"
```

---

## Task 21: Overview / Home view

**Files:**
- Create: `app/lab/views/overview_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Write the view**

Create `app/lab/views/overview_view.py`:

```python
"""Overview — first view users see. Hero + quick status + top recommendation."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, MetricTile, StatusPill, HealthDot,
)
from app.lab.services.capacity import estimate_capacity
from app.lab.state.store import LabStore


class OverviewView(QWidget):
    navigate_requested = Signal(str)
    install_requested = Signal(str)   # entry id

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        # Hero
        hero = GlassCard(raised=True)
        htitle = QLabel("Local AI Lab")
        htitle.setProperty("role", "display")
        hsub = QLabel("Your workstation, your models. Offline inference with llama.cpp.")
        hsub.setProperty("role", "muted")
        hsub.setWordWrap(True)
        hero.body().addWidget(htitle)
        hero.body().addWidget(hsub)

        cta_row = QHBoxLayout()
        self.cta_primary = QPushButton("Discover models")
        self.cta_primary.clicked.connect(lambda: self.navigate_requested.emit("discover"))
        self.cta_secondary = QPushButton("Check runtime")
        self.cta_secondary.setProperty("variant", "ghost")
        self.cta_secondary.clicked.connect(lambda: self.navigate_requested.emit("runtime"))
        cta_row.addWidget(self.cta_primary)
        cta_row.addWidget(self.cta_secondary)
        cta_row.addStretch()
        hero.body().addLayout(cta_row)
        root.addWidget(hero)

        # Status strip
        strip = QHBoxLayout()
        strip.setSpacing(t.SPACE_4)
        self.hw_tile = MetricTile("Machine", "Detecting…", "")
        self.rt_tile = MetricTile("Runtime", "Detecting…", "")
        self.lib_tile = MetricTile("Library", "—", "")
        self.health_tile = MetricTile("Health", "—", "")
        strip.addWidget(self.hw_tile)
        strip.addWidget(self.rt_tile)
        strip.addWidget(self.lib_tile)
        strip.addWidget(self.health_tile)
        root.addLayout(strip)

        # Top recommendation card
        self.rec_card = GlassCard()
        self.rec_title = QLabel("Loading recommendation…")
        self.rec_title.setProperty("role", "title")
        self.rec_body = QLabel("")
        self.rec_body.setWordWrap(True)
        self.rec_body.setProperty("role", "muted")
        self.rec_install = QPushButton("Install")
        self.rec_install.setVisible(False)
        self._rec_id: str | None = None
        self.rec_install.clicked.connect(
            lambda: self._rec_id and self.install_requested.emit(self._rec_id))
        rr = QHBoxLayout()
        rr.addWidget(SectionHeader("BEST FIT", "Top pick"))
        rr.addStretch()
        self.rec_card.body().addLayout(rr)
        self.rec_card.body().addWidget(self.rec_title)
        self.rec_card.body().addWidget(self.rec_body)
        rb = QHBoxLayout()
        rb.addStretch()
        rb.addWidget(self.rec_install)
        self.rec_card.body().addLayout(rb)
        root.addWidget(self.rec_card)

        root.addStretch()

        for sig in (self.store.hardware_changed, self.store.runtime_changed,
                    self.store.library_changed, self.store.recommendations_changed,
                    self.store.diagnostics_changed):
            sig.connect(lambda *_: self._render())
        self._render()

    def _render(self):
        hw = self.store.hardware
        rt = self.store.runtime
        cap = estimate_capacity(hw) if hw.cpu_name else None
        if cap:
            self.hw_tile.set_value(cap.tier.upper(), cap.headline)
        else:
            self.hw_tile.set_value("—", "")
        if rt.installed and rt.validated:
            self.rt_tile.set_value("READY", f"{rt.version}  ·  {rt.backend}")
        elif rt.installed:
            self.rt_tile.set_value("PARTIAL", "version unknown")
        else:
            self.rt_tile.set_value("MISSING", "install required")
        valid = [m for m in self.store.library if m.valid]
        self.lib_tile.set_value(str(len(valid)), f"of {len(self.store.library)} files")
        issues = self.store.diagnostics
        err_n = sum(1 for i in issues if i.level == "err")
        warn_n = sum(1 for i in issues if i.level == "warn")
        if err_n:
            self.health_tile.set_value("ATTENTION", f"{err_n} critical, {warn_n} warnings")
        elif warn_n:
            self.health_tile.set_value("OK", f"{warn_n} warnings")
        else:
            self.health_tile.set_value("HEALTHY", "everything looks good")

        recs = self.store.recommendations
        top = next((r for r in recs if r.fit in ("excellent", "good")), None)
        if top:
            self._rec_id = top.entry.id
            self.rec_title.setText(top.entry.display_name)
            self.rec_body.setText(
                f"{top.entry.notes}  "
                f"Needs ~{top.entry.approx_vram_gb:.0f} GB VRAM — "
                f"{top.fit} fit on your machine."
            )
            self.rec_install.setVisible(True)
        else:
            self._rec_id = None
            self.rec_title.setText("No recommendation yet")
            self.rec_body.setText("Finish hardware detection to see a top pick.")
            self.rec_install.setVisible(False)
```

- [ ] **Step 2: Wire into shell**

Modify `app/lab/shell.py`. Import:

```python
from app.lab.views.overview_view import OverviewView
```

At the end of `__init__`:

```python
        self.overview_view = OverviewView(self.store, self)
        self.replace_view("overview", self.overview_view)
        self.overview_view.navigate_requested.connect(
            lambda k: (self.nav.set_active(k), self._switch(k)))
        self.overview_view.install_requested.connect(self._on_install_requested)
```

- [ ] **Step 3: Smoke run**

Run: `python main.py` → Lab → Overview (default).
Expected: hero renders, 4 status tiles fill in within ~2s, top-pick card recommends an appropriate model.

- [ ] **Step 4: Commit**

```bash
git add app/lab/views/overview_view.py app/lab/shell.py
git commit -m "lab: Overview hero + status strip + top recommendation"
```

---

## Task 22: Model detail view

**Files:**
- Create: `app/lab/views/model_detail_view.py`
- Modify: `app/lab/views/library_view.py`
- Modify: `app/lab/shell.py`

The model detail view is surfaced via a modal-style replacement of the Library view or a push inside the Library stack. For simplicity we implement it as a separate view reachable from Library's "Details" button; a "Back" button returns to Library.

- [ ] **Step 1: Write the view**

Create `app/lab/views/model_detail_view.py`:

```python
"""Model detail — full panel for a single GGUF file."""
from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)
from PySide6.QtCore import Signal
from app.lab import theme as t
from app.lab.components.primitives import (
    GlassCard, SectionHeader, KeyValueRow, StatusPill,
)
from app.lab.state.models import ModelFile
from app.lab.state.store import LabStore


class ModelDetailView(QWidget):
    back_requested = Signal()
    benchmark_requested = Signal(str)
    removed = Signal(str)    # path

    def __init__(self, store: LabStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._model: ModelFile | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_5)

        head = QHBoxLayout()
        self.back_btn = QPushButton("← Library")
        self.back_btn.setProperty("variant", "ghost")
        self.back_btn.clicked.connect(self.back_requested.emit)
        head.addWidget(self.back_btn)
        head.addStretch()
        root.addLayout(head)

        self.title_row = QHBoxLayout()
        self.title = QLabel("—")
        self.title.setProperty("role", "display")
        self.pill = StatusPill("GGUF", "info")
        self.title_row.addWidget(self.title)
        self.title_row.addStretch()
        self.title_row.addWidget(self.pill)
        root.addLayout(self.title_row)

        self.card = GlassCard()
        self.card.body().addWidget(SectionHeader("TECHNICAL", "Metadata"))
        self.row_arch = KeyValueRow("Architecture", "—")
        self.row_params = KeyValueRow("Parameters", "—")
        self.row_ctx = KeyValueRow("Context length", "—")
        self.row_quant = KeyValueRow("Quantization", "—")
        self.row_size = KeyValueRow("File size", "—")
        self.row_path = KeyValueRow("Path", "—")
        for r in [self.row_arch, self.row_params, self.row_ctx,
                  self.row_quant, self.row_size, self.row_path]:
            self.card.body().addWidget(r)
        root.addWidget(self.card)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_3)
        self.bench_btn = QPushButton("Run benchmark")
        self.bench_btn.clicked.connect(
            lambda: self._model and self.benchmark_requested.emit(self._model.path))
        self.remove_btn = QPushButton("Remove file")
        self.remove_btn.setProperty("variant", "danger")
        self.remove_btn.clicked.connect(self._remove)
        actions.addWidget(self.bench_btn)
        actions.addStretch()
        actions.addWidget(self.remove_btn)
        root.addLayout(actions)
        root.addStretch()

    def show_model_by_path(self, path: str):
        m = next((x for x in self.store.library if x.path == path), None)
        if m is None:
            return
        self._model = m
        self.title.setText(m.name)
        self.pill.set_status(m.quant or "GGUF", "info" if m.valid else "err")
        self.row_arch.set_value(m.architecture or "—")
        self.row_params.set_value(f"{m.param_count_b:.2f} B" if m.param_count_b else "—")
        self.row_ctx.set_value(f"{m.context_length:,}" if m.context_length else "—")
        self.row_quant.set_value(m.quant or "—")
        self.row_size.set_value(f"{m.size_bytes / (1024 ** 3):.2f} GB")
        self.row_path.set_value(m.path)

    def _remove(self):
        if self._model is None:
            return
        reply = QMessageBox.question(
            self, "Remove model",
            f"Delete {self._model.name} from disk?\n\n{self._model.path}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            os.remove(self._model.path)
        except OSError as e:
            QMessageBox.critical(self, "Remove failed", str(e))
            return
        self.removed.emit(self._model.path)
        self.back_requested.emit()
```

- [ ] **Step 2: Add detail slot in Library nav**

In `app/lab/shell.py`, treat "library" as a container that swaps between grid and detail. Simpler: add model detail as a NEW stacked-widget entry (not in NavRail) and switch to it programmatically.

Modify `app/lab/shell.py`. Imports:

```python
from app.lab.views.model_detail_view import ModelDetailView
```

In `__init__` after Diagnostics wiring:

```python
        self.detail_view = ModelDetailView(self.store, self)
        self.stack.addWidget(self.detail_view)   # not in nav rail
        self.detail_view.back_requested.connect(lambda: self._switch("library"))
        self.detail_view.removed.connect(lambda _p: self.library_view.rescan())
        self.detail_view.benchmark_requested.connect(
            lambda p: (self.benchmark_view.select_model(p),
                       self.nav.set_active("benchmark"),
                       self._switch_detail_to_bench()))

        self.library_view.model_detail_requested.connect(self._open_detail)
```

Add helper methods:

```python
    def _open_detail(self, path: str):
        self.detail_view.show_model_by_path(path)
        self.stack.setCurrentWidget(self.detail_view)

    def _switch_detail_to_bench(self):
        self._switch("benchmark")
```

- [ ] **Step 3: Smoke run**

Run: `python main.py` → Lab → Library → "Details" on any card.
Expected: detail view opens with full metadata, Back returns, Benchmark jumps to Benchmark with the model preselected, Remove deletes and rescans.

- [ ] **Step 4: Commit**

```bash
git add app/lab/views/model_detail_view.py app/lab/shell.py
git commit -m "lab: Model detail view + remove flow"
```

---

## Task 23: Visual polish — download progress + skeletons + empty states

**Files:**
- Create: `app/lab/components/progress_bar.py`
- Modify: `app/lab/views/discover_view.py`
- Modify: `app/lab/components/recommendation_card.py`
- Modify: `app/lab/views/library_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Progress bar component**

Create `app/lab/components/progress_bar.py`:

```python
"""Lab-styled progress bar — thin, animated, on-brand."""
from __future__ import annotations
from PySide6.QtWidgets import QProgressBar
from app.lab import theme as t


class LabProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(6)
        self.setStyleSheet(
            f"QProgressBar {{ background: {t.SURFACE_3}; border: none;"
            f" border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {t.ACCENT};"
            f" border-radius: 3px; }}"
        )
```

- [ ] **Step 2: Wire download progress into recommendation cards**

Modify `app/lab/components/recommendation_card.py`. At the top add:

```python
from app.lab.components.progress_bar import LabProgressBar
from app.lab.services.downloader import humanize_speed
```

In `RecommendationCard.__init__`, before the final `self.body().addLayout(actions)`:

```python
        self.progress = LabProgressBar()
        self.progress.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setProperty("role", "muted")
        self.progress_label.setVisible(False)
        self.body().addWidget(self.progress)
        self.body().addWidget(self.progress_label)
```

Add methods:

```python
    def set_progress(self, downloaded: int, total: int, speed: float):
        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.install_btn.setEnabled(False)
        self.install_btn.setText("Downloading…")
        if total > 0:
            pct = int(100 * downloaded / total)
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            self.progress_label.setText(
                f"{downloaded / (1024**3):.2f} / {total / (1024**3):.2f} GB   "
                f"·   {humanize_speed(speed)}")
        else:
            self.progress.setRange(0, 0)
            self.progress_label.setText(f"{humanize_speed(speed)}")

    def set_install_state(self, state: str):
        if state == "done":
            self.progress.setVisible(False)
            self.progress_label.setVisible(False)
            self.install_btn.setText("Installed")
            self.install_btn.setEnabled(False)
        elif state == "failed":
            self.progress.setVisible(False)
            self.progress_label.setText("Download failed")
            self.install_btn.setText("Retry")
            self.install_btn.setEnabled(True)
```

- [ ] **Step 3: Discover view — hold card refs by entry id**

Modify `app/lab/views/discover_view.py`. In `_rerank`, after `self.list_lay.addWidget(card)`:

```python
            self._cards[r.entry.id] = card
```

And at top of `_rerank`:

```python
        self._cards = {}
```

Expose helper:

```python
    def on_progress(self, entry_id: str, d: int, total: int, speed: float):
        card = self._cards.get(entry_id)
        if card:
            card.set_progress(d, total, speed)

    def on_install_result(self, entry_id: str, ok: bool):
        card = self._cards.get(entry_id)
        if card:
            card.set_install_state("done" if ok else "failed")
```

- [ ] **Step 4: Shell forwards progress**

Modify `app/lab/shell.py` in `_on_install_requested`:

```python
        worker.progress.connect(
            lambda d, total, spd, e=entry_id:
                self.discover_view.on_progress(e, d, total, spd))
```

In `_on_download_done`:

```python
        self.discover_view.on_install_result(entry_id, ok)
```

- [ ] **Step 5: Library empty state polish**

Modify `app/lab/views/library_view.py`. Replace the empty card contents with:

```python
        e_title = QLabel("Your library is empty")
        e_title.setProperty("role", "display")
        e_body = QLabel(
            "Install a recommended model from Discover, import a GGUF you "
            "already have, or point the Library at an existing folder."
        )
        e_body.setWordWrap(True)
        e_body.setProperty("role", "muted")
        e_row = QHBoxLayout()
        e_discover = QPushButton("Go to Discover")
        e_discover.clicked.connect(lambda: self._emit_nav("discover"))
        e_pick = QPushButton("Pick folder")
        e_pick.setProperty("variant", "ghost")
        e_pick.clicked.connect(self._pick_folder)
        e_row.addWidget(e_discover)
        e_row.addWidget(e_pick)
        e_row.addStretch()
        self.empty.body().addWidget(e_title)
        self.empty.body().addWidget(e_body)
        self.empty.body().addLayout(e_row)
```

Add signal + helper:

```python
class LibraryView(QWidget):
    model_detail_requested = Signal(str)
    benchmark_requested = Signal(str)
    navigate_requested = Signal(str)
    ...
    def _emit_nav(self, key: str):
        self.navigate_requested.emit(key)
```

Wire in shell:

```python
        self.library_view.navigate_requested.connect(
            lambda k: (self.nav.set_active(k), self._switch(k)))
```

- [ ] **Step 6: Smoke**

Run: `python main.py` → install a small model from Discover.
Expected: the card shows a moving progress bar and speed; on completion, button flips to "Installed".

- [ ] **Step 7: Commit**

```bash
git add app/lab/components/progress_bar.py app/lab/components/recommendation_card.py app/lab/views/discover_view.py app/lab/views/library_view.py app/lab/shell.py
git commit -m "lab: download progress UI + library empty state polish"
```

---

## Task 24: Persist models_dir + final wiring

**Files:**
- Modify: `app/lab/views/library_view.py`
- Modify: `app/lab/shell.py`

- [ ] **Step 1: Persist models_dir through ConfigStore**

Modify `app/lab/shell.py` constructor to accept a config_store + callback:

```python
class LabShell(QWidget):
    def __init__(self, config=None, config_store=None, parent=None):
        ...
        self._config_store = config_store
```

Add:

```python
    def _persist_models_dir(self, path: str):
        if self._config_store is not None and self._config is not None:
            self._config.models_dir = path
            self._config_store.save(self._config)
```

Modify `app/lab/views/library_view.py` — emit a signal when directory changes:

```python
class LibraryView(QWidget):
    model_detail_requested = Signal(str)
    benchmark_requested = Signal(str)
    navigate_requested = Signal(str)
    models_dir_changed = Signal(str)
    ...
    def set_models_dir(self, path: str):
        self.models_dir = path
        self.dir_lbl.setText(path or "No directory configured")
        self.models_dir_changed.emit(path)
        self.rescan()
```

In shell:

```python
        self.library_view.models_dir_changed.connect(self._persist_models_dir)
```

Modify `app/ui/main_window.py`:

```python
        self.lab_shell = LabShell(self.config, self.config_store)
```

- [ ] **Step 2: Smoke — restart app, dir is remembered**

Run: `python main.py` → Lab → Library → pick a folder → close app → reopen.
Expected: selected folder reappears, library repopulates.

- [ ] **Step 3: Full test run**

Run: `pytest -v`
Expected: all Lab + Cloud tests green.

- [ ] **Step 4: Commit**

```bash
git add app/lab/shell.py app/lab/views/library_view.py app/ui/main_window.py
git commit -m "lab: persist models_dir via ConfigStore"
```

---

## Final hand-off checklist

- [ ] Full test suite passes: `pytest -v`
- [ ] `python main.py` launches; Cloud view unchanged; Lab toggle works.
- [ ] Lab → Overview renders hero + 4 status tiles + top pick.
- [ ] Lab → Machine shows real CPU/RAM/GPU/VRAM/Disk + capacity card.
- [ ] Lab → Runtime detects llama-server on PATH (or shows MISSING + install guide).
- [ ] Lab → Discover ranks catalog, filter dropdown works.
- [ ] Lab → Library scans models_dir, import + remove flows work, persists across restarts.
- [ ] Lab → Benchmark runs a generation and records tokens/s.
- [ ] Lab → Diagnostics enumerates issues with working "Open Runtime" / "Rescan Library" buttons.
- [ ] Installing a model from Discover shows live progress and rescans Library on done.

## What is NOT done (followup work)

- **Model config sliders** (threads / context / gpu-layers / batch) per model — current flow always uses `-ngl 99` + default context. Add a `ModelConfig` dataclass + per-model settings panel.
- **Autotune** (probe different `-ngl` values and pick the best) — build on top of BenchmarkWorker.
- **Duplicate detection** in Library (SHA-256 on GGUF tail) — stub for Task 13+.
- **Authed downloads** for gated HF repos (Llama 3, Gemma) — surface a token field in settings.
- **Remote bridge** — launch Lab benchmarks against a Vast instance through the existing SSH tunnel.
- **Keyboard shortcuts** for nav (1..7) + subtle view-in/out transitions.

