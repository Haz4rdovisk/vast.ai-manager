# Lab-as-Primary-App Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge all Cloud-session functionality into the Lab workspace so that the Lab becomes the single main application, with a consolidated, professional black-dashboard design system.

**Architecture:** Promote the existing `app.lab` package to the app's primary shell. The top-bar Cloud/Lab toggle disappears; `MainWindow` becomes a thin host around a renamed `AppShell` (née `LabShell`). A new `Instances` view (replacing the Cloud body) slots into the existing nav rail as the default landing page. All workers (list, action, tunnel, live-metrics, model-watcher, llama-probe) migrate from `MainWindow` into a single `AppController` the shell owns. The old `app/theme.py` is deleted; `app/lab/theme.py` is renamed to `app/theme.py` and becomes THE design system.

**Tech Stack:** Python 3.10+, PySide6 (Qt6), pytest + pytest-qt for tests.

---

## Scope Note

This is a coherent single-subsystem migration (app shell + design system + view port). Phases are strictly sequential: the design system must land before UI ports, and workers must be centralized before the cloud shell is torn down. **Do not skip ahead.** If a phase exposes unknowns, stop and add tasks rather than improvise.

## File Structure

### New files
- `app/ui/components/__init__.py` — shared component package (promoted from lab/components)
- `app/ui/components/primitives.py` — moved from `app/lab/components/primitives.py`; extended with `ConsoleLog`, `ToastBanner`, `MetricStrip`, `NumberMetric`, `InstanceRow`, `PrimaryButton`, `GhostButton`, `DangerButton`, `IconButton`
- `app/ui/components/nav_rail.py` — moved from `app/lab/components/nav_rail.py`; adds "Instances" item as first nav entry
- `app/controller.py` — new `AppController` that owns workers, tracker, SSH, and emits high-level signals the views consume
- `app/ui/views/instances_view.py` — new landing view: billing strip + instance list + inline console
- `app/ui/views/instance_card.py` — redesigned instance card using the new design system
- `app/ui/views/billing_strip.py` — compact, always-on-top billing widget (balance / burn / autonomy + projection)
- `app/ui/views/console_drawer.py` — collapsible bottom drawer wrapping the console log
- `app/ui/app_shell.py` — moved/renamed from `app/lab/shell.py`; adds top bar, hosts `AppController`, wires the Instances view alongside the existing Lab views
- `tests/test_controller.py`, `tests/test_instances_view.py`, `tests/test_theme_tokens.py`, `tests/test_billing_strip.py`

### Modified files
- `main.py` — single stylesheet, `AppShell` instead of `MainWindow`-wrapping-LabShell
- `app/theme.py` — **replaced** by the contents of `app/lab/theme.py` (with additions noted below)
- `app/ui/settings_dialog.py` — restyled for new design tokens; no behavior change
- `app/ui/toast.py` — restyled, integrated with new design tokens
- `app/billing.py` — no change, reused as-is
- `app/config.py`, `app/models.py`, `app/services/*`, `app/workers/*`, `app/lab/services/*`, `app/lab/workers/*`, `app/lab/state/*`, `app/lab/views/*` — logic unchanged; any import of `app.theme` continues to resolve after the theme-file swap

### Deleted / absorbed files (final phase)
- `app/ui/main_window.py` — absorbed into `app/ui/app_shell.py`
- `app/lab/theme.py` — contents migrated to `app/theme.py`, file deleted
- `app/lab/components/primitives.py` — moved to `app/ui/components/primitives.py`
- `app/lab/components/nav_rail.py` — moved to `app/ui/components/nav_rail.py`
- `app/lab/shell.py` — renamed to `app/ui/app_shell.py`
- `app/ui/model_manager_dialog.py` — already superseded by Lab views; delete
- `app/ui/metric_bar.py` — replaced by the new `MetricStrip` primitive
- Old `app/ui/instance_card.py` — replaced by `app/ui/views/instance_card.py`
- `app/ui/log_panel.py` — replaced by `ConsoleLog` primitive inside `console_drawer.py`
- `app/ui/billing_header.py` — replaced by `app/ui/views/billing_strip.py`

---

## Design System Reference (Phase 0 outcome)

The single theme file at `app/theme.py` will expose (expanding on current lab tokens):

```python
# Palette
BG_DEEP     = "#07090D"   # shell
BG_BASE     = "#0C1016"   # content
SURFACE_1   = "#141922"   # cards
SURFACE_2   = "#1C2330"   # hover / raised
SURFACE_3   = "#262F3F"   # inputs / pressed
BORDER_LOW  = "#1B2230"
BORDER_MED  = "#2A3345"
BORDER_HI   = "#3B4662"

TEXT_HI  = "#F1F4FA"
TEXT     = "#C7CEDC"
TEXT_MID = "#8891A6"
TEXT_LOW = "#5A6277"

ACCENT       = "#7C5CFF"
ACCENT_HI    = "#9B83FF"
ACCENT_GLOW  = "rgba(124, 92, 255, 0.35)"

OK   = "#3BD488"
WARN = "#F4B740"
ERR  = "#F0556A"
INFO = "#4EA8FF"
LIVE = "#19C37D"   # new: tunnel-alive indicator
```

```python
# Geometry
RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL = 6, 10, 14, 20
SPACE_1..SPACE_7 = 4, 8, 12, 16, 24, 32, 48
FONT_DISPLAY = "Inter, 'Segoe UI Variable', 'Segoe UI', sans-serif"
FONT_MONO    = "'JetBrains Mono', Consolas, 'Courier New', monospace"
```

```python
# Helpers (new + preserved)
def metric_color(percent: float | None) -> str  # 0-60 OK, 60-85 WARN, 85+ ERR
def temp_color(temp: float | None) -> str
def autonomy_color(hours: float | None) -> str  # preserves 4-tier scale from old theme
def health_color(level: str) -> str
```

---

# Phase 0 — Unified Design System

Goal: rip out `app/theme.py` and replace it with a superset of `app/lab/theme.py`, without breaking the running app. At the end of Phase 0 the app still runs with its current UI, but every import of `app.theme` now returns the new tokens. Colours on the current Cloud UI will temporarily look wrong (dark/iris) — that is expected; later phases delete those widgets.

---

### Task 0.1: Snapshot stylesheet test

**Files:**
- Create: `tests/test_theme_tokens.py`

- [x] **Step 1: Write a test asserting new token names exist and have expected values**

```python
# tests/test_theme_tokens.py
"""Locks in the unified design-system palette so refactors can't accidentally
drop a token or change a hex. Runs before any theme edit so the failure is real."""
import re
from app import theme


def test_core_palette_present():
    assert theme.BG_DEEP == "#07090D"
    assert theme.BG_BASE == "#0C1016"
    assert theme.SURFACE_1 == "#141922"
    assert theme.SURFACE_2 == "#1C2330"
    assert theme.SURFACE_3 == "#262F3F"
    assert theme.ACCENT == "#7C5CFF"


def test_text_scale_present():
    assert theme.TEXT_HI == "#F1F4FA"
    assert theme.TEXT == "#C7CEDC"
    assert theme.TEXT_MID == "#8891A6"
    assert theme.TEXT_LOW == "#5A6277"


def test_status_colors_present():
    assert theme.OK == "#3BD488"
    assert theme.WARN == "#F4B740"
    assert theme.ERR == "#F0556A"
    assert theme.INFO == "#4EA8FF"
    assert theme.LIVE == "#19C37D"


def test_metric_color_tiers():
    assert theme.metric_color(10) == theme.OK
    assert theme.metric_color(70) == theme.WARN
    assert theme.metric_color(95) == theme.ERR
    assert theme.metric_color(None) == theme.TEXT_MID


def test_autonomy_color_tiers():
    """Preserves the 4-tier scale from the old app/theme.py."""
    assert theme.autonomy_color(0.5) == theme.ERR
    assert theme.autonomy_color(3.0) == "#ff9800"
    assert theme.autonomy_color(12.0) == theme.WARN
    assert theme.autonomy_color(48.0) == theme.OK
    assert theme.autonomy_color(None) == theme.TEXT_MID


def test_stylesheet_has_lab_shell_scope_removed():
    """Phase 0 ends with the lab-shell scope removed from the main stylesheet —
    the design system now applies globally."""
    assert "#lab-shell" not in theme.STYLESHEET
    assert "QMainWindow" in theme.STYLESHEET  # global rules are back
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme_tokens.py -v`
Expected: FAIL — `BG_DEEP`/`TEXT_HI`/etc. don't exist on current `app/theme.py`.

- [x] **Step 3: Commit the failing test**

```bash
git add tests/test_theme_tokens.py
git commit -m "test: lock in unified design-system tokens (failing)"
```

---

### Task 0.2: Rewrite `app/theme.py` as the unified design system

**Files:**
- Modify: `app/theme.py` (complete rewrite)

- [x] **Step 1: Replace the file with the unified theme**

```python
# app/theme.py
"""Unified design system for Vast.ai Manager. One theme for the whole app —
scoped stylesheets and per-workspace QSS are gone."""
from __future__ import annotations

# ---- Surfaces ----------------------------------------------------------------
BG_DEEP    = "#07090D"
BG_BASE    = "#0C1016"
SURFACE_1  = "#141922"
SURFACE_2  = "#1C2330"
SURFACE_3  = "#262F3F"
BORDER_LOW = "#1B2230"
BORDER_MED = "#2A3345"
BORDER_HI  = "#3B4662"

# ---- Typography --------------------------------------------------------------
TEXT_HI  = "#F1F4FA"
TEXT     = "#C7CEDC"
TEXT_MID = "#8891A6"
TEXT_LOW = "#5A6277"

FONT_DISPLAY = "Inter, 'Segoe UI Variable', 'Segoe UI', sans-serif"
FONT_MONO    = "'JetBrains Mono', Consolas, 'Courier New', monospace"

# ---- Accent + status ---------------------------------------------------------
ACCENT      = "#7C5CFF"
ACCENT_HI   = "#9B83FF"
ACCENT_GLOW = "rgba(124, 92, 255, 0.35)"

OK   = "#3BD488"
WARN = "#F4B740"
ERR  = "#F0556A"
INFO = "#4EA8FF"
LIVE = "#19C37D"  # "alive / tunneled" indicator

# ---- Geometry ----------------------------------------------------------------
RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL = 6, 10, 14, 20
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5, SPACE_6, SPACE_7 = 4, 8, 12, 16, 24, 32, 48


# ---- Semantic color helpers --------------------------------------------------
def metric_color(percent: float | None) -> str:
    if percent is None:
        return TEXT_MID
    if percent < 60:
        return OK
    if percent < 85:
        return WARN
    return ERR


def temp_color(temp: float | None) -> str:
    if temp is None:
        return TEXT_MID
    if temp < 70:
        return OK
    if temp < 80:
        return WARN
    return ERR


def autonomy_color(hours: float | None) -> str:
    """4-tier scale preserved from the pre-migration theme:
    <1h = CRITICAL, 1-6h = LOW, 6-24h = MEDIUM, >24h = GOOD."""
    if hours is None:
        return TEXT_MID
    if hours > 24:
        return OK
    if hours > 6:
        return WARN
    if hours > 1:
        return "#ff9800"
    return ERR


def health_color(level: str) -> str:
    return {"ok": OK, "warn": WARN, "err": ERR, "info": INFO, "live": LIVE}.get(level, TEXT_MID)


# ---- Global stylesheet -------------------------------------------------------
STYLESHEET = f"""
QMainWindow, QDialog, QWidget#app-shell {{
    background-color: {BG_DEEP};
    color: {TEXT};
    font-family: {FONT_DISPLAY};
    font-size: 10pt;
}}
QWidget {{ color: {TEXT}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel[role="display"] {{
    color: {TEXT_HI};
    font-size: 22pt;
    font-weight: 700;
    letter-spacing: -0.5px;
}}
QLabel[role="title"] {{
    color: {TEXT_HI};
    font-size: 14pt;
    font-weight: 600;
}}
QLabel[role="section"] {{
    color: {TEXT_MID};
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}
QLabel[role="mono"] {{
    font-family: {FONT_MONO};
    color: {TEXT};
}}
QLabel[role="muted"] {{ color: {TEXT_MID}; }}

QFrame[role="card"] {{
    background-color: {SURFACE_1};
    border: 1px solid {BORDER_LOW};
    border-radius: {RADIUS_LG}px;
}}
QFrame[role="card-raised"] {{
    background-color: {SURFACE_2};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_LG}px;
}}

QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {ACCENT_HI}; }}
QPushButton:disabled {{ background-color: {SURFACE_3}; color: {TEXT_LOW}; }}
QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {TEXT};
    border: 1px solid {BORDER_MED};
}}
QPushButton[variant="ghost"]:hover {{
    background-color: {SURFACE_2};
    border-color: {BORDER_HI};
}}
QPushButton[variant="danger"] {{ background-color: {ERR}; }}
QPushButton[variant="danger"]:hover {{ background-color: #d63a4d; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {SURFACE_3};
    color: {TEXT_HI};
    border: 1px solid {BORDER_MED};
    border-radius: {RADIUS_MD}px;
    padding: 8px 12px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {ACCENT};
}}

QTextEdit#console {{
    background-color: {BG_DEEP};
    color: {TEXT};
    border: 1px solid {BORDER_LOW};
    border-radius: {RADIUS_MD}px;
    font-family: {FONT_MONO};
    font-size: 9pt;
    padding: 8px 10px;
}}

QFrame#nav-rail {{
    background-color: {BG_BASE};
    border-right: 1px solid {BORDER_LOW};
}}
QFrame#nav-rail QPushButton[role="nav-item"] {{
    background-color: transparent;
    color: {TEXT_MID};
    text-align: left;
    padding: 12px 18px;
    border: none;
    border-radius: {RADIUS_MD}px;
    font-weight: 500;
}}
QFrame#nav-rail QPushButton[role="nav-item"]:hover {{
    color: {TEXT_HI};
    background-color: {SURFACE_1};
}}
QFrame#nav-rail QPushButton[role="nav-item"][active="true"] {{
    color: {TEXT_HI};
    background-color: {SURFACE_2};
    border-left: 2px solid {ACCENT};
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_MED}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_MED};
    border-radius: 4px;
    background: {SURFACE_3};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QMessageBox {{ background-color: {SURFACE_1}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
"""
```

- [x] **Step 2: Run theme token test to verify it passes**

Run: `pytest tests/test_theme_tokens.py -v`
Expected: PASS

- [x] **Step 3: Commit**

```bash
git add app/theme.py
git commit -m "feat(theme): replace Cloud theme with unified design system"
```

---

### Task 0.3: Remove the lab-theme concatenation from `main.py`

**Files:**
- Modify: `main.py`

- [x] **Step 1: Drop the lab-theme import and concatenation**

```python
# main.py
from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from app.config import ConfigStore
from app import theme
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Vast.ai Manager")
    app.setStyleSheet(theme.STYLESHEET)

    store = ConfigStore()
    win = MainWindow(store)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Remove the scoped `#lab-shell` prefix from `app/lab/theme.py`**

The lab workspace now inherits styles from the global stylesheet — `app/lab/theme.py` keeps its symbols (BG_DEEP, ACCENT, etc.) as a **re-export layer** during the rest of Phase 0 so nothing breaks. Replace its entire body with:

```python
# app/lab/theme.py
"""Compatibility re-export. All styles now live in app.theme.
This file is deleted at the end of Phase 8."""
from app.theme import *  # noqa: F401,F403

# Empty stylesheet — global one already applies.
STYLESHEET = ""
```

- [x] **Step 3: Manual verify — run the app**

Run: `python main.py`
Expected: the app launches. The Cloud view will look **wrong** (dark backgrounds against the new palette, old button colors gone) — this is fine, Phases 2-4 replace it entirely. The Lab view should look correct.

- [x] **Step 4: Commit**

```bash
git add main.py app/lab/theme.py
git commit -m "feat(theme): single global stylesheet; lab theme is now a re-export shim"
```

---

### Task 0.4: Move `lab/components/primitives.py` to `app/ui/components/primitives.py`

**Files:**
- Create: `app/ui/components/__init__.py` (empty)
- Create: `app/ui/components/primitives.py` (copy of current lab primitives)
- Modify: `app/lab/components/primitives.py` → shim that re-exports

- [x] **Step 1: Create the new package directory and __init__.py**

```python
# app/ui/components/__init__.py
```

- [x] **Step 2: Copy the current lab primitives file verbatim into `app/ui/components/primitives.py`**, then change its import:

```python
# app/ui/components/primitives.py  (top of file)
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget
from PySide6.QtCore import Qt
from app import theme as t
# ... rest of file identical to original lab/components/primitives.py
```

- [x] **Step 3: Replace `app/lab/components/primitives.py` with a re-export shim**

```python
# app/lab/components/primitives.py
"""Compatibility re-export. Deleted at end of Phase 8."""
from app.ui.components.primitives import *  # noqa: F401,F403
```

- [x] **Step 4: Run the app to verify it still launches**

Run: `python main.py`
Expected: app launches; click to Lab view; primitives still render.

- [x] **Step 5: Commit**

```bash
git add app/ui/components/ app/lab/components/primitives.py
git commit -m "refactor: move lab primitives to app/ui/components/primitives.py"
```

---

### Task 0.5: Move `lab/components/nav_rail.py` to `app/ui/components/nav_rail.py`

**Files:**
- Create: `app/ui/components/nav_rail.py`
- Modify: `app/lab/components/nav_rail.py` → shim

- [x] **Step 1: Copy nav_rail.py verbatim to the new location, changing:**
  - `self.setObjectName("lab-nav-rail")` → `self.setObjectName("nav-rail")` (matches new QSS selector)
  - `from app.lab import theme as t` → `from app import theme as t`

Full new file body:

```python
# app/ui/components/nav_rail.py
"""Left nav rail. Emits `selected(key)` on button click."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt
from app import theme as t


NAV_ITEMS = [
    ("instances",  "Instances",    "\u2630"),
    ("dashboard",  "Dashboard",    "\u25C8"),
    ("discover",   "Discover",     "\u2726"),
    ("models",     "Models",       "\u25A4"),
    ("configure",  "Configure",    "\u2699"),
    ("monitor",    "Monitor",      "\u25F4"),
]


class NavRail(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nav-rail")
        self.setFixedWidth(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_4, t.SPACE_5, t.SPACE_3, t.SPACE_4)
        lay.setSpacing(2)

        brand = QLabel("\u2726  VAST.AI")
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

        foot = QLabel("v2 \u2022 remote inference")
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 8pt; padding: 8px;")
        lay.addWidget(foot)

        self.set_active("instances")

    def _on_click(self, key: str):
        self.set_active(key)
        self.selected.emit(key)

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
```

- [x] **Step 2: Replace `app/lab/components/nav_rail.py` with a shim**

```python
# app/lab/components/nav_rail.py
"""Compatibility re-export. Deleted at end of Phase 8."""
from app.ui.components.nav_rail import NavRail, NAV_ITEMS  # noqa: F401
```

- [x] **Step 3: Run the app**

Run: `python main.py`
Expected: Lab sidebar now shows 6 items (Instances added at top). Clicking "Instances" currently does nothing — the view doesn't exist yet. That's expected.

- [x] **Step 4: Commit**

```bash
git add app/ui/components/nav_rail.py app/lab/components/nav_rail.py
git commit -m "refactor: move NavRail to app/ui/components; add Instances item"
```

---

# Phase 1 — AppController: extract worker orchestration

Goal: move every worker lifecycle currently in `MainWindow` into a dedicated `AppController`. The controller owns services, workers, trackers; the shell subscribes via signals. `MainWindow` becomes thinner and the new Instances view (Phase 2) consumes the same signals.

---

### Task 1.1: Failing test for AppController surface

**Files:**
- Create: `tests/test_controller.py`

- [x] **Step 1: Write unit tests for the controller (mocking VastService and SSHService)**

```python
# tests/test_controller.py
"""AppController owns all worker lifecycles. Tests pin the public contract
the shell will rely on. VastService/SSHService are mocked; workers aren't
started (we test wiring, not threading)."""
from unittest.mock import MagicMock, patch
import pytest
from app.controller import AppController
from app.config import ConfigStore
from app.models import AppConfig, InstanceState, TunnelStatus


@pytest.fixture
def config():
    return AppConfig(api_key="fake", refresh_interval_seconds=30,
                     default_tunnel_port=11434)


@pytest.fixture
def store(tmp_path, config):
    s = ConfigStore(path=tmp_path / "config.json")
    s.save(config)
    return s


def test_controller_starts_uninitialized(store):
    c = AppController(store)
    assert c.vast is None
    assert c.last_instances == []
    assert c.today_spend() == 0.0


def test_controller_bootstrap_creates_workers(store):
    c = AppController(store)
    with patch("app.controller.VastService") as VS:
        VS.return_value = MagicMock()
        c.bootstrap()
    assert c.vast is not None
    assert c.list_worker is not None
    assert c.action_worker is not None
    assert c.tunnel_starter is not None


def test_controller_signals_exposed(store):
    c = AppController(store)
    for sig in ("instances_refreshed", "refresh_failed", "tunnel_status_changed",
                "action_done", "live_metrics", "model_changed", "log_line"):
        assert hasattr(c, sig), f"missing signal {sig}"


def test_controller_tunnel_state_tracking(store):
    c = AppController(store)
    c._on_tunnel_status(123, TunnelStatus.CONNECTED.value, "ok")
    assert c.tunnel_states[123] == TunnelStatus.CONNECTED


def test_controller_shutdown_stops_everything(store):
    c = AppController(store)
    c.ssh = MagicMock()
    c.shutdown()
    c.ssh.stop_all.assert_called_once()
```

- [x] **Step 2: Run test to verify failure**

Run: `pytest tests/test_controller.py -v`
Expected: FAIL — `app.controller` doesn't exist.

- [x] **Step 3: Commit**

```bash
git add tests/test_controller.py
git commit -m "test: failing AppController contract"
```

---

### Task 1.2: Implement AppController

**Files:**
- Create: `app/controller.py`

- [x] **Step 1: Write the controller**

The controller is a `QObject` that encapsulates everything `MainWindow` currently does between `_bootstrap_service()` and `_check_tunnels_health()`. Copy the logic from [main_window.py:192-654](app/ui/main_window.py:192) — the relevant methods are `_bootstrap_service`, `_destroy_workers`, `_apply_interval`, `_on_refreshed`, `_on_refresh_failed`, `_on_activate`, `_on_deactivate`, `_on_reconnect`, `_on_disconnect`, `_on_action_done`, `_start_tunnel_for`, `_on_tunnel_status`, `_start_live_metrics`, `_stop_live_metrics`, `_sync_live_workers`, `_can_ssh_silently`, `_start_model_watcher`, `_stop_model_watcher`, `_check_tunnels_health`, `_ensure_passphrase`.

```python
# app/controller.py
"""Single orchestrator for Vast.ai services, workers, SSH and billing.
The app shell/views subscribe to signals; all state lives here."""
from __future__ import annotations
from PySide6.QtCore import QObject, QTimer, Signal, QThread
from app.config import ConfigStore
from app.models import AppConfig, Instance, InstanceState, TunnelStatus, UserInfo
from app.services.vast_service import VastService
from app.services.ssh_service import SSHService
from app.workers.list_worker import ListWorker
from app.workers.action_worker import ActionWorker
from app.workers.tunnel_starter import TunnelStarter
from app.workers.live_metrics import LiveMetricsWorker
from app.workers.model_watcher import ModelWatcher
from app.workers.llama_probe import LlamaReadyProbe
from app.billing import DailySpendTracker


class AppController(QObject):
    # ---- High-level signals the shell/views subscribe to ----
    instances_refreshed = Signal(list, object)   # list[Instance], UserInfo
    refresh_failed      = Signal(str, str)       # kind, message
    tunnel_status_changed = Signal(int, str, str)  # iid, status, message
    action_done         = Signal(int, str, bool, str)  # iid, action, ok, msg
    live_metrics        = Signal(int, dict)      # iid, payload
    model_changed       = Signal(int, str)       # iid, model_id
    log_line            = Signal(str)            # log message
    passphrase_needed   = Signal()               # shell must prompt

    # ---- Internal triggers (Qt cross-thread signals) ----
    _trigger_refresh = Signal()
    _trigger_start   = Signal(int)
    _trigger_stop    = Signal(int)
    _trigger_connect = Signal(int, int)

    def __init__(self, config_store: ConfigStore, parent=None):
        super().__init__(parent)
        self.config_store = config_store
        self.config: AppConfig = config_store.load()
        self.vast: VastService | None = None
        self.ssh = SSHService(ssh_key_path=self.config.ssh_key_path)
        self.tracker = DailySpendTracker()

        self.last_instances: list[Instance] = []
        self.last_user: UserInfo | None = None
        self.tunnel_states: dict[int, TunnelStatus] = {}

        self._pending_start: set[int] = set()
        self._pending_stop:  set[int] = set()
        self._pending_tunnel:set[int] = set()

        self._live_workers:   dict[int, LiveMetricsWorker] = {}
        self._model_watchers: dict[int, ModelWatcher] = {}
        self._llama_probes:   dict[int, LlamaReadyProbe] = {}

        self.list_thread   = QThread()
        self.action_thread = QThread()
        self.tunnel_thread = QThread()
        self.list_worker:   ListWorker | None    = None
        self.action_worker: ActionWorker | None  = None
        self.tunnel_starter:TunnelStarter | None = None

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_timer_tick)

    # ---- Convenience ----
    def today_spend(self) -> float:
        return self.tracker.today_spend()

    # ---- Lifecycle ----
    def bootstrap(self):
        """Spin up workers against the current API key."""
        if not self.config.api_key:
            return
        self.vast = VastService(self.config.api_key)
        self._destroy_workers()

        self.list_thread = QThread()
        self.list_worker = ListWorker(self.vast)
        self.list_worker.moveToThread(self.list_thread)
        self.list_worker.refreshed.connect(self._on_refreshed)
        self.list_worker.failed.connect(self._on_refresh_failed)
        self._trigger_refresh.connect(self.list_worker.refresh)
        self.list_thread.start()

        self.action_thread = QThread()
        self.action_worker = ActionWorker(self.vast)
        self.action_worker.moveToThread(self.action_thread)
        self.action_worker.finished.connect(self._on_action_done)
        self._trigger_start.connect(self.action_worker.start)
        self._trigger_stop.connect(self.action_worker.stop)
        self.action_thread.start()

        self.tunnel_thread = QThread()
        self.tunnel_starter = TunnelStarter(self.vast, self.ssh, self.config)
        self.tunnel_starter.moveToThread(self.tunnel_thread)
        self.tunnel_starter.status_changed.connect(self._on_tunnel_status)
        self._trigger_connect.connect(self.tunnel_starter.connect)
        self.tunnel_thread.start()

        self._apply_interval()
        self.log_line.emit("Conectando à Vast.ai...")
        self._trigger_refresh.emit()

    def shutdown(self):
        self.refresh_timer.stop()
        for iid in list(self._live_workers.keys()):
            self._stop_live_metrics(iid)
        for iid in list(self._model_watchers.keys()):
            self._stop_model_watcher(iid)
        for iid in list(self._llama_probes.keys()):
            probe = self._llama_probes.pop(iid)
            probe.stop(); probe.wait(2000)
        if self.ssh is not None:
            self.ssh.stop_all()
        self._destroy_workers()

    def _destroy_workers(self):
        if self.list_worker is not None:
            for sig in (self._trigger_refresh, self._trigger_start,
                        self._trigger_stop, self._trigger_connect):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        for t in (self.list_thread, self.action_thread, self.tunnel_thread):
            if t.isRunning():
                t.quit(); t.wait(1500)

    # ---- Config ----
    def apply_config(self, cfg: AppConfig):
        changed_key = cfg.api_key != self.config.api_key
        self.config = cfg
        self.config_store.save(cfg)
        self.ssh.ssh_key_path = cfg.ssh_key_path
        self.log_line.emit("Configurações salvas.")
        if changed_key:
            self.bootstrap()
        else:
            self._apply_interval()

    def _apply_interval(self):
        secs = self.config.refresh_interval_seconds
        if secs <= 0:
            self.refresh_timer.stop()
        else:
            self.refresh_timer.start(secs * 1000)

    def _on_timer_tick(self):
        if self.vast is not None:
            self._trigger_refresh.emit()

    def request_refresh(self):
        if self.vast is not None:
            self._trigger_refresh.emit()

    # ---- Refresh callbacks ----
    def _on_refreshed(self, instances: list, user):
        self.last_instances = instances
        self.last_user = user
        for inst in instances:
            self.tracker.update(inst)
        self._check_tunnels_health()
        self._sync_live_workers(instances)
        self.instances_refreshed.emit(instances, user)

    def _on_refresh_failed(self, kind: str, message: str):
        self.log_line.emit(f"Erro ({kind}): {message}")
        self.refresh_failed.emit(kind, message)

    # ---- Actions ----
    def _find_instance(self, iid: int) -> Instance | None:
        return next((i for i in self.last_instances if i.id == iid), None)

    def activate(self, iid: int) -> bool:
        if iid in self._pending_start:
            return False
        if self.config.auto_connect_on_activate and not self._has_usable_passphrase():
            self.passphrase_needed.emit()
            return False
        self._pending_start.add(iid)
        self.log_line.emit(f"Ativando instância {iid}...")
        self._trigger_start.emit(iid)
        return True

    def deactivate(self, iid: int):
        if iid in self._pending_stop:
            return
        self._pending_stop.add(iid)
        self.ssh.stop_tunnel(iid)
        self._stop_live_metrics(iid)
        self._stop_model_watcher(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.log_line.emit(f"Desativando instância {iid}...")
        self._trigger_stop.emit(iid)

    def connect_tunnel(self, iid: int):
        if iid in self._pending_tunnel:
            return
        if not self._has_usable_passphrase():
            self.passphrase_needed.emit()
            return
        self._pending_tunnel.add(iid)
        self.tunnel_states[iid] = TunnelStatus.CONNECTING
        self.tunnel_status_changed.emit(iid, TunnelStatus.CONNECTING.value, "connecting")
        self.log_line.emit(f"Conectando #{iid}...")
        self._trigger_connect.emit(iid, self.config.default_tunnel_port)

    def disconnect_tunnel(self, iid: int):
        self.ssh.stop_tunnel(iid)
        self._stop_live_metrics(iid)
        self._stop_model_watcher(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.log_line.emit(f"Conexão #{iid} encerrada.")
        self.tunnel_status_changed.emit(iid, TunnelStatus.DISCONNECTED.value, "disconnected")

    def _on_action_done(self, iid: int, action: str, ok: bool, msg: str):
        if action == "start":
            self._pending_start.discard(iid)
        elif action == "stop":
            self._pending_stop.discard(iid)
        if ok:
            self.log_line.emit(f"✓ {action} #{iid}: {msg}")
            if action == "start" and self.config.auto_connect_on_activate:
                self.connect_tunnel(iid)
        else:
            self.log_line.emit(f"✗ {action} #{iid}: {msg}")
        self.action_done.emit(iid, action, ok, msg)
        self._trigger_refresh.emit()

    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        self.tunnel_states[iid] = TunnelStatus(status)
        self.log_line.emit(f"Túnel #{iid}: {msg}")
        if self.tunnel_states[iid] == TunnelStatus.CONNECTED:
            self._pending_tunnel.discard(iid)
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
            self._start_model_watcher(iid)
        elif self.tunnel_states[iid] == TunnelStatus.FAILED:
            self._pending_tunnel.discard(iid)
            low = msg.lower()
            if ("permission denied" in low or "publickey" in low
                    or "host key verification failed" in low):
                self.ssh.clear_passphrase()
                self._stop_live_metrics(iid)
            self._stop_model_watcher(iid)
        self.tunnel_status_changed.emit(iid, status, msg)

    # ---- Live metrics ----
    def _has_usable_passphrase(self) -> bool:
        if not self.ssh.ssh_key_path:
            return True
        if not self.ssh.is_passphrase_required():
            return True
        return self.ssh.passphrase_cache is not None

    def _sync_live_workers(self, instances: list):
        if not self._has_usable_passphrase():
            return
        running = {i.id for i in instances
                   if i.state == InstanceState.RUNNING and i.ssh_host and i.ssh_port}
        for iid in running:
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
        for iid in list(self._live_workers.keys()):
            if iid not in running:
                self._stop_live_metrics(iid)

    def _start_live_metrics(self, iid: int):
        self._stop_live_metrics(iid)
        inst = self._find_instance(iid)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            return
        w = LiveMetricsWorker(iid, inst.ssh_host, inst.ssh_port, self.ssh)
        w.metrics.connect(self.live_metrics)
        w.error.connect(lambda i, e: self.log_line.emit(f"Métricas live #{i}: {e}"))
        self._live_workers[iid] = w
        w.start()

    def _stop_live_metrics(self, iid: int):
        w = self._live_workers.pop(iid, None)
        if w is not None:
            w.stop(); w.wait(2000)

    def _start_model_watcher(self, iid: int):
        self._stop_model_watcher(iid)
        w = ModelWatcher(iid, self.config.default_tunnel_port)
        w.model_changed.connect(self.model_changed)
        self._model_watchers[iid] = w
        w.start()

    def _stop_model_watcher(self, iid: int):
        w = self._model_watchers.pop(iid, None)
        if w is not None:
            w.stop(); w.wait(2000)

    def _check_tunnels_health(self):
        for iid, status in list(self.tunnel_states.items()):
            if status == TunnelStatus.CONNECTED:
                handle = self.ssh.get(iid)
                if handle is None or not handle.alive():
                    self.tunnel_states[iid] = TunnelStatus.FAILED
                    self._stop_live_metrics(iid)
                    self._stop_model_watcher(iid)
                    self.log_line.emit(f"Conexão #{iid} caiu.")
                    self.tunnel_status_changed.emit(iid, TunnelStatus.FAILED.value, "health-check-failed")
        running_ids = {i.id for i in self.last_instances if i.state == InstanceState.RUNNING}
        for iid in list(self._live_workers.keys()):
            if iid not in running_ids:
                self._stop_live_metrics(iid)
        for iid in list(self._model_watchers.keys()):
            if iid not in running_ids:
                self._stop_model_watcher(iid)
```

- [x] **Step 2: Run controller tests to verify pass**

Run: `pytest tests/test_controller.py -v`
Expected: PASS

- [x] **Step 3: Commit**

```bash
git add app/controller.py
git commit -m "feat(controller): AppController owns workers + SSH + tracker"
```

---

### Task 1.3: Wire MainWindow to use AppController (parity refactor)

**Files:**
- Modify: `app/ui/main_window.py`

This is a non-behavior-changing refactor — MainWindow delegates to the controller but keeps identical UX so nothing regresses before the real migration starts.

- [x] **Step 1: Replace MainWindow's private state/workers with an AppController instance**

At the top of `MainWindow.__init__`:

```python
from app.controller import AppController
# ...
self.controller = AppController(config_store, self)
self.controller.instances_refreshed.connect(self._on_refreshed)
self.controller.refresh_failed.connect(self._on_refresh_failed)
self.controller.tunnel_status_changed.connect(self._on_tunnel_status)
self.controller.action_done.connect(self._on_action_done)
self.controller.live_metrics.connect(self._on_live_metrics)
self.controller.model_changed.connect(self._on_model_changed)
self.controller.log_line.connect(self.log.log)
self.controller.passphrase_needed.connect(self._prompt_passphrase)
```

Delete the local `_pending_*`, `_live_workers`, `_model_watchers`, `_llama_probes`, `tracker`, `vast`, `ssh`, `list_thread`, `action_thread`, `tunnel_thread`, `_trigger_*` — they now live on `controller`.

- [x] **Step 2: Route every handler through the controller**

- `_on_activate(iid)` → `self.controller.activate(iid)`
- `_on_deactivate(iid)` → prompt then `self.controller.deactivate(iid)`
- `_on_reconnect(iid)` → `self.controller.connect_tunnel(iid)`
- `_on_disconnect(iid)` → `self.controller.disconnect_tunnel(iid)`
- `_on_manual_refresh()` → `self.controller.request_refresh()`
- `_bootstrap_service()` → `self.controller.bootstrap()`
- `_on_settings_saved(cfg)` → `self.controller.apply_config(cfg)` then `self._rebuild_cards(self.controller.last_instances)`
- `_prompt_passphrase()` → the existing `_ensure_passphrase()` body; on success call `self.ssh.set_passphrase(pwd)` using `self.controller.ssh`
- `closeEvent()` → `self.controller.shutdown()`

- [x] **Step 3: Run the app and exercise every Cloud action**

Run: `python main.py`
Expected: open Cloud view → refresh, activate, deactivate, connect tunnel, disconnect, open terminal, manage models — all still work. Log still updates. No regressions.

- [x] **Step 4: Commit**

```bash
git add app/ui/main_window.py
git commit -m "refactor(main-window): delegate all worker orchestration to AppController"
```

---

# Phase 2 — Instances view: billing strip + instance list + console drawer

Goal: build the new landing view in Lab. It consumes `AppController` signals directly so there's no MainWindow dependency. Three building blocks: `BillingStrip`, `InstanceCard` (redesigned), `ConsoleDrawer`.

---

### Task 2.1: BillingStrip primitive + test

**Files:**
- Create: `app/ui/views/billing_strip.py`
- Create: `app/ui/views/__init__.py` (empty)
- Create: `tests/test_billing_strip.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_billing_strip.py
"""BillingStrip renders the same numbers as the old BillingHeader but using
the new design tokens. Tests assert text content, not styling."""
import pytest
from PySide6.QtWidgets import QApplication
from app.ui.views.billing_strip import BillingStrip
from app.models import AppConfig, UserInfo, Instance, InstanceState


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _inst(iid=1, dph=0.5, state=InstanceState.RUNNING):
    return Instance(
        id=iid, label=f"#{iid}", state=state, gpu_name="RTX 3090",
        num_gpus=1, gpu_ram_gb=24, image="base", dph=dph,
    )


def test_renders_balance(qapp):
    s = BillingStrip(AppConfig())
    s.update_values(UserInfo(balance=12.34, email="x"), [], 0.0)
    assert "12.34" in s.balance_lbl.text()


def test_renders_burn_and_autonomy(qapp):
    s = BillingStrip(AppConfig())
    s.update_values(UserInfo(balance=10.0, email="x"),
                    [_inst(dph=1.0)], today_spend=2.0)
    assert "1." in s.burn_lbl.text()
    assert "Autonomia" in s.autonomy_lbl.text()


def test_today_spend(qapp):
    s = BillingStrip(AppConfig())
    s.update_values(UserInfo(balance=5.0, email="x"), [], 1.23)
    assert "1.23" in s.today_lbl.text()
```

Run: `pytest tests/test_billing_strip.py -v`
Expected: FAIL (module missing)

- [x] **Step 2: Implement BillingStrip using new design tokens**

```python
# app/ui/views/billing_strip.py
"""Compact always-visible billing strip. Same numbers as the old BillingHeader
(balance, burn rate, autonomy, today spend, projection) rendered on the new
design system — horizontal layout of MetricTiles + projection subtitle."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QWidget
from app import theme as t
from app.billing import (
    BurnRateTracker, autonomy_hours, format_autonomy,
    project_balance, total_burn_rate,
)
from app.models import AppConfig, Instance, UserInfo
from app.ui.components.primitives import GlassCard


class BillingStrip(GlassCard):
    def __init__(self, config: AppConfig | None = None, parent=None):
        super().__init__(raised=True, parent=parent)
        self._config = config or AppConfig()
        self._tracker = BurnRateTracker(
            window_size=max(1, self._config.burn_rate_smoothing_window)
        )
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        self._lay.setSpacing(t.SPACE_2)

        row = QHBoxLayout()
        row.setSpacing(t.SPACE_6)
        self.balance_lbl = _metric("SALDO", "—")
        self.burn_lbl    = _metric("GASTANDO", "$0.00/h")
        self.autonomy_lbl= _metric("AUTONOMIA", "—")
        self.today_lbl   = _metric("HOJE", "$0.00")
        row.addWidget(self.balance_lbl)
        row.addWidget(self.burn_lbl)
        row.addWidget(self.autonomy_lbl)
        row.addWidget(self.today_lbl)
        row.addStretch()
        self._lay.addLayout(row)

        self.projection_lbl = QLabel("")
        self.projection_lbl.setProperty("role", "muted")
        self.projection_lbl.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID};")
        self._lay.addWidget(self.projection_lbl)

    def apply_config(self, config: AppConfig) -> None:
        self._config = config
        new_window = max(1, config.burn_rate_smoothing_window)
        if new_window != self._tracker.window_size:
            self._tracker = BurnRateTracker(window_size=new_window)

    def update_values(self, user: UserInfo | None,
                      instances: list[Instance], today_spend: float) -> None:
        cfg = self._config
        if user is None:
            self.balance_lbl.set_value("—")
        else:
            self.balance_lbl.set_value(f"${user.balance:.2f}")

        burn = total_burn_rate(
            instances,
            include_storage=cfg.include_storage_in_burn_rate,
            estimated_network_cost_per_hour=cfg.estimated_network_cost_per_hour,
        )
        smoothed = self._tracker.update(burn)
        trend = self._tracker.get_trend()
        display_burn = smoothed if smoothed > 0 else burn
        self.burn_lbl.set_value(f"${display_burn:.2f}/h {trend.arrow}")

        hours = autonomy_hours(user.balance if user else 0.0, display_burn)
        if hours is None:
            self.autonomy_lbl.set_value("—", color=t.TEXT)
            self.projection_lbl.setText("")
        else:
            color = t.autonomy_color(hours)
            self.autonomy_lbl.set_value(format_autonomy(hours), color=color)
            self.balance_lbl.set_value(self.balance_lbl.value_text, color=color)
            if user is not None and display_burn > 0:
                p24 = project_balance(user.balance, display_burn, 24)
                p7  = project_balance(user.balance, display_burn, 24 * 7)
                p30 = project_balance(user.balance, display_burn, 24 * 30)
                self.projection_lbl.setText(
                    f"Projeção  ·  24h → ${p24['balance']:.2f}  ·  "
                    f"7d → ${p7['balance']:.2f}  ·  30d → ${p30['balance']:.2f}"
                )
            else:
                self.projection_lbl.setText("")

        self.today_lbl.set_value(f"${today_spend:.2f}")


class _metric(QWidget):
    """Private helper — small two-line metric: uppercase label + big value."""
    def __init__(self, label: str, initial: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        self._k = QLabel(label); self._k.setProperty("role", "section")
        self._v = QLabel(initial)
        self._v.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 14pt; font-weight: 700;"
        )
        v.addWidget(self._k); v.addWidget(self._v)
        self.value_text = initial

    def set_value(self, text: str, color: str | None = None):
        self.value_text = text
        self._v.setText(text)
        if color:
            self._v.setStyleSheet(
                f"color: {color}; font-size: 14pt; font-weight: 700;"
            )

    def text(self) -> str:  # shim for tests
        return self._v.text()
```

Note the test reads `.text()` — adapt the test to `.value_text` if needed, or keep the `text()` method as shown.

- [x] **Step 3: Run test to verify pass**

Run: `pytest tests/test_billing_strip.py -v`
Expected: PASS

- [x] **Step 4: Commit**

```bash
git add app/ui/views/ tests/test_billing_strip.py
git commit -m "feat(view): BillingStrip — compact, design-system-native billing widget"
```

---

### Task 2.2: ConsoleDrawer (bottom log panel)

**Files:**
- Create: `app/ui/views/console_drawer.py`

- [x] **Step 1: Write the drawer**

```python
# app/ui/views/console_drawer.py
"""Bottom console drawer: collapsible log panel styled via the QTextEdit#console
rule in app.theme. Header row with a caret toggle and a Clear button."""
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
)
from PySide6.QtCore import Qt
from app import theme as t


class ConsoleDrawer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("console-drawer")
        self.setStyleSheet(
            f"#console-drawer {{ background: transparent; border: none; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_2)

        bar = QHBoxLayout()
        self.toggle_btn = QPushButton("▾  Console")
        self.toggle_btn.setProperty("variant", "ghost")
        self.toggle_btn.setFixedHeight(28)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        self.clear_btn = QPushButton("Limpar")
        self.clear_btn.setProperty("variant", "ghost")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.clicked.connect(lambda: self.view.clear())
        bar.addWidget(self.toggle_btn)
        bar.addStretch()
        bar.addWidget(self.clear_btn)
        root.addLayout(bar)

        self.view = QTextEdit()
        self.view.setObjectName("console")
        self.view.setReadOnly(True)
        self.view.setFixedHeight(140)
        root.addWidget(self.view)

        self._expanded = True

    def _toggle(self):
        self._expanded = not self._expanded
        self.view.setVisible(self._expanded)
        self.toggle_btn.setText(("▾  Console" if self._expanded else "▸  Console"))

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.view.append(f"[{ts}] {message}")
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())
```

- [x] **Step 2: Manual verify via a tiny scratch script (optional)**

```python
# scratch_console.py (not committed)
from PySide6.QtWidgets import QApplication
from app.ui.views.console_drawer import ConsoleDrawer
from app import theme
app = QApplication([])
app.setStyleSheet(theme.STYLESHEET)
w = ConsoleDrawer(); w.show()
for i in range(5): w.log(f"message {i}")
app.exec()
```

- [x] **Step 3: Commit**

```bash
git add app/ui/views/console_drawer.py
git commit -m "feat(view): ConsoleDrawer — collapsible console log primitive"
```

---

### Task 2.3: Redesigned InstanceCard

**Files:**
- Create: `app/ui/views/instance_card.py`

This is the biggest visual port. Preserve every signal and state transition from [instance_card.py](app/ui/instance_card.py) but rebuild the layout using `GlassCard` and the new tokens.

- [x] **Step 1: Write the new card**

```python
# app/ui/views/instance_card.py
"""Instance card — dashboard-style dark surface built from the new design
system. Preserves every signal/state from the Cloud version so AppController
wiring is unchanged."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QSizePolicy, QWidget,
)
from app import theme as t
from app.models import Instance, InstanceState, TunnelStatus
from app.ui.components.primitives import GlassCard, SectionHeader, StatusPill


STATE_LABELS = {
    InstanceState.STOPPED:  ("○ Desativada",    "muted"),
    InstanceState.STARTING: ("◌ Ativando…",     "warn"),
    InstanceState.RUNNING:  ("● Ativa",         "ok"),
    InstanceState.STOPPING: ("◌ Desativando…",  "warn"),
    InstanceState.UNKNOWN:  ("? Desconhecido",  "muted"),
}

TUNNEL_LABELS = {
    TunnelStatus.DISCONNECTED: ("Desconectado", "info"),
    TunnelStatus.CONNECTING:   ("Conectando…",  "warn"),
    TunnelStatus.CONNECTED:    ("Conectado",    "live"),
    TunnelStatus.FAILED:       ("Falha",        "err"),
}


def _fmt_duration(seconds: int | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    h, r = divmod(seconds, 3600)
    m, _ = divmod(r, 60)
    return f"{h}h {m}m" if h else f"{m}m"


class _Bar(QWidget):
    """Inline labeled progress bar. Replaces the old MetricBar."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(10)
        self.k = QLabel(label); self.k.setFixedWidth(56)
        self.k.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 9pt;")
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.v = QLabel("—")
        self.v.setAlignment(Qt.AlignRight | Qt.AlignVCenter); self.v.setMinimumWidth(140)
        self.v.setStyleSheet(f"color: {t.TEXT}; font-family: {t.FONT_MONO}; font-size: 9pt;")
        h.addWidget(self.k); h.addWidget(self.bar, 1); h.addWidget(self.v)
        self._color(t.TEXT_MID)

    def set_value(self, percent: float | None, text: str | None = None):
        if percent is None:
            self.bar.setValue(0); self.v.setText("—"); self._color(t.TEXT_MID); return
        p = max(0.0, min(100.0, percent))
        self.bar.setValue(int(p))
        self.v.setText(text if text is not None else f"{p:.0f}%")
        self._color(t.metric_color(p))

    def _color(self, color: str):
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {t.SURFACE_3}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )


class InstanceCard(GlassCard):
    activate_requested      = Signal(int)
    deactivate_requested    = Signal(int)
    reconnect_requested     = Signal(int)
    disconnect_requested    = Signal(int)
    open_terminal_requested = Signal(int)
    open_lab_requested      = Signal(int)  # renamed from models_requested
    copy_endpoint_requested = Signal(int)

    def __init__(self, instance: Instance, parent=None):
        super().__init__(parent=parent)
        self.instance = instance
        self.tunnel_status = TunnelStatus.DISCONNECTED
        self.local_port = 11434
        self._live: dict = {}
        self._loaded_model: str | None = None

        # ---- Header: state pill + gpu line ----
        head = QHBoxLayout()
        self.state_pill = StatusPill("—", "muted")
        head.addWidget(self.state_pill)
        head.addStretch()
        self.gpu_lbl = QLabel("")
        self.gpu_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 10pt;")
        head.addWidget(self.gpu_lbl)
        self._lay.addLayout(head)

        # ---- Title row: instance label + hourly cost ----
        title_row = QHBoxLayout()
        self.title_lbl = QLabel("")
        self.title_lbl.setProperty("role", "title")
        self.cost_lbl = QLabel("")
        self.cost_lbl.setStyleSheet(
            f"color: {t.ACCENT}; font-size: 11pt; font-weight: 700; font-family: {t.FONT_MONO};"
        )
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        title_row.addWidget(self.cost_lbl)
        self._lay.addLayout(title_row)

        # ---- Subtitle: image + uptime ----
        self.subtitle_lbl = QLabel("")
        self.subtitle_lbl.setProperty("role", "muted")
        self.subtitle_lbl.setWordWrap(True)
        self._lay.addWidget(self.subtitle_lbl)

        # ---- Hardware detail line ----
        self.details_lbl = QLabel("")
        self.details_lbl.setProperty("role", "muted")
        self.details_lbl.setWordWrap(True)
        self.details_lbl.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: 9pt;")
        self._lay.addWidget(self.details_lbl)

        # ---- Metrics container (visible only when CONNECTED) ----
        self.metrics_container = QFrame()
        self.metrics_container.setStyleSheet("QFrame { background: transparent; border: none; }")
        m = QVBoxLayout(self.metrics_container)
        m.setContentsMargins(0, t.SPACE_2, 0, t.SPACE_2); m.setSpacing(t.SPACE_2)
        self.gpu_bar  = _Bar("GPU")
        self.vram_bar = _Bar("vRAM")
        self.cpu_bar  = _Bar("CPU")
        self.ram_bar  = _Bar("RAM")
        self.disk_bar = _Bar("Disco")
        self.net_lbl  = QLabel("Rede   ↓ — / ↑ —")
        self.net_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 9pt;")
        for b in (self.gpu_bar, self.vram_bar, self.cpu_bar, self.ram_bar, self.disk_bar):
            m.addWidget(b)
        m.addWidget(self.net_lbl)
        self._lay.addWidget(self.metrics_container)

        # ---- Endpoint row ----
        self.endpoint_wrap = QFrame()
        self.endpoint_wrap.setStyleSheet("QFrame { background: transparent; border: none; }")
        er = QHBoxLayout(self.endpoint_wrap); er.setContentsMargins(0, 0, 0, 0)
        self.endpoint_lbl = QLabel("")
        self.endpoint_lbl.setProperty("role", "mono")
        self.endpoint_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.copy_btn = QPushButton("Copiar")
        self.copy_btn.setProperty("variant", "ghost")
        self.copy_btn.setFixedWidth(88)
        self.copy_btn.clicked.connect(lambda: self.copy_endpoint_requested.emit(self.instance.id))
        er.addWidget(self.endpoint_lbl); er.addStretch(); er.addWidget(self.copy_btn)
        self._lay.addWidget(self.endpoint_wrap)

        # ---- Model badge ----
        self.model_badge = QLabel("")
        self.model_badge.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.model_badge.setStyleSheet(
            f"QLabel {{ background: {t.SURFACE_2}; color: {t.TEXT};"
            f" border: 1px solid {t.BORDER_MED};"
            f" border-radius: 999px; padding: 4px 12px;"
            f" font-family: {t.FONT_MONO}; font-size: 9pt; }}"
        )
        self.model_badge.setVisible(False)
        self._lay.addWidget(self.model_badge)

        # ---- Actions row ----
        actions = QHBoxLayout()
        self.primary_btn      = QPushButton(""); self.primary_btn.clicked.connect(self._on_primary)
        self.lab_btn          = QPushButton("Abrir no Lab"); self.lab_btn.setProperty("variant", "ghost")
        self.lab_btn.clicked.connect(lambda: self.open_lab_requested.emit(self.instance.id))
        self.terminal_btn     = QPushButton("Terminal"); self.terminal_btn.setProperty("variant", "ghost")
        self.terminal_btn.clicked.connect(lambda: self.open_terminal_requested.emit(self.instance.id))
        self.disconnect_btn   = QPushButton("Desconectar"); self.disconnect_btn.setProperty("variant", "ghost")
        self.disconnect_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.instance.id))
        self.deactivate_btn   = QPushButton("Desativar"); self.deactivate_btn.setProperty("variant", "danger")
        self.deactivate_btn.clicked.connect(lambda: self.deactivate_requested.emit(self.instance.id))
        for b in (self.primary_btn, self.lab_btn, self.terminal_btn, self.disconnect_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(self.deactivate_btn)
        self._lay.addLayout(actions)

        self.update_from(instance, self.tunnel_status, self.local_port)

    # ---- Public API used by the Instances view ----
    def update_from(self, inst: Instance, tunnel_status: TunnelStatus, local_port: int):
        """Identical contract to the old card — see [instance_card.py:166-263]
        for the full state machine. Reimplemented against the new widgets."""
        self.instance = inst
        self.tunnel_status = tunnel_status
        self.local_port = local_port

        label, level = STATE_LABELS.get(inst.state, STATE_LABELS[InstanceState.UNKNOWN])
        if inst.state == InstanceState.RUNNING:
            t_label, t_level = TUNNEL_LABELS[tunnel_status]
            self.state_pill.set_status(f"{label}  ·  {t_label}", t_level)
        else:
            self.state_pill.set_status(label, level)

        gpu_part = f"{inst.num_gpus}× {inst.gpu_name}" if inst.num_gpus > 1 else (inst.gpu_name or "GPU")
        self.gpu_lbl.setText(f"{gpu_part} · {inst.gpu_ram_gb:.0f} GB VRAM")

        self.title_lbl.setText(inst.label or f"Instance #{inst.id}")
        self.cost_lbl.setText(f"${inst.dph:.2f}/h")

        sub = []
        if inst.image: sub.append(inst.image)
        if inst.state == InstanceState.RUNNING and inst.duration_seconds:
            sub.append(f"ativa há {_fmt_duration(inst.duration_seconds)}")
        self.subtitle_lbl.setText(" · ".join(sub))

        self.details_lbl.setText(self._format_details(inst))

        is_running = inst.state == InstanceState.RUNNING
        is_connected = is_running and tunnel_status == TunnelStatus.CONNECTED
        self.metrics_container.setVisible(is_connected)
        if not is_connected:
            for b in (self.gpu_bar, self.vram_bar, self.cpu_bar, self.ram_bar, self.disk_bar):
                b.set_value(None)
            self.net_lbl.setText("Rede   ↓ — / ↑ —")
            self._live = {}
        else:
            self._render_metrics_from_instance(inst)

        self.endpoint_wrap.setVisible(is_connected)
        if is_connected:
            self.endpoint_lbl.setText(f"🔗  http://127.0.0.1:{local_port}")

        self.model_badge.setVisible(bool(self._loaded_model) and is_connected)
        if is_running and self._live:
            self._apply_live_overlay()

        self._update_buttons()

    def set_live_metrics(self, d: dict):
        self._live = d or {}
        if self.instance.state == InstanceState.RUNNING:
            self._apply_live_overlay()

    def clear_live_metrics(self):
        self._live = {}

    def set_loaded_model(self, model_id: str | None):
        mid = (model_id or "").strip()
        self._loaded_model = mid or None
        if not mid:
            self.model_badge.setVisible(False); self.model_badge.setText(""); return
        disp = mid if len(mid) <= 60 else "…" + mid[-58:]
        self.model_badge.setText(f"🤖  {disp}")
        self.model_badge.setToolTip(mid)
        if self.endpoint_wrap.isVisible():
            self.model_badge.setVisible(True)

    # ---- internals ----
    def _on_primary(self):
        s = self.instance.state
        if s == InstanceState.STOPPED:
            self.activate_requested.emit(self.instance.id); return
        if s == InstanceState.RUNNING and self.tunnel_status in (
                TunnelStatus.FAILED, TunnelStatus.DISCONNECTED):
            self.reconnect_requested.emit(self.instance.id)

    def _render_metrics_from_instance(self, inst: Instance):
        # Identical logic to [instance_card.py:213-243]
        if inst.gpu_util is not None:
            temp = f"  {inst.gpu_temp:.0f}°C" if inst.gpu_temp is not None else ""
            self.gpu_bar.set_value(inst.gpu_util, f"{inst.gpu_util:.0f}%{temp}")
        if inst.vram_usage_gb is not None and inst.gpu_ram_gb:
            pct = (inst.vram_usage_gb / inst.gpu_ram_gb) * 100.0
            self.vram_bar.set_value(pct, f"{inst.vram_usage_gb:.1f} / {inst.gpu_ram_gb:.1f} GB")
        if inst.cpu_util is not None:
            self.cpu_bar.set_value(inst.cpu_util, f"{inst.cpu_util:.0f}%")
        if inst.ram_total_gb and inst.ram_used_gb is not None:
            pct = (inst.ram_used_gb / inst.ram_total_gb) * 100.0
            self.ram_bar.set_value(pct, f"{pct:.0f}% ({inst.ram_used_gb:.0f} / {inst.ram_total_gb:.0f} GB)")
        if inst.disk_space_gb and inst.disk_usage_gb is not None:
            pct = (inst.disk_usage_gb / inst.disk_space_gb) * 100.0
            self.disk_bar.set_value(pct, f"{inst.disk_usage_gb:.0f} / {inst.disk_space_gb:.0f} GB")
        down = f"{inst.inet_down_mbps:.1f}" if inst.inet_down_mbps is not None else "—"
        up   = f"{inst.inet_up_mbps:.1f}"   if inst.inet_up_mbps is not None else "—"
        self.net_lbl.setText(f"Rede   ↓ {down} Mbps  /  ↑ {up} Mbps")

    def _apply_live_overlay(self):
        # Identical to [instance_card.py:329-351]
        d = self._live
        if "gpu_util" in d:
            t_ = f"  {d['gpu_temp']:.0f}°C" if "gpu_temp" in d else ""
            self.gpu_bar.set_value(d["gpu_util"], f"{d['gpu_util']:.0f}%{t_}")
        if "vram_used_mb" in d and d.get("vram_total_mb", 0) > 0:
            used = d["vram_used_mb"] / 1024.0
            total = d["vram_total_mb"] / 1024.0
            self.vram_bar.set_value(used / total * 100.0, f"{used:.1f} / {total:.1f} GB")
        if "ram_used_mb" in d and d.get("ram_total_mb", 0) > 0:
            used = d["ram_used_mb"] / 1024.0
            total = d["ram_total_mb"] / 1024.0
            self.ram_bar.set_value(used / total * 100.0, f"{used/total*100:.0f}% ({used:.0f} / {total:.0f} GB)")
        if "load1" in d and self.instance.cpu_cores:
            cpu_pct = min(100.0, d["load1"] / max(1, self.instance.cpu_cores) * 100.0)
            self.cpu_bar.set_value(cpu_pct, f"{cpu_pct:.0f}%")
        if "disk_used_gb" in d and d.get("disk_total_gb", 0) > 0:
            pct = d["disk_used_gb"] / d["disk_total_gb"] * 100.0
            self.disk_bar.set_value(pct, f"{d['disk_used_gb']:.0f} / {d['disk_total_gb']:.0f} GB")

    def _update_buttons(self):
        s = self.instance.state
        tun = self.tunnel_status
        # Defaults
        self.primary_btn.setVisible(True); self.primary_btn.setEnabled(True)
        self.lab_btn.setVisible(False); self.terminal_btn.setVisible(False)
        self.disconnect_btn.setVisible(False); self.deactivate_btn.setVisible(False)

        if s == InstanceState.STOPPED:
            self.primary_btn.setText("Ativar")
        elif s == InstanceState.STARTING:
            self.primary_btn.setText("Ativando…"); self.primary_btn.setEnabled(False)
            self.deactivate_btn.setVisible(True)
        elif s == InstanceState.STOPPING:
            self.primary_btn.setText("Desativando…"); self.primary_btn.setEnabled(False)
        elif s == InstanceState.RUNNING:
            self.terminal_btn.setVisible(True); self.deactivate_btn.setVisible(True)
            if tun == TunnelStatus.CONNECTED:
                self.primary_btn.setVisible(False)
                self.lab_btn.setVisible(True)
                self.disconnect_btn.setVisible(True)
            elif tun == TunnelStatus.CONNECTING:
                self.primary_btn.setText("Conectando…"); self.primary_btn.setEnabled(False)
            elif tun == TunnelStatus.FAILED:
                self.primary_btn.setText("Tentar novamente")
            else:
                self.primary_btn.setText("Conectar")
        else:
            self.primary_btn.setVisible(False)

    @staticmethod
    def _format_details(inst: Instance) -> str:
        # Identical to [instance_card.py:293-327]
        bits = []
        if inst.geolocation: bits.append(f"📍 {inst.geolocation}")
        elif inst.country:   bits.append(f"📍 {inst.country}")
        if inst.hostname:    bits.append(f"🖥 {inst.hostname}")
        elif inst.host_id:   bits.append(f"🖥 host #{inst.host_id}")
        if inst.datacenter:  bits.append(f"🏢 {inst.datacenter}")
        if inst.cpu_name:
            cores = f" ({inst.cpu_cores}c)" if inst.cpu_cores else ""
            bits.append(f"🧠 {inst.cpu_name}{cores}")
        if inst.cuda_max_good:   bits.append(f"CUDA ≤ {inst.cuda_max_good:g}")
        if inst.pcie_gen:
            pcie = f"PCIe Gen {inst.pcie_gen:g}"
            if inst.pcie_bw_gbps: pcie += f" · {inst.pcie_bw_gbps:.1f} GB/s"
            bits.append(pcie)
        if inst.disk_bw_mbps: bits.append(f"Disco {inst.disk_bw_mbps:.0f} MB/s")
        if inst.dlperf:       bits.append(f"DLPerf {inst.dlperf:.1f}")
        if inst.reliability is not None:
            r = inst.reliability * 100 if inst.reliability <= 1.0 else inst.reliability
            bits.append(f"⚡ {r:.1f}%")
        return "  ·  ".join(bits)
```

- [x] **Step 2: Commit**

```bash
git add app/ui/views/instance_card.py
git commit -m "feat(view): redesigned InstanceCard on the new design system"
```

---

### Task 2.4: Failing test for InstancesView

**Files:**
- Create: `tests/test_instances_view.py`

- [x] **Step 1: Write the test**

```python
# tests/test_instances_view.py
"""The Instances view renders one InstanceCard per instance emitted by the
controller, handles empty state, and relays card signals to controller methods."""
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication
from app.ui.views.instances_view import InstancesView
from app.models import AppConfig, Instance, InstanceState, UserInfo


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _inst(iid, state=InstanceState.RUNNING):
    return Instance(
        id=iid, label=f"#{iid}", state=state, gpu_name="RTX 3090",
        num_gpus=1, gpu_ram_gb=24, image="img", dph=0.5,
    )


def test_empty_state_shown_initially(qapp):
    ctl = MagicMock(last_instances=[], last_user=None, config=AppConfig(),
                    tunnel_states={})
    v = InstancesView(ctl)
    assert v.empty_lbl.isVisible()


def test_renders_cards_on_refresh(qapp):
    ctl = MagicMock(last_instances=[], last_user=None, config=AppConfig(),
                    tunnel_states={})
    v = InstancesView(ctl)
    v.handle_refresh([_inst(1), _inst(2)], UserInfo(balance=5.0, email=""))
    assert len(v.cards) == 2
    assert not v.empty_lbl.isVisible()


def test_card_activate_calls_controller(qapp):
    ctl = MagicMock(last_instances=[], last_user=None, config=AppConfig(),
                    tunnel_states={})
    v = InstancesView(ctl)
    v.handle_refresh([_inst(1, state=InstanceState.STOPPED)],
                     UserInfo(balance=5.0, email=""))
    v.cards[1].activate_requested.emit(1)
    ctl.activate.assert_called_once_with(1)
```

- [x] **Step 2: Run test to verify failure**

Run: `pytest tests/test_instances_view.py -v`
Expected: FAIL (module missing)

- [x] **Step 3: Commit**

```bash
git add tests/test_instances_view.py
git commit -m "test: failing InstancesView contract"
```

---

### Task 2.5: Implement InstancesView

**Files:**
- Create: `app/ui/views/instances_view.py`

- [x] **Step 1: Write the view**

```python
# app/ui/views/instances_view.py
"""The Instances view — landing page. Billing strip on top, one InstanceCard
per Vast.ai instance, and a console drawer at the bottom. Consumes signals
from AppController directly."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox,
)
from app import theme as t
from app.controller import AppController
from app.models import Instance, InstanceState, TunnelStatus, UserInfo
from app.ui.components.primitives import SectionHeader
from app.ui.views.billing_strip import BillingStrip
from app.ui.views.console_drawer import ConsoleDrawer
from app.ui.views.instance_card import InstanceCard


class InstancesView(QWidget):
    open_lab_requested = Signal(int)  # iid — propagates to shell to switch tabs
    open_settings_requested = Signal()

    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.cards: dict[int, InstanceCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        # Header row: title + counts + refresh controls
        head = QHBoxLayout()
        head.addWidget(SectionHeader("CLOUD", "Minhas Instâncias"))
        head.addStretch()
        self.active_lbl = QLabel("0 ativas"); self.active_lbl.setProperty("role", "muted")
        head.addWidget(self.active_lbl)

        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["↺ 5s", "↺ 10s", "↺ 30s", "↺ 60s", "↺ off"])
        idx_map = {5: 0, 10: 1, 30: 2, 60: 3, 0: 4}
        self.interval_combo.setCurrentIndex(
            idx_map.get(controller.config.refresh_interval_seconds, 2))
        self.interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        head.addWidget(self.interval_combo)

        self.refresh_btn = QPushButton("Atualizar")
        self.refresh_btn.setProperty("variant", "ghost")
        self.refresh_btn.clicked.connect(controller.request_refresh)
        head.addWidget(self.refresh_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setProperty("variant", "ghost")
        self.settings_btn.setFixedWidth(42)
        self.settings_btn.clicked.connect(self.open_settings_requested)
        head.addWidget(self.settings_btn)
        root.addLayout(head)

        # Billing strip
        self.billing = BillingStrip(controller.config)
        root.addWidget(self.billing)

        # Instance list scroll area
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0); self.list_layout.setSpacing(t.SPACE_3)
        self.empty_lbl = QLabel("Conecte sua API key para ver suas instâncias.")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setProperty("role", "muted")
        self.empty_lbl.setStyleSheet(
            f"padding: 80px 0; font-size: 12pt; color: {t.TEXT_MID};"
        )
        self.list_layout.addWidget(self.empty_lbl)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        # Console drawer
        self.console = ConsoleDrawer()
        root.addWidget(self.console)

        # Controller wiring
        controller.instances_refreshed.connect(self.handle_refresh)
        controller.tunnel_status_changed.connect(self._on_tunnel_status)
        controller.live_metrics.connect(self._on_live_metrics)
        controller.model_changed.connect(self._on_model_changed)
        controller.log_line.connect(self.console.log)

    # ---- Refresh ----
    def handle_refresh(self, instances: list[Instance], user):
        self._rebuild_cards(instances)
        self.billing.update_values(user, instances, self.controller.today_spend())
        active = sum(1 for i in instances if i.state == InstanceState.RUNNING)
        self.active_lbl.setText(f"{active} ativa" if active == 1 else f"{active} ativas")

    def _rebuild_cards(self, instances: list[Instance]):
        current = {i.id for i in instances}
        for iid in list(self.cards.keys()):
            if iid not in current:
                card = self.cards.pop(iid)
                self.list_layout.removeWidget(card); card.setParent(None); card.deleteLater()

        self.empty_lbl.setVisible(not instances)
        for inst in instances:
            tun = self.controller.tunnel_states.get(inst.id, TunnelStatus.DISCONNECTED)
            if inst.id in self.cards:
                self.cards[inst.id].update_from(inst, tun, self.controller.config.default_tunnel_port)
            else:
                c = InstanceCard(inst)
                c.activate_requested.connect(self.controller.activate)
                c.deactivate_requested.connect(self._confirm_deactivate)
                c.reconnect_requested.connect(self.controller.connect_tunnel)
                c.disconnect_requested.connect(self.controller.disconnect_tunnel)
                c.open_terminal_requested.connect(self._on_open_terminal)
                c.open_lab_requested.connect(self.open_lab_requested)
                c.copy_endpoint_requested.connect(self._on_copy_endpoint)
                c.update_from(inst, tun, self.controller.config.default_tunnel_port)
                insert_at = max(0, self.list_layout.count() - 1)
                self.list_layout.insertWidget(insert_at, c)
                self.cards[inst.id] = c

    # ---- Per-card event relays ----
    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        inst = next((i for i in self.controller.last_instances if i.id == iid), None)
        card = self.cards.get(iid)
        if card and inst:
            card.update_from(inst, TunnelStatus(status),
                             self.controller.config.default_tunnel_port)

    def _on_live_metrics(self, iid: int, d: dict):
        card = self.cards.get(iid)
        if card is not None:
            card.set_live_metrics(d)

    def _on_model_changed(self, iid: int, model_id: str):
        card = self.cards.get(iid)
        if card is not None:
            card.set_loaded_model(model_id or None)

    # ---- Commands ----
    def _confirm_deactivate(self, iid: int):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Desativar instância",
            "Tem certeza? A máquina será parada e a conexão encerrada.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.controller.deactivate(iid)

    def _on_open_terminal(self, iid: int):
        inst = next((i for i in self.controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            self.console.log(f"Terminal indisponível para #{iid}")
            return
        try:
            self.controller.ssh.open_terminal(
                inst.ssh_host, inst.ssh_port,
                self.controller.config.terminal_preference,
            )
            self.console.log(f"Terminal aberto para {inst.ssh_host}:{inst.ssh_port}")
        except Exception as e:
            self.console.log(f"Falha ao abrir terminal: {e}")

    def _on_copy_endpoint(self, iid: int):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(
            f"http://127.0.0.1:{self.controller.config.default_tunnel_port}")
        self.console.log("Endereço copiado.")

    def _on_interval_changed(self, idx: int):
        mapping = {0: 5, 1: 10, 2: 30, 3: 60, 4: 0}
        self.controller.config.refresh_interval_seconds = mapping[idx]
        self.controller.config_store.save(self.controller.config)
        self.controller._apply_interval()
```

- [x] **Step 2: Run tests to verify pass**

Run: `pytest tests/test_instances_view.py -v`
Expected: PASS

- [x] **Step 3: Commit**

```bash
git add app/ui/views/instances_view.py
git commit -m "feat(view): InstancesView — landing page with billing + cards + console"
```

---

# Phase 3 — AppShell: unify Lab shell and Instances view

Goal: the old `LabShell` now also hosts the Instances view. No top toggle bar yet — we add the nav item and keep MainWindow running.

---

### Task 3.1: Add InstancesView to LabShell

**Files:**
- Modify: `app/lab/shell.py`

- [x] **Step 1: Import and register the view**

At the top of `shell.py`, add:

```python
from app.controller import AppController
from app.ui.views.instances_view import InstancesView
```

In `LabShell.__init__`, **before** `self._switch("dashboard")`:

```python
# Instances is now the default landing view. It needs an AppController —
# MainWindow will inject one via `attach_controller()` during Phase 4.
# Until then the view is constructed lazily when the controller arrives.
self._controller: AppController | None = None
# NOTE: InstancesView is added to the stack by attach_controller().
```

Add a new method:

```python
def attach_controller(self, controller: AppController):
    """Wire the app controller into the shell. Builds and registers the
    Instances view. Idempotent."""
    if self._controller is not None:
        return
    self._controller = controller
    self.instances = InstancesView(controller, self)
    self._add_view("instances", self.instances)
    self.instances.open_lab_requested.connect(self._on_open_lab_from_card)
    self.instances.open_settings_requested.connect(
        lambda: self.parent() and self.parent().open_settings())
    # Make Instances the landing view
    self._switch("instances")
    self.nav.set_active("instances")

def _on_open_lab_from_card(self, iid: int):
    """User clicked "Abrir no Lab" on an instance card. Select the instance
    and jump to Dashboard."""
    inst = next((i for i in self._controller.last_instances if i.id == iid), None)
    if not inst:
        return
    self.select_instance(iid, inst.gpu_name or "",
                          inst.ssh_host or "", inst.ssh_port or 0)
    self._go("dashboard")
```

- [x] **Step 2: Commit**

```bash
git add app/lab/shell.py
git commit -m "feat(lab-shell): attach_controller wires InstancesView + open-from-card"
```

---

### Task 3.2: MainWindow hands the controller to LabShell

**Files:**
- Modify: `app/ui/main_window.py`

- [x] **Step 1: After constructing `self.lab_shell`, call `attach_controller`**

```python
# in _build_ui, right after self.lab_shell = LabShell(...)
self.lab_shell.attach_controller(self.controller)
```

- [x] **Step 2: Expose `open_settings` on MainWindow for the shell to call**

```python
def open_settings(self):
    self._open_settings()
```

- [x] **Step 3: Manual verify**

Run: `python main.py`
Expected:
- App launches.
- Click the "Lab" button in the top bar.
- Sidebar now has 6 items; "Instances" is active and shows the new landing view with billing strip + instance cards + console at the bottom.
- All instance actions work (same wiring as Cloud view).
- "Abrir no Lab" on a card jumps to Dashboard with that instance selected.

- [x] **Step 4: Commit**

```bash
git add app/ui/main_window.py
git commit -m "feat(main-window): pass AppController to LabShell"
```

---

# Phase 4 — Retire the top tab bar: Lab becomes the whole app

Goal: remove the Cloud/Lab toggle. `MainWindow` collapses to a thin shell that hosts `AppShell`. Any remaining Cloud-only UI is deleted.

---

### Task 4.1: Rename LabShell to AppShell (location + class)

**Files:**
- Create: `app/ui/app_shell.py` (copy of lab/shell.py, with class renamed to `AppShell`)
- Modify: `app/lab/shell.py` → re-export shim

- [x] **Step 1: Copy `app/lab/shell.py` to `app/ui/app_shell.py`, rename the class**

Change at the top of the new file:
- `class LabShell(QWidget):` → `class AppShell(QWidget):`
- `self.setObjectName("lab-shell")` → `self.setObjectName("app-shell")`

- [x] **Step 2: Update `app/lab/shell.py` to re-export**

```python
# app/lab/shell.py
"""Compatibility re-export. Deleted at end of Phase 8."""
from app.ui.app_shell import AppShell as LabShell  # noqa: F401
```

- [x] **Step 3: Manual verify — app still runs**

Run: `python main.py`
Expected: no visible change.

- [x] **Step 4: Commit**

```bash
git add app/ui/app_shell.py app/lab/shell.py
git commit -m "refactor: rename LabShell → AppShell; relocate to app/ui/"
```

---

### Task 4.2: Delete the top toggle bar in MainWindow

**Files:**
- Modify: `app/ui/main_window.py`

- [x] **Step 1: Rewrite `_build_ui` to host only `AppShell`**

Replace the entire method body with:

```python
def _build_ui(self):
    from app.ui.app_shell import AppShell
    self.shell = AppShell(self.config, self.config_store, self.controller.ssh, self)
    self.shell.attach_controller(self.controller)
    self.setCentralWidget(self.shell)
```

Delete:
- `self.toggle_cloud_btn`, `self.toggle_lab_btn`, `toggle_bar`, `_switch_workspace`
- `self.workspace_stack`, `self.cloud_body`, `self.billing`, `self.list_container`, `self.scroll`, `self.log`, `self.refresh_interval_combo`, `self.manual_refresh_btn`, `self.settings_btn`, `self.empty_lbl`, `self.active_lbl`, `self.refresh_timer` (now on controller)
- `_rebuild_cards`, `_on_refreshed` (now on InstancesView), `_on_refresh_failed` → still useful for Toast; keep the Toast branch and forward to shell
- `_on_interval_changed`, `_on_manual_refresh`, `_on_deploy_status`, `_start_llama_probe`, `_stop_llama_probe`, `_on_llama_progress`, `_on_llama_ready`, `_on_llama_failed`, `_on_copy_endpoint`, `_start_tunnel_for`, `_on_tunnel_status`, `_refresh_card`, `_check_tunnels_health`, `_can_ssh_silently`, `_sync_live_workers`, `_start_live_metrics`, `_stop_live_metrics`, `_start_model_watcher`, `_stop_model_watcher`, `_on_live_metrics`, `_on_model_changed`, `_on_manage_models`, `_on_activate`, `_on_deactivate`, `_on_reconnect`, `_on_disconnect`, `_on_open_terminal`, `_find_instance`, `_on_action_done`, `_trigger_*` — all moved to AppController or InstancesView.

Keep only:
- `__init__` (simplified)
- `_build_ui`
- `open_settings()` + `_open_settings()`, `_on_settings_saved()` (delegates to controller.apply_config)
- `_prompt_passphrase()` (the passphrase dialog — controller emits `passphrase_needed`)
- `resizeEvent()` (for toasts)
- `closeEvent()` (calls `controller.shutdown()`)

The new file should be ~100 lines instead of ~675.

- [x] **Step 2: Route Toasts via a signal from AppController**

Add to AppController:

```python
toast_requested = Signal(str, str, int)  # message, level, duration_ms
```

In `_on_refresh_failed` and other places where Toast was shown, `controller.toast_requested.emit(...)`. In MainWindow:

```python
self.controller.toast_requested.connect(lambda m, k, d: Toast(self.shell, m, k, d))
```

- [x] **Step 3: Manual verify — full regression**

Run: `python main.py`
Expected:
- App launches directly into the Instances view (no top tabs).
- Sidebar has 6 items.
- Refresh, activate, deactivate, connect tunnel, disconnect, terminal, copy endpoint, settings, open-in-lab — all work.
- Console drawer shows log lines.
- Toasts still appear on the shell.

- [x] **Step 4: Commit**

```bash
git add app/ui/main_window.py app/controller.py
git commit -m "feat(main-window): remove top tab bar — AppShell is the whole app"
```

---

### Task 4.3: Delete obsolete Cloud-era UI files

**Files:**
- Delete: `app/ui/billing_header.py`
- Delete: `app/ui/instance_card.py`
- Delete: `app/ui/log_panel.py`
- Delete: `app/ui/metric_bar.py`
- Delete: `app/ui/model_manager_dialog.py`
- Delete: `app/lab/components/primitives.py` (shim no longer needed)
- Delete: `app/lab/components/nav_rail.py` (shim no longer needed)

- [x] **Step 1: grep for importers first**

Run: `grep -rn "from app.ui.billing_header\|from app.ui.instance_card\|from app.ui.log_panel\|from app.ui.metric_bar\|from app.ui.model_manager_dialog\|from app.lab.components" app tests`
Expected: no hits after Phase 4 Task 2 (if any remain, clean them up inline).

- [x] **Step 2: Delete files**

```bash
git rm app/ui/billing_header.py app/ui/instance_card.py app/ui/log_panel.py \
       app/ui/metric_bar.py app/ui/model_manager_dialog.py \
       app/lab/components/primitives.py app/lab/components/nav_rail.py
```

- [x] **Step 3: Run tests + launch**

Run: `pytest -q && python main.py`
Expected: tests pass; app launches normally.

- [x] **Step 4: Commit**

```bash
git commit -m "chore: delete obsolete Cloud UI modules (replaced by app/ui/views)"
```

---

# Phase 5 — Settings dialog and Toast restyle

Goal: re-render settings + toast in the unified design system. Behavior unchanged.

---

### Task 5.1: SettingsDialog restyle

**Files:**
- Modify: `app/ui/settings_dialog.py`

- [x] **Step 1: Replace the header block + status-color calls**

At the top of `__init__`, replace:

```python
title = QLabel("Configurações")
title.setObjectName("h1")
lay.addWidget(title)
subtitle = QLabel(...)
subtitle.setObjectName("secondary")
```

with:

```python
from app.ui.components.primitives import SectionHeader
lay.addWidget(SectionHeader("PREFERÊNCIAS", "Configurações"))
subtitle = QLabel("A API key é salva em %USERPROFILE%\\.vastai-app\\config.json")
subtitle.setProperty("role", "muted")
lay.addWidget(subtitle)
```

In `_on_test`, replace `theme.WARNING`/`theme.SUCCESS`/`theme.DANGER`/`theme.TEXT_SECONDARY` with `theme.WARN` / `theme.OK` / `theme.ERR` / `theme.TEXT_MID`.

Replace `self.save_btn` / `cancel_btn` / `test_btn` styling — `cancel_btn` and `test_btn` should be ghost buttons:

```python
self.test_btn.setProperty("variant", "ghost")
self.cancel_btn.setProperty("variant", "ghost")
# save_btn keeps default accent
```

Remove any remaining `setObjectName("secondary")` — not needed under the new stylesheet.

- [x] **Step 2: Manual verify**

Run `python main.py`, open Settings — form renders in dark dashboard style, all controls still work. Save a config change, verify it persists.

- [x] **Step 3: Commit**

```bash
git add app/ui/settings_dialog.py
git commit -m "feat(settings): restyle dialog on unified design system"
```

---

### Task 5.2: Toast restyle

**Files:**
- Modify: `app/ui/toast.py`

- [x] **Step 1: Update palette references and visuals**

```python
# app/ui/toast.py
from __future__ import annotations
from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtCore import Qt, QTimer
from app import theme as t


class Toast(QLabel):
    COLORS = {
        "info":    t.INFO,
        "success": t.OK,
        "warning": t.WARN,
        "error":   t.ERR,
    }
    _stack: list["Toast"] = []

    def __init__(self, parent: QWidget, message: str, kind: str = "info",
                 duration_ms: int = 3000):
        super().__init__(parent)
        self.setText(message); self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        color = self.COLORS.get(kind, t.INFO)
        self.setStyleSheet(
            f"QLabel {{ background-color: {t.SURFACE_2}; color: {t.TEXT_HI};"
            f" border: 1px solid {t.BORDER_MED}; border-left: 3px solid {color};"
            f" border-radius: {t.RADIUS_MD}px; padding: 12px 16px;"
            f" font-weight: 500; }}"
        )
        self.setFixedWidth(340); self.adjustSize()
        Toast._stack.append(self); self._reposition_stack()
        self.show(); self.raise_()
        QTimer.singleShot(duration_ms, self._close)

    def mousePressEvent(self, _e):
        self._close()

    def _close(self):
        if self in Toast._stack:
            Toast._stack.remove(self)
        self.close(); self._reposition_stack()

    def _reposition_stack(self):
        parent = self.parent()
        if parent is None: return
        margin = 20; y = parent.height() - margin
        for tw in reversed(Toast._stack):
            y -= tw.height() + 8
            x = parent.width() - tw.width() - margin
            tw.move(x, y)
```

- [x] **Step 2: Manual verify** — trigger a toast (e.g. manual refresh fail with bad API key) and confirm it renders with the new look.

- [x] **Step 3: Commit**

```bash
git add app/ui/toast.py
git commit -m "feat(toast): restyle on unified design system"
```

---

# Phase 6 — UX polish pass

Goal: small, high-impact refinements that elevate the result from "it works" to "professional".

---

### Task 6.1: Keyboard shortcuts and focus

**Files:**
- Modify: `app/ui/app_shell.py`

- [x] **Step 1: Add a shell-level QShortcut for Ctrl+R (refresh) and Ctrl+, (settings)**

```python
from PySide6.QtGui import QShortcut, QKeySequence
# in AppShell.__init__, at the end:
QShortcut(QKeySequence("Ctrl+R"), self,
          activated=lambda: self._controller and self._controller.request_refresh())
QShortcut(QKeySequence("Ctrl+,"), self,
          activated=lambda: self.window().open_settings()
                             if hasattr(self.window(), "open_settings") else None)
```

- [x] **Step 2: Commit**

```bash
git add app/ui/app_shell.py
git commit -m "feat(ux): Ctrl+R refresh and Ctrl+, settings shortcuts"
```

---

### Task 6.2: Empty state for Instances view when API key missing

**Files:**
- Modify: `app/ui/views/instances_view.py`

- [x] **Step 1: Detect no-key case and show actionable empty state**

Replace the current `empty_lbl` setup with:

```python
from PySide6.QtWidgets import QVBoxLayout
self.empty_card = GlassCard()
from app.ui.components.primitives import GlassCard, SectionHeader
self.empty_card.body().addWidget(SectionHeader("COMEÇAR", "Configure sua API key"))
hint = QLabel("Cole sua Vast.ai API key em Configurações para começar a ver suas instâncias.")
hint.setWordWrap(True); hint.setProperty("role", "muted")
self.empty_card.body().addWidget(hint)
go_btn = QPushButton("Abrir Configurações")
go_btn.clicked.connect(self.open_settings_requested)
self.empty_card.body().addWidget(go_btn)
self.list_layout.addWidget(self.empty_card)
```

Toggle its visibility the same way as `empty_lbl` — show when `not instances and not controller.config.api_key`; show a simpler "0 instances" plain label when key is set but list is empty.

- [x] **Step 2: Manual verify** — start with empty config → card with "Open Settings" renders. Save a key → cards appear.

- [x] **Step 3: Commit**

```bash
git add app/ui/views/instances_view.py
git commit -m "feat(ux): actionable empty state on Instances view"
```

---

### Task 6.3: Window title and icon

**Files:**
- Modify: `app/ui/main_window.py`, `main.py`

- [x] **Step 1: Update window title to reflect the unified app**

In MainWindow: `self.setWindowTitle("Vast.ai Manager")` (unchanged) and ensure the default size is appropriate for the wider nav rail layout:

```python
self.resize(1240, 820)
```

- [x] **Step 2: Commit**

```bash
git add app/ui/main_window.py
git commit -m "chore: default window size accommodates nav rail + wide cards"
```

---

# Phase 7 — Test sweep and final cleanup

Goal: ensure the suite is green, dead code is gone, imports are tidy.

---

### Task 7.1: Run the full test suite

- [x] **Step 1: Run**

Run: `pytest -q`
Expected: all tests pass.

- [x] **Step 2: If any test references `app.ui.instance_card`, `app.ui.billing_header`, `app.ui.log_panel`, or `app.ui.model_manager_dialog`, update or delete it.**

Search: `grep -rn "billing_header\|instance_card\|log_panel\|metric_bar\|model_manager_dialog" tests`

Update imports to new paths (`app.ui.views.*`) or delete tests that only validated deleted widgets.

- [x] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: update imports to new app/ui/views layout"
```

---

### Task 7.2: Delete compatibility shims

**Files:**
- Delete: `app/lab/theme.py`
- Delete: `app/lab/shell.py`
- Delete: `app/lab/components/` directory (if empty)

- [x] **Step 1: grep for any remaining `from app.lab.theme`, `from app.lab.shell`, `from app.lab.components` outside of the deleted shims themselves**

Run: `grep -rn "from app\.lab\.theme\|from app\.lab\.shell\|from app\.lab\.components" app`
Expected: only inside `app/lab/*` itself.

- [x] **Step 2: Delete shims**

```bash
git rm app/lab/theme.py app/lab/shell.py
git rm -r app/lab/components/ 2>/dev/null || true
```

- [x] **Step 3: Run tests + app**

Run: `pytest -q && python main.py`
Expected: tests pass; app still launches.

- [x] **Step 4: Commit**

```bash
git commit -m "chore: drop compatibility shims; app.lab now exposes only lab domain code"
```

---

### Task 7.3: Final manual walkthrough checklist

- [x] **Step 1: Execute the full checklist**

- [ ] App launches directly to Instances view
- [ ] Billing strip shows balance, burn rate, autonomy, today spend, projection (when applicable)
- [ ] Instance cards render for every live instance
- [ ] Activate/deactivate/connect/disconnect/terminal work
- [ ] "Abrir no Lab" on a connected card jumps to Lab Dashboard with that instance selected
- [ ] Dashboard → Discover → Models → Configure → Monitor all still work and are scoped to the selected instance
- [ ] Console drawer toggles, clears, receives all controller log lines
- [ ] Settings dialog opens, tests API key, saves
- [ ] Toasts appear with the new design
- [ ] Ctrl+R triggers refresh; Ctrl+, opens settings
- [ ] Closing the window terminates all workers cleanly (no hung Python process)
- [ ] `python main.py` on a fresh `~/.vastai-app/config.json` opens settings first

- [x] **Step 2: Record any deferred issues in `docs/superpowers/plans/` as follow-ups**

If any gotchas surface that weren't in scope, create `docs/superpowers/plans/2026-04-16-lab-migration-followups.md` with a bulleted list. Do not fix them as part of this migration.

- [x] **Step 3: Tag the milestone**

```bash
git tag v2.0-lab-primary
git commit --allow-empty -m "milestone: Lab is now the primary app"
```

---

## Phase Summary

| Phase | Deliverable | Risk |
|-------|-------------|------|
| 0 | Unified design system, primitives moved | Low — re-export shims preserve imports |
| 1 | `AppController` extracts worker ownership | Medium — lots of state moving |
| 2 | Instances view + redesigned card/billing/console | Medium — visual port, behavior parity tests |
| 3 | LabShell registers InstancesView | Low |
| 4 | Kill top tab bar; collapse MainWindow | High — biggest shell change; relies on Phase 1 being solid |
| 5 | Settings + Toast restyle | Low |
| 6 | Polish (shortcuts, empty states) | Low |
| 7 | Tests + cleanup | Low |

**Commit after every task.** If a task exposes something the plan didn't anticipate, stop and add a task rather than widening scope in-place.

---

## Verification gates (read before starting each phase)

- **Phase 0 → 1:** `pytest tests/test_theme_tokens.py` passes AND `python main.py` launches.
- **Phase 1 → 2:** `pytest tests/test_controller.py` passes AND every Cloud action still works through the controller.
- **Phase 2 → 3:** `pytest tests/test_instances_view.py tests/test_billing_strip.py` passes.
- **Phase 3 → 4:** Top-bar "Lab" button shows a fully-wired Instances view that mirrors the Cloud view exactly.
- **Phase 4 → 5:** App launches with **no** top tab bar; every Phase 3 behavior is intact.
- **Phase 5 → 6:** Settings and Toast visibly adopt the new palette.
- **Phase 6 → 7:** Shortcuts work; empty state has an "Open Settings" button.
- **Phase 7 complete:** Full manual checklist passes.
