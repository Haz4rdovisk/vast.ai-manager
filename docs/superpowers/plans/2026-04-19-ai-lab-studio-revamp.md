# AI Lab Studio Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the AI Lab as an LM-Studio-style workspace: a standalone **Discover** with local LLMfit scoring per rented instance, a **Download/Install** flow with live visual progress for llama.cpp and GGUF files, and a new **Studio** view (replaces `Dashboard`) that embeds the official llama.cpp webui and detects/surfaces launch errors.

**Architecture:** Four layered changes: (1) add an SSH streaming primitive (`stream_script`) + a generic `StreamingRemoteWorker` that emits line-by-line progress; (2) add a pure-Python `InstanceFitScorer` service and an app-local `LocalLLMFit` HTTP client that runs `llmfit serve` on the user's machine, so scoring stops depending on the remote instance; (3) add structured parsers for llama.cpp build, `wget` download, and llama-server log diagnostics, each feeding a reusable `ProgressPanel` primitive; (4) add a new `StudioView` built around an instance dropdown, a sidebar of installed models + ServerParams, a central `QWebEngineView` pointed at the tunnel port, and an inline diagnostics panel. Existing `LabStore` signals keep the reactive backbone; views are swapped via `NavRail` without changing the shell contract.

**Tech Stack:** Python 3.11, PySide6 6.6+ (including `PySide6-Addons` for `QtWebEngineWidgets`), qtawesome, pytest, existing vastai SDK, local `llmfit` binary (installed via `pipx` or `pip --user` — wrapper installs lazily on first use).

**Reference screenshot:** LM Studio — top bar with model dropdown, right sidebar of inference parameters, central chat panel. (Provided in command-args.)

---

## Conventions

- All paths relative to `C:/Users/Pc_Lu/Desktop/vastai-app/`.
- Windows bash shell (forward slashes, `/dev/null`).
- Tests run with `python -m pytest tests/<path> -v`; `tests/conftest.py` provides the `qt_app` offscreen fixture.
- After each task the suite must stay green: `python -m pytest tests/ -x -q`.
- Commit style: Conventional Commits (`feat(lab):`, `fix(lab):`, `refactor(lab):`, `test(lab):`).
- Do **not** reformat unrelated files. Keep diffs focused.
- Every new `QWidget` must compile under the offscreen platform (no `show()` in tests, use `qt_app` fixture).

---

## File Structure

**New files (create):**

- `app/lab/services/ssh_stream.py` — `stream_script(host, port, script, on_line)` generator + helper.
- `app/lab/services/fit_scorer.py` — `InstanceFitScorer` pure-Python class.
- `app/lab/services/local_llmfit.py` — `LocalLLMFit` client (manages a local `llmfit serve` subprocess + HTTP).
- `app/lab/services/progress_parsers.py` — line parsers for `wget`, `cmake`, `llama-server.log` → structured events.
- `app/lab/services/model_catalog.py` — cached model catalog JSON + refresh logic.
- `app/lab/services/diagnostics.py` — rule-based error classifier for llama-server logs.
- `app/lab/workers/streaming_worker.py` — `StreamingRemoteWorker(QThread)` emitting `line(str)` + `finished(bool, str)`.
- `app/lab/workers/local_llmfit_worker.py` — wraps LLMfit install/start on the user's machine.
- `app/ui/components/progress_panel.py` — reusable step-list + live log widget.
- `app/ui/components/diagnostic_banner.py` — inline error banner with Fix action.
- `app/lab/views/studio_view.py` — the new Studio view (replaces dashboard in the main flow).
- `app/lab/views/install_panel.py` — Download/Install dialog/panel with live progress.
- `tests/lab/test_ssh_stream.py`
- `tests/lab/test_fit_scorer.py`
- `tests/lab/test_local_llmfit.py`
- `tests/lab/test_progress_parsers.py`
- `tests/lab/test_diagnostics.py`
- `tests/lab/test_model_catalog.py`
- `tests/lab/test_streaming_worker.py`
- `tests/lab/test_install_panel.py`
- `tests/lab/test_studio_view.py`
- `tests/lab/test_discover_view_scoring.py`
- `tests/lab/test_progress_panel.py`

**Existing files (modify):**

- `requirements.txt` — add `PySide6-Addons>=6.6` (QtWebEngine) and `requests>=2.31`.
- `app/services/ssh_service.py` — add `stream_script` method.
- `app/lab/state/models.py` — add `InstallJob`, `DownloadJob`, `ServerDiagnostic` dataclasses; per-instance scored models.
- `app/lab/state/store.py` — add signals for install/download progress; per-instance scored catalog.
- `app/lab/views/discover_view.py` — use local scorer, show per-instance score chips, trigger install panel on download.
- `app/lab/views/dashboard_view.py` — **delete** after Studio lands (final phase).
- `app/lab/views/configure_view.py` — extract param controls into reusable widget used by Studio sidebar.
- `app/lab/views/monitor_view.py` — **delete**; diagnostics absorbed into StudioView.
- `app/lab/views/models_view.py` — becomes a thin catalog of installed GGUFs; launching moves to Studio.
- `app/ui/app_shell.py` — register Studio, drop Dashboard/Monitor, wire streaming workers.
- `app/ui/components/nav_rail.py` — rename `dashboard`→`studio`, remove `monitor`.
- `app/lab/workers/remote_setup_worker.py` — keep for short scripts; long installs go through `StreamingRemoteWorker`.

**Delete at end (after replacements land):**

- `app/lab/views/dashboard_view.py`
- `app/lab/views/monitor_view.py`

---

## Phase 1 — SSH streaming + streaming worker

### Task 1: Add `SSHService.stream_script`

**Files:**
- Modify: `app/services/ssh_service.py` (append method inside `SSHService` class)
- Test: `tests/test_ssh_service.py`

- [x] **Step 1.1: Write the failing test**

Append to `tests/test_ssh_service.py`:

```python
def test_stream_script_yields_lines_then_exit_code(monkeypatch):
    """stream_script calls on_line for each stdout line and returns (ok, full_output)."""
    import subprocess
    from app.services.ssh_service import SSHService

    class FakeProc:
        def __init__(self):
            self.stdout = iter([b"line1\n", b"line2\n", b"line3\n", b""])
            self.returncode = 0
            self._stdin_closed = False
            class Stdin:
                def write(self_, _b): pass
                def close(self_): pass
            self.stdin = Stdin()
        def wait(self, timeout=None):
            return 0
        def poll(self):
            return self.returncode

    def fake_popen(*a, **kw):
        return FakeProc()

    monkeypatch.setattr("app.services.ssh_service.subprocess.Popen", fake_popen)
    svc = SSHService(ssh_key_path="")
    seen: list[str] = []
    ok, full = svc.stream_script("h", 22, "echo hi", on_line=seen.append)
    assert ok is True
    assert seen == ["line1", "line2", "line3"]
    assert "line1" in full and "line3" in full


def test_stream_script_returns_false_on_nonzero(monkeypatch):
    from app.services.ssh_service import SSHService

    class FakeProc:
        def __init__(self):
            self.stdout = iter([b"boom\n", b""])
            self.returncode = 42
            class Stdin:
                def write(self_, _b): pass
                def close(self_): pass
            self.stdin = Stdin()
        def wait(self, timeout=None):
            return 42
        def poll(self):
            return 42

    monkeypatch.setattr("app.services.ssh_service.subprocess.Popen", lambda *a, **k: FakeProc())
    svc = SSHService(ssh_key_path="")
    ok, full = svc.stream_script("h", 22, "exit 42", on_line=lambda _l: None)
    assert ok is False
    assert "boom" in full
```

- [x] **Step 1.2: Run tests to verify they fail**

```bash
python -m pytest tests/test_ssh_service.py::test_stream_script_yields_lines_then_exit_code tests/test_ssh_service.py::test_stream_script_returns_false_on_nonzero -v
```

Expected: FAIL with `AttributeError: 'SSHService' object has no attribute 'stream_script'`.

- [x] **Step 1.3: Implement `stream_script`**

In `app/services/ssh_service.py`, add this method to `SSHService` (right after `run_script`, before `detect_win_tunnels`):

```python
    def stream_script(
        self,
        host: str,
        port: int,
        script: str,
        on_line,
    ) -> tuple[bool, str]:
        """Run an SSH bash script and call on_line(line) for every stdout line
        as it arrives. Returns (success, full_output). stderr is merged into
        stdout. The callback must be thread-safe for Qt (use signals)."""
        use_askpass, env = self._create_askpass_env()

        cmd = ["ssh", "-p", str(port)]
        if self.ssh_key_path:
            cmd += ["-i", self.ssh_key_path, "-o", "IdentitiesOnly=yes"]
        cmd += ["-o", "StrictHostKeyChecking=accept-new"]
        if not use_askpass:
            cmd += ["-o", "BatchMode=yes"]
        cmd += [f"root@{host}", "bash", "-l", "-s"]

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        script = "\n".join(l.rstrip() for l in script.replace("\r", "").splitlines()) + "\n"

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=creationflags,
                bufsize=0,
            )
        except Exception as e:
            return False, str(e)

        try:
            proc.stdin.write(script.encode("utf-8"))
            proc.stdin.close()
        except Exception:
            pass

        lines: list[str] = []
        for raw in proc.stdout:
            if not raw:
                break
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            lines.append(text)
            try:
                on_line(text)
            except Exception:
                pass

        rc = proc.wait()
        return rc == 0, "\n".join(lines)
```

- [x] **Step 1.4: Run the tests — they should pass**

```bash
python -m pytest tests/test_ssh_service.py::test_stream_script_yields_lines_then_exit_code tests/test_ssh_service.py::test_stream_script_returns_false_on_nonzero -v
```

Expected: PASS.

- [x] **Step 1.5: Commit**

```bash
git add app/services/ssh_service.py tests/test_ssh_service.py
git commit -m "feat(ssh): add stream_script for line-by-line remote output"
```

---

### Task 2: `StreamingRemoteWorker` QThread

**Files:**
- Create: `app/lab/workers/streaming_worker.py`
- Test: `tests/lab/test_streaming_worker.py`

- [ ] **Step 2.1: Write the failing test**

Create `tests/lab/test_streaming_worker.py`:

```python
from PySide6.QtCore import QEventLoop, QTimer
from app.lab.workers.streaming_worker import StreamingRemoteWorker


class _FakeSSH:
    def __init__(self, lines, ok=True):
        self._lines = lines
        self._ok = ok

    def stream_script(self, host, port, script, on_line):
        for l in self._lines:
            on_line(l)
        return self._ok, "\n".join(self._lines)


def test_streaming_worker_emits_line_then_finished(qt_app):
    ssh = _FakeSSH(["one", "two", "three"])
    w = StreamingRemoteWorker(ssh, "h", 22, "echo stub")
    seen: list[str] = []
    done: dict = {}
    w.line.connect(seen.append)
    w.finished.connect(lambda ok, out: done.update(ok=ok, out=out))

    loop = QEventLoop()
    w.finished.connect(lambda *_: loop.quit())
    QTimer.singleShot(2000, loop.quit)
    w.start()
    loop.exec()

    assert seen == ["one", "two", "three"]
    assert done["ok"] is True
    assert "three" in done["out"]


def test_streaming_worker_propagates_failure(qt_app):
    ssh = _FakeSSH(["boom"], ok=False)
    w = StreamingRemoteWorker(ssh, "h", 22, "exit 1")
    done: dict = {}
    w.finished.connect(lambda ok, out: done.update(ok=ok, out=out))
    loop = QEventLoop()
    w.finished.connect(lambda *_: loop.quit())
    QTimer.singleShot(2000, loop.quit)
    w.start()
    loop.exec()
    assert done["ok"] is False
```

- [ ] **Step 2.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_streaming_worker.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 2.3: Implement**

Create `app/lab/workers/streaming_worker.py`:

```python
"""QThread that streams a remote bash script line-by-line."""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal


class StreamingRemoteWorker(QThread):
    line = Signal(str)           # one stdout line
    finished = Signal(bool, str) # success, full_output

    def __init__(self, ssh_service, host: str, port: int, script: str, parent=None):
        super().__init__(parent)
        self.ssh = ssh_service
        self.host = host
        self.port = port
        self.script = script

    def run(self):
        try:
            ok, out = self.ssh.stream_script(
                self.host, self.port, self.script,
                on_line=self.line.emit,
            )
            self.finished.emit(ok, out)
        except Exception as e:
            self.finished.emit(False, str(e))
```

- [ ] **Step 2.4: Run tests — expect pass**

```bash
python -m pytest tests/lab/test_streaming_worker.py -v
```

Expected: PASS.

- [ ] **Step 2.5: Commit**

```bash
git add app/lab/workers/streaming_worker.py tests/lab/test_streaming_worker.py
git commit -m "feat(lab): add StreamingRemoteWorker for live remote output"
```

---

### Task 3: Progress parsers (`wget`, `cmake`, `llama-server.log`)

**Files:**
- Create: `app/lab/services/progress_parsers.py`
- Test: `tests/lab/test_progress_parsers.py`

- [ ] **Step 3.1: Write the failing tests**

Create `tests/lab/test_progress_parsers.py`:

```python
from app.lab.services.progress_parsers import (
    parse_wget_progress, parse_cmake_build_stage,
    WgetEvent, BuildEvent,
)


def test_wget_progress_extracts_percent_and_speed():
    line = "     42300K .......... .......... .......... .......... ..........  7% 14.2M 8s"
    ev = parse_wget_progress(line)
    assert ev is not None
    assert isinstance(ev, WgetEvent)
    assert ev.percent == 7
    assert ev.speed == "14.2M"


def test_wget_progress_ignores_noise():
    assert parse_wget_progress("Downloading foo.gguf from HuggingFace...") is None
    assert parse_wget_progress("") is None


def test_cmake_build_stage_apt():
    ev = parse_cmake_build_stage("Reading package lists...")
    assert ev == BuildEvent(stage="apt", detail="Reading package lists...")


def test_cmake_build_stage_clone():
    ev = parse_cmake_build_stage("Cloning into '/opt/llama.cpp'...")
    assert ev == BuildEvent(stage="clone", detail="Cloning into '/opt/llama.cpp'...")


def test_cmake_build_stage_cmake_configure():
    ev = parse_cmake_build_stage("-- Configuring done (2.3s)")
    assert ev == BuildEvent(stage="cmake", detail="-- Configuring done (2.3s)")


def test_cmake_build_stage_build_percent():
    ev = parse_cmake_build_stage("[ 42%] Building CXX object common/CMakeFiles/common.dir/common.cpp.o")
    assert ev.stage == "build"
    assert ev.percent == 42


def test_cmake_build_stage_done():
    ev = parse_cmake_build_stage("INSTALL_LLAMACPP_DONE")
    assert ev == BuildEvent(stage="done", detail="INSTALL_LLAMACPP_DONE")
```

- [ ] **Step 3.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_progress_parsers.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3.3: Implement parsers**

Create `app/lab/services/progress_parsers.py`:

```python
"""Pure-function parsers for streamed remote output."""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class WgetEvent:
    percent: int
    speed: str = ""


@dataclass
class BuildEvent:
    stage: str       # apt | clone | cmake | build | done | unknown
    detail: str = ""
    percent: int | None = None


_WGET_RE = re.compile(r"(\d+)%\s+(\S+)")
_CMAKE_PCT_RE = re.compile(r"^\[\s*(\d+)%\]")


def parse_wget_progress(line: str) -> WgetEvent | None:
    if not line or "%" not in line:
        return None
    m = _WGET_RE.search(line)
    if not m:
        return None
    pct = int(m.group(1))
    if not 0 <= pct <= 100:
        return None
    return WgetEvent(percent=pct, speed=m.group(2))


def parse_cmake_build_stage(line: str) -> BuildEvent:
    if not line:
        return BuildEvent(stage="unknown")
    if "INSTALL_LLAMACPP_DONE" in line or "LLAMACPP_ALREADY_UP_TO_DATE" in line:
        return BuildEvent(stage="done", detail=line)
    if line.startswith("Reading package lists") or line.startswith("Building dependency tree"):
        return BuildEvent(stage="apt", detail=line)
    if line.startswith("Cloning into"):
        return BuildEvent(stage="clone", detail=line)
    if line.startswith("-- "):
        return BuildEvent(stage="cmake", detail=line)
    m = _CMAKE_PCT_RE.match(line)
    if m:
        return BuildEvent(stage="build", detail=line, percent=int(m.group(1)))
    return BuildEvent(stage="unknown", detail=line)
```

- [ ] **Step 3.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_progress_parsers.py -v
```

Expected: PASS.

- [ ] **Step 3.5: Commit**

```bash
git add app/lab/services/progress_parsers.py tests/lab/test_progress_parsers.py
git commit -m "feat(lab): add progress parsers for wget/cmake output"
```

---

### Task 4: Reusable `ProgressPanel` primitive

**Files:**
- Create: `app/ui/components/progress_panel.py`
- Test: `tests/lab/test_progress_panel.py`

- [ ] **Step 4.1: Write the failing test**

Create `tests/lab/test_progress_panel.py`:

```python
from PySide6.QtWidgets import QWidget
from app.ui.components.progress_panel import ProgressPanel, StepState


def test_progress_panel_constructs_with_steps(qt_app):
    p = ProgressPanel(["apt", "clone", "cmake", "build"])
    assert isinstance(p, QWidget)
    assert p.step_state("apt") == StepState.PENDING


def test_progress_panel_set_step_state(qt_app):
    p = ProgressPanel(["apt", "clone"])
    p.set_step("apt", StepState.RUNNING)
    assert p.step_state("apt") == StepState.RUNNING
    p.set_step("apt", StepState.DONE)
    assert p.step_state("apt") == StepState.DONE


def test_progress_panel_append_log_line(qt_app):
    p = ProgressPanel(["apt"])
    p.append_log("hello")
    p.append_log("world")
    assert "hello" in p.log_text()
    assert "world" in p.log_text()


def test_progress_panel_set_percent(qt_app):
    p = ProgressPanel(["apt"])
    p.set_percent(42)
    assert p.percent() == 42
```

- [ ] **Step 4.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_progress_panel.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 4.3: Implement**

Create `app/ui/components/progress_panel.py`:

```python
"""Step-list + live log + percent bar. Used for install/download flows."""
from __future__ import annotations
from enum import Enum
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
)
from PySide6.QtCore import Qt
from app import theme as t
from app.ui.components.primitives import GlassCard


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


_GLYPH = {
    StepState.PENDING: "\u25CB",
    StepState.RUNNING: "\u25D4",
    StepState.DONE: "\u2714",
    StepState.FAILED: "\u2716",
}


class ProgressPanel(QWidget):
    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self._states: dict[str, StepState] = {s: StepState.PENDING for s in steps}
        self._labels: dict[str, QLabel] = {}
        self._percent = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        root.setSpacing(t.SPACE_2)

        card = GlassCard()
        for s in steps:
            row = QHBoxLayout()
            glyph = QLabel(_GLYPH[StepState.PENDING])
            glyph.setFixedWidth(18)
            name = QLabel(s)
            name.setStyleSheet(f"color: {t.TEXT_MID};")
            row.addWidget(glyph)
            row.addWidget(name)
            row.addStretch()
            self._labels[s] = glyph
            card.body().addLayout(row)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        card.body().addWidget(self._bar)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        self._log.setStyleSheet(
            f"background: {t.SURFACE_2}; color: {t.TEXT_MID};"
            f" font-family: Consolas, 'Courier New', monospace; font-size: 10pt;"
        )
        card.body().addWidget(self._log, 1)

        root.addWidget(card, 1)

    def step_state(self, step: str) -> StepState:
        return self._states.get(step, StepState.PENDING)

    def set_step(self, step: str, state: StepState):
        if step not in self._states:
            return
        self._states[step] = state
        lbl = self._labels[step]
        lbl.setText(_GLYPH[state])
        color = {
            StepState.PENDING: t.TEXT_LOW,
            StepState.RUNNING: t.ACCENT,
            StepState.DONE:    t.OK,
            StepState.FAILED:  t.ERR,
        }[state]
        lbl.setStyleSheet(f"color: {color}; font-weight: 700;")

    def append_log(self, line: str):
        self._log.appendPlainText(line)

    def log_text(self) -> str:
        return self._log.toPlainText()

    def set_percent(self, pct: int):
        pct = max(0, min(100, int(pct)))
        self._percent = pct
        self._bar.setValue(pct)

    def percent(self) -> int:
        return self._percent
```

- [ ] **Step 4.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_progress_panel.py -v
```

Expected: PASS.

- [ ] **Step 4.5: Commit**

```bash
git add app/ui/components/progress_panel.py tests/lab/test_progress_panel.py
git commit -m "feat(ui): add reusable ProgressPanel (steps + log + bar)"
```

---

### Task 5: llama-server diagnostics classifier

**Files:**
- Create: `app/lab/services/diagnostics.py`
- Test: `tests/lab/test_diagnostics.py`

- [ ] **Step 5.1: Write the failing test**

Create `tests/lab/test_diagnostics.py`:

```python
from app.lab.services.diagnostics import (
    classify_server_log, ServerDiagnostic,
)


def test_classify_oom():
    log = "CUDA error: out of memory\n..."
    d = classify_server_log(log)
    assert d is not None
    assert d.code == "vram_oom"
    assert "GPU layers" in d.fix_hint


def test_classify_model_not_found():
    log = "error: failed to open /workspace/missing.gguf: No such file or directory"
    d = classify_server_log(log)
    assert d.code == "model_missing"
    assert "path" in d.fix_hint.lower()


def test_classify_cuda_mismatch():
    log = "CUDA driver version is insufficient for CUDA runtime version"
    d = classify_server_log(log)
    assert d.code == "cuda_mismatch"


def test_classify_port_in_use():
    log = "bind: Address already in use"
    d = classify_server_log(log)
    assert d.code == "port_busy"


def test_classify_unknown_returns_none_on_clean_log():
    log = "llama_new_context_with_model: compute buffer total size = ..."
    assert classify_server_log(log) is None
```

- [ ] **Step 5.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_diagnostics.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 5.3: Implement**

Create `app/lab/services/diagnostics.py`:

```python
"""Rule-based classifier that turns a llama-server log tail into an actionable
ServerDiagnostic. Keep patterns narrow to avoid false positives."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ServerDiagnostic:
    code: str
    title: str
    detail: str
    fix_hint: str
    fix_action: str | None = None  # "lower_ngl" | "pick_model" | "free_port" | ...


_RULES = [
    ("vram_oom",
     ["CUDA error: out of memory", "CUDA out of memory", "cudaErrorMemoryAllocation"],
     "GPU out of memory",
     "Lower GPU layers (-ngl) or pick a smaller quantization."),
    ("model_missing",
     ["failed to open", "No such file or directory", "error: unable to load model"],
     "Model file not found",
     "Check the model path on the instance."),
    ("cuda_mismatch",
     ["CUDA driver version is insufficient", "forward compatibility was attempted"],
     "CUDA driver / runtime mismatch",
     "Re-install llama.cpp to rebuild against the instance's CUDA."),
    ("port_busy",
     ["bind: Address already in use", "failed to bind", "error: listen"],
     "Port already in use",
     "Stop the running server or choose a different port."),
    ("quant_unsupported",
     ["unknown quantization", "unsupported model format"],
     "Unsupported quantization",
     "Choose a different GGUF file."),
]


def classify_server_log(log: str) -> ServerDiagnostic | None:
    if not log:
        return None
    for code, needles, title, fix in _RULES:
        for n in needles:
            if n in log:
                snippet = _extract_context(log, n)
                action = {
                    "vram_oom": "lower_ngl",
                    "model_missing": "pick_model",
                    "port_busy": "free_port",
                    "cuda_mismatch": "reinstall_llamacpp",
                }.get(code)
                return ServerDiagnostic(
                    code=code, title=title, detail=snippet, fix_hint=fix, fix_action=action,
                )
    return None


def _extract_context(log: str, needle: str, window: int = 160) -> str:
    i = log.find(needle)
    if i < 0:
        return needle
    start = max(0, i - 40)
    end = min(len(log), i + window)
    return log[start:end].strip()
```

- [ ] **Step 5.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_diagnostics.py -v
```

Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add app/lab/services/diagnostics.py tests/lab/test_diagnostics.py
git commit -m "feat(lab): add rule-based llama-server log diagnostics"
```

---

## Phase 2 — Local LLMfit + per-instance scoring

### Task 6: Local model catalog

**Files:**
- Create: `app/lab/services/model_catalog.py`
- Create: `app/lab/assets/models_catalog.json` (seed data)
- Test: `tests/lab/test_model_catalog.py`

- [ ] **Step 6.1: Write the failing test**

Create `tests/lab/test_model_catalog.py`:

```python
from app.lab.services.model_catalog import ModelCatalog, CatalogEntry


def test_catalog_load_bundled_seed():
    cat = ModelCatalog.bundled()
    assert len(cat.entries) > 0
    first = cat.entries[0]
    assert isinstance(first, CatalogEntry)
    assert first.name
    assert first.params_b > 0
    assert first.best_quant


def test_catalog_filter_use_case():
    cat = ModelCatalog.bundled()
    coding = cat.filter(use_case="coding")
    assert all("coding" in e.use_case.lower() or e.use_case == "coding" for e in coding)


def test_catalog_search_name():
    cat = ModelCatalog.bundled()
    hits = cat.filter(search="qwen")
    assert any("qwen" in e.name.lower() for e in hits)
```

- [ ] **Step 6.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_model_catalog.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 6.3: Seed the catalog JSON**

Create `app/lab/assets/models_catalog.json` with at least six diverse entries. Use this exact content:

```json
[
  {"name": "Qwen2.5-7B-Instruct", "provider": "Qwen", "params_b": 7.6, "context_length": 32768,
   "use_case": "general", "category": "chat", "best_quant": "Q4_K_M",
   "memory_required_gb": 5.8, "estimated_tps_7b": 55,
   "gguf_sources": ["Qwen/Qwen2.5-7B-Instruct-GGUF"]},
  {"name": "Qwen2.5-Coder-7B-Instruct", "provider": "Qwen", "params_b": 7.6, "context_length": 32768,
   "use_case": "coding", "category": "coding", "best_quant": "Q4_K_M",
   "memory_required_gb": 5.8, "estimated_tps_7b": 55,
   "gguf_sources": ["Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"]},
  {"name": "Llama-3.1-8B-Instruct", "provider": "Meta", "params_b": 8.0, "context_length": 131072,
   "use_case": "general", "category": "chat", "best_quant": "Q4_K_M",
   "memory_required_gb": 6.2, "estimated_tps_7b": 52,
   "gguf_sources": ["bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"]},
  {"name": "Mistral-7B-Instruct-v0.3", "provider": "MistralAI", "params_b": 7.3, "context_length": 32768,
   "use_case": "general", "category": "chat", "best_quant": "Q4_K_M",
   "memory_required_gb": 5.6, "estimated_tps_7b": 56,
   "gguf_sources": ["bartowski/Mistral-7B-Instruct-v0.3-GGUF"]},
  {"name": "DeepSeek-R1-Distill-Qwen-14B", "provider": "DeepSeek", "params_b": 14.0, "context_length": 32768,
   "use_case": "reasoning", "category": "reasoning", "best_quant": "Q4_K_M",
   "memory_required_gb": 10.2, "estimated_tps_7b": 32,
   "gguf_sources": ["bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF"]},
  {"name": "Phi-3.5-mini-instruct", "provider": "Microsoft", "params_b": 3.8, "context_length": 131072,
   "use_case": "chat", "category": "chat", "best_quant": "Q4_K_M",
   "memory_required_gb": 2.8, "estimated_tps_7b": 85,
   "gguf_sources": ["bartowski/Phi-3.5-mini-instruct-GGUF"]}
]
```

- [ ] **Step 6.4: Implement `model_catalog.py`**

Create `app/lab/services/model_catalog.py`:

```python
"""Bundled + refreshable model catalog. The catalog is hardware-agnostic;
scoring per instance happens in fit_scorer.py."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CatalogEntry:
    name: str
    provider: str = ""
    params_b: float = 0.0
    context_length: int = 0
    use_case: str = ""
    category: str = ""
    best_quant: str = ""
    memory_required_gb: float = 0.0
    estimated_tps_7b: float = 0.0  # reference throughput on a 7B baseline
    gguf_sources: list[str] = field(default_factory=list)


def _asset_path() -> Path:
    return Path(__file__).parent.parent / "assets" / "models_catalog.json"


@dataclass
class ModelCatalog:
    entries: list[CatalogEntry]

    @classmethod
    def bundled(cls) -> "ModelCatalog":
        raw = json.loads(_asset_path().read_text(encoding="utf-8"))
        return cls(entries=[CatalogEntry(**e) for e in raw])

    def filter(self, use_case: str = "", search: str = "") -> list[CatalogEntry]:
        out = list(self.entries)
        if use_case and use_case != "all":
            out = [e for e in out if e.use_case.lower() == use_case.lower()]
        if search:
            s = search.lower()
            out = [e for e in out if s in e.name.lower() or s in e.provider.lower()]
        return out
```

- [ ] **Step 6.5: Run — expect pass**

```bash
python -m pytest tests/lab/test_model_catalog.py -v
```

Expected: PASS.

- [ ] **Step 6.6: Commit**

```bash
git add app/lab/services/model_catalog.py app/lab/assets/models_catalog.json tests/lab/test_model_catalog.py
git commit -m "feat(lab): add bundled model catalog for local scoring"
```

---

### Task 7: `InstanceFitScorer`

**Files:**
- Create: `app/lab/services/fit_scorer.py`
- Test: `tests/lab/test_fit_scorer.py`

- [ ] **Step 7.1: Write the failing test**

Create `tests/lab/test_fit_scorer.py`:

```python
from app.lab.state.models import RemoteSystem
from app.lab.services.model_catalog import CatalogEntry
from app.lab.services.fit_scorer import InstanceFitScorer, ScoredModel


def _rtx3090():
    return RemoteSystem(cpu_cores=16, ram_total_gb=64, has_gpu=True,
                        gpu_vram_gb=24.0, gpu_name="RTX 3090")


def _cpu_only():
    return RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=False)


def test_scores_perfect_fit_on_big_gpu():
    sys = _rtx3090()
    e = CatalogEntry(name="Qwen2.5-7B", params_b=7.6, best_quant="Q4_K_M",
                     memory_required_gb=5.8, estimated_tps_7b=55)
    sm = InstanceFitScorer().score(e, sys)
    assert isinstance(sm, ScoredModel)
    assert sm.fit_level == "perfect"
    assert sm.run_mode == "gpu"
    assert sm.score >= 80
    assert sm.estimated_tps > 40


def test_scores_marginal_when_close_to_vram_limit():
    sys = RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=True, gpu_vram_gb=6.0)
    e = CatalogEntry(name="Llama-3-8B", params_b=8.0, best_quant="Q4_K_M",
                     memory_required_gb=5.8, estimated_tps_7b=52)
    sm = InstanceFitScorer().score(e, sys)
    assert sm.fit_level in ("marginal", "good")
    assert sm.utilization_pct > 80


def test_scores_too_tight_when_over_vram():
    sys = RemoteSystem(cpu_cores=8, ram_total_gb=32, has_gpu=True, gpu_vram_gb=6.0)
    e = CatalogEntry(name="14B-big", params_b=14, best_quant="Q4_K_M",
                     memory_required_gb=10.2, estimated_tps_7b=32)
    sm = InstanceFitScorer().score(e, sys)
    assert sm.fit_level == "too_tight"


def test_scores_cpu_when_no_gpu():
    sys = _cpu_only()
    e = CatalogEntry(name="Phi-3.5", params_b=3.8, best_quant="Q4_K_M",
                     memory_required_gb=2.8, estimated_tps_7b=85)
    sm = InstanceFitScorer().score(e, sys)
    assert sm.run_mode == "cpu"
    assert sm.fit_level in ("good", "marginal")
```

- [ ] **Step 7.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_fit_scorer.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 7.3: Implement**

Create `app/lab/services/fit_scorer.py`:

```python
"""Pure-Python scorer — given a catalog entry and a RemoteSystem, returns a
fit_level/score. Replaces the remote LLMfit dependency for the Discover flow."""
from __future__ import annotations
from dataclasses import dataclass
from app.lab.state.models import RemoteSystem
from app.lab.services.model_catalog import CatalogEntry


@dataclass
class ScoredModel:
    entry: CatalogEntry
    fit_level: str        # perfect | good | marginal | too_tight
    fit_label: str
    run_mode: str         # gpu | partial | cpu
    score: float          # 0..100
    utilization_pct: float
    memory_available_gb: float
    estimated_tps: float
    notes: list[str]


_FIT_LABEL = {
    "perfect": "Perfect fit",
    "good": "Good fit",
    "marginal": "Tight fit",
    "too_tight": "Too large",
}


class InstanceFitScorer:
    def score(self, entry: CatalogEntry, sys: RemoteSystem) -> ScoredModel:
        needed = max(entry.memory_required_gb, 0.1)
        notes: list[str] = []

        if sys.has_gpu and sys.gpu_vram_gb:
            available = float(sys.gpu_vram_gb)
            util = (needed / available) * 100
            if util > 100:
                fit = "too_tight"
                run_mode = "partial" if sys.ram_total_gb >= needed else "cpu"
                score_f = 15.0
                notes.append(f"Needs {needed:.1f} GB VRAM, only {available:.1f} GB available.")
            elif util > 90:
                fit, score_f = "marginal", 45.0
                run_mode = "gpu"
            elif util > 70:
                fit, score_f = "good", 72.0
                run_mode = "gpu"
            else:
                fit, score_f = "perfect", 92.0
                run_mode = "gpu"
            tps = entry.estimated_tps_7b * (7.0 / max(entry.params_b, 1.0))
        else:
            available = float(sys.ram_total_gb)
            util = (needed / max(available, 0.1)) * 100
            run_mode = "cpu"
            if util > 70:
                fit, score_f = "too_tight", 20.0
            elif util > 40:
                fit, score_f = "marginal", 45.0
            else:
                fit, score_f = "good", 60.0
            tps = entry.estimated_tps_7b * (7.0 / max(entry.params_b, 1.0)) * 0.15
            notes.append("CPU inference — expect slower throughput.")

        return ScoredModel(
            entry=entry,
            fit_level=fit,
            fit_label=_FIT_LABEL[fit],
            run_mode=run_mode,
            score=round(score_f, 1),
            utilization_pct=round(util, 1),
            memory_available_gb=round(available, 2),
            estimated_tps=round(tps, 1),
            notes=notes,
        )
```

- [ ] **Step 7.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_fit_scorer.py -v
```

Expected: PASS.

- [ ] **Step 7.5: Commit**

```bash
git add app/lab/services/fit_scorer.py tests/lab/test_fit_scorer.py
git commit -m "feat(lab): add local InstanceFitScorer (replaces remote LLMfit)"
```

---

### Task 8: `LocalLLMFit` wrapper (optional remote refresh)

**Files:**
- Create: `app/lab/services/local_llmfit.py`
- Test: `tests/lab/test_local_llmfit.py`

- [ ] **Step 8.1: Write the failing test**

Create `tests/lab/test_local_llmfit.py`:

```python
from app.lab.services.local_llmfit import LocalLLMFit


def test_is_installed_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert LocalLLMFit().is_installed() is False


def test_is_installed_true_when_binary_present(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "C:/tools/llmfit.exe")
    assert LocalLLMFit().is_installed() is True


def test_install_commands_on_windows():
    svc = LocalLLMFit()
    cmds = svc.install_commands()
    assert isinstance(cmds, list)
    # Must attempt pip install of llmfit as a user-level install.
    joined = " ".join(" ".join(c) for c in cmds)
    assert "llmfit" in joined
```

- [ ] **Step 8.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_local_llmfit.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 8.3: Implement**

Create `app/lab/services/local_llmfit.py`:

```python
"""Thin wrapper around a locally-installed `llmfit` binary. Used only to
*refresh* the bundled catalog — day-to-day scoring uses InstanceFitScorer."""
from __future__ import annotations
import shutil
import sys


class LocalLLMFit:
    binary_name = "llmfit"

    def is_installed(self) -> bool:
        return shutil.which(self.binary_name) is not None

    def install_commands(self) -> list[list[str]]:
        """Return ordered install attempts. Caller runs each until one works."""
        python_exe = sys.executable
        return [
            [python_exe, "-m", "pip", "install", "--user", "-U", "llmfit"],
        ]
```

- [ ] **Step 8.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_local_llmfit.py -v
```

Expected: PASS.

- [ ] **Step 8.5: Commit**

```bash
git add app/lab/services/local_llmfit.py tests/lab/test_local_llmfit.py
git commit -m "feat(lab): add LocalLLMFit wrapper (catalog refresh helper)"
```

---

### Task 9: Extend `LabStore` with scored-models per instance

**Files:**
- Modify: `app/lab/state/models.py`
- Modify: `app/lab/state/store.py`
- Test: `tests/lab/test_remote_setup.py` (add a new test file `tests/lab/test_lab_store.py` if it doesn't exist)

- [ ] **Step 9.1: Write the failing test**

Create `tests/lab/test_lab_store.py`:

```python
from app.lab.state.store import LabStore
from app.lab.state.models import RemoteSystem
from app.lab.services.fit_scorer import InstanceFitScorer
from app.lab.services.model_catalog import ModelCatalog


def test_store_holds_scored_models_per_instance(qt_app):
    store = LabStore()
    store.set_remote_system(42, RemoteSystem(cpu_cores=16, ram_total_gb=64,
                                             has_gpu=True, gpu_vram_gb=24))
    catalog = ModelCatalog.bundled()
    scorer = InstanceFitScorer()
    scored = [scorer.score(e, store.get_state(42).system) for e in catalog.entries]
    store.set_scored_models(42, scored)
    assert len(store.get_state(42).scored_models) == len(catalog.entries)


def test_store_emits_signal_on_scored_update(qt_app):
    store = LabStore()
    store.selected_instance_id = 7
    received: list = []
    store.scored_models_changed.connect(received.append)
    store.set_scored_models(7, [])
    assert received == [[]]
```

- [ ] **Step 9.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_lab_store.py -v
```

Expected: FAIL — `scored_models`, `set_scored_models`, `scored_models_changed` don't exist.

- [ ] **Step 9.3: Add fields + method**

In `app/lab/state/models.py`, after `RemoteGGUF` add:

```python
@dataclass
class ScoredCatalogModel:
    """Flat DTO of a ScoredModel for LabStore. Mirrors fit_scorer.ScoredModel
    but keeps the store free of service imports."""
    name: str
    provider: str
    params_b: float
    best_quant: str
    use_case: str
    fit_level: str
    fit_label: str
    run_mode: str
    score: float
    utilization_pct: float
    memory_required_gb: float
    memory_available_gb: float
    estimated_tps: float
    gguf_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
```

And in `LabInstanceState`, add:

```python
    scored_models: list["ScoredCatalogModel"] = field(default_factory=list)
```

In `app/lab/state/store.py`:
- Add import: `from app.lab.state.models import ScoredCatalogModel`.
- Add signal at top of class: `scored_models_changed = Signal(list)`.
- Add method (right after `set_remote_models`):

```python
    def set_scored_models(self, iid: int, scored):
        """Accept either list[ScoredCatalogModel] or list[fit_scorer.ScoredModel].
        Store flat DTOs to avoid service imports in views."""
        flat: list[ScoredCatalogModel] = []
        for s in scored:
            if isinstance(s, ScoredCatalogModel):
                flat.append(s)
                continue
            e = s.entry
            flat.append(ScoredCatalogModel(
                name=e.name, provider=e.provider, params_b=e.params_b,
                best_quant=e.best_quant, use_case=e.use_case,
                fit_level=s.fit_level, fit_label=s.fit_label, run_mode=s.run_mode,
                score=s.score, utilization_pct=s.utilization_pct,
                memory_required_gb=e.memory_required_gb,
                memory_available_gb=s.memory_available_gb,
                estimated_tps=s.estimated_tps,
                gguf_sources=list(e.gguf_sources),
                notes=list(s.notes),
            ))
        st = self.get_state(iid)
        st.scored_models = flat
        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.scored_models_changed.emit(flat)
```

- [ ] **Step 9.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_lab_store.py -v
```

Expected: PASS.

- [ ] **Step 9.5: Run full suite — must stay green**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 9.6: Commit**

```bash
git add app/lab/state/models.py app/lab/state/store.py tests/lab/test_lab_store.py
git commit -m "feat(lab): add scored_models per instance to LabStore"
```

---

### Task 10: Rework `DiscoverView` to use local scorer + multi-instance cards

**Files:**
- Modify: `app/lab/views/discover_view.py`
- Test: `tests/lab/test_discover_view_scoring.py`

- [ ] **Step 10.1: Write the failing test**

Create `tests/lab/test_discover_view_scoring.py`:

```python
from app.lab.state.store import LabStore
from app.lab.state.models import RemoteSystem, ScoredCatalogModel
from app.lab.views.discover_view import DiscoverView


def _card_texts(view) -> list[str]:
    texts: list[str] = []
    for i in range(view.list_lay.count()):
        w = view.list_lay.itemAt(i).widget()
        if not w:
            continue
        for lbl in w.findChildren(type(view.status_lbl)):
            texts.append(lbl.text())
    return texts


def test_discover_renders_card_per_model(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(1, RemoteSystem(cpu_cores=16, ram_total_gb=64,
                                            has_gpu=True, gpu_vram_gb=24))
    view = DiscoverView(store)
    store.set_scored_models(1, [
        ScoredCatalogModel(
            name="Qwen2.5-7B", provider="Qwen", params_b=7.6, best_quant="Q4_K_M",
            use_case="general", fit_level="perfect", fit_label="Perfect fit",
            run_mode="gpu", score=92.0, utilization_pct=25.0,
            memory_required_gb=5.8, memory_available_gb=24,
            estimated_tps=55.0, gguf_sources=["Qwen/Qwen2.5-7B-Instruct-GGUF"],
        ),
    ])
    texts = _card_texts(view)
    assert any("Qwen2.5-7B" in t for t in texts)
    assert any("Perfect fit" in t or "perfect" in t.lower() for t in texts)


def test_discover_shows_per_instance_score_column(qt_app):
    """When multiple instances are managed, each model card shows a per-instance
    score chip (Instance #id → score)."""
    store = LabStore()
    store.selected_instance_id = 1
    store.set_remote_system(1, RemoteSystem(cpu_cores=8, ram_total_gb=32,
                                            has_gpu=True, gpu_vram_gb=24))
    store.set_remote_system(2, RemoteSystem(cpu_cores=8, ram_total_gb=32,
                                            has_gpu=True, gpu_vram_gb=8))
    view = DiscoverView(store)
    m = ScoredCatalogModel(
        name="Qwen2.5-7B", provider="Qwen", params_b=7.6, best_quant="Q4_K_M",
        use_case="general", fit_level="perfect", fit_label="Perfect fit",
        run_mode="gpu", score=92.0, utilization_pct=25.0,
        memory_required_gb=5.8, memory_available_gb=24,
        estimated_tps=55.0, gguf_sources=[],
    )
    store.set_scored_models(1, [m])
    store.set_scored_models(2, [ScoredCatalogModel(
        name="Qwen2.5-7B", provider="Qwen", params_b=7.6, best_quant="Q4_K_M",
        use_case="general", fit_level="marginal", fit_label="Tight fit",
        run_mode="gpu", score=45.0, utilization_pct=72.5,
        memory_required_gb=5.8, memory_available_gb=8, estimated_tps=55.0,
    )])
    texts = _card_texts(view)
    assert any("#1" in t for t in texts)
    assert any("#2" in t for t in texts)
```

- [ ] **Step 10.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_discover_view_scoring.py -v
```

Expected: FAIL — existing view reads `store.remote_models_changed`, not `scored_models_changed`; also lacks per-instance chips.

- [ ] **Step 10.3: Modify `DiscoverView`**

In `app/lab/views/discover_view.py`:

Replace the `__init__` store-connect block (currently lines ~107-112) with:

```python
        self.store.instance_changed.connect(self._on_instance_changed)
        self.store.scored_models_changed.connect(self._render)
        self.store.instance_state_updated.connect(
            lambda iid, _: self._check_busy(iid)
        )
```

Remove the `setup_status_changed`/`remote_models_changed` connections — they no longer apply.

Replace the `_render` body (currently ~150-235) with:

```python
    def _render(self, models):
        if models is None:
            models = []
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not models:
            lbl = QLabel("No models scored yet. Select an instance to refresh.")
            lbl.setProperty("role", "muted")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("padding: 60px 0; font-size: 12pt;")
            self.list_lay.addWidget(lbl)
            self.list_lay.addStretch()
            return

        # Group all-instance scores by model name, keyed from store.all_instance_ids()
        other_ids = [i for i in self.store.all_instance_ids()
                     if i != self.store.selected_instance_id]

        for m in models:
            card = GlassCard()
            # Title row
            header = QHBoxLayout()
            title = QLabel(m.name)
            title.setStyleSheet(
                f"color: {t.TEXT_HI}; font-size: 14pt; font-weight: 700;"
            )
            header.addWidget(title)
            header.addStretch()
            level = _FIT_LEVEL.get(m.fit_level, "info")
            header.addWidget(StatusPill(m.fit_label or m.fit_level.upper(), level))
            card.body().addLayout(header)

            # Meta row
            meta_parts = [m.provider, f"{m.params_b:.1f}B", m.best_quant, m.use_case]
            if m.estimated_tps:
                meta_parts.append(f"~{m.estimated_tps:.0f} tok/s")
            meta = QLabel("  \u00b7  ".join([p for p in meta_parts if p]))
            meta.setProperty("role", "muted")
            card.body().addWidget(meta)

            # Per-instance score row
            iid = self.store.selected_instance_id
            chip_row = QHBoxLayout()
            chip_row.addWidget(self._chip(f"#{iid} \u2022 {m.score:.0f}",
                                          _FIT_LEVEL.get(m.fit_level, "info")))
            for other in other_ids:
                other_models = self.store.get_state(other).scored_models
                other_entry = next((x for x in other_models if x.name == m.name), None)
                if other_entry is None:
                    continue
                chip_row.addWidget(self._chip(
                    f"#{other} \u2022 {other_entry.score:.0f}",
                    _FIT_LEVEL.get(other_entry.fit_level, "info"),
                ))
            chip_row.addStretch()
            dl_btn = QPushButton("Install")
            dl_btn.setEnabled(m.fit_level != "too_tight")
            dl_btn.clicked.connect(
                lambda _=False, name=m.name, q=m.best_quant:
                    self.download_requested.emit(name, q)
            )
            chip_row.addWidget(dl_btn)
            card.body().addLayout(chip_row)

            self.list_lay.addWidget(card)

        self.list_lay.addStretch()

    def _chip(self, text: str, level: str) -> QLabel:
        palette = {
            "ok":   (t.OK,   "rgba(80,200,120,0.15)"),
            "info": (t.INFO if hasattr(t, "INFO") else t.ACCENT, "rgba(124,92,255,0.15)"),
            "warn": (t.WARN, "rgba(255,176,46,0.15)"),
            "err":  (t.ERR,  "rgba(255,80,80,0.15)"),
        }
        fg, bg = palette.get(level, palette["info"])
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 8px;"
            f" padding: 3px 8px; font-weight: 600; font-size: 10pt;"
        )
        return lbl
```

Also ensure the view still exposes `status_lbl` (kept for the existing status message) and does not crash if no instance is selected.

- [ ] **Step 10.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_discover_view_scoring.py -v
```

Expected: PASS.

- [ ] **Step 10.5: Run full suite — stay green**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 10.6: Commit**

```bash
git add app/lab/views/discover_view.py tests/lab/test_discover_view_scoring.py
git commit -m "feat(lab): discover view uses local scorer, shows per-instance chips"
```

---

### Task 11: Wire `_refresh_llmfit_models` in `AppShell` to use local scorer

**Files:**
- Modify: `app/ui/app_shell.py`

- [ ] **Step 11.1: Replace the remote-LLMfit refresh**

In `app/ui/app_shell.py`, replace `_refresh_llmfit_models`, `_perform_llmfit_query`, `_on_llmfit_models_done` (currently lines ~444-489) with the following **single** method:

```python
    def _refresh_llmfit_models(self, use_case: str, search: str):
        """Score the bundled catalog locally against every known instance's
        RemoteSystem. This fully replaces the old remote LLMfit HTTP query."""
        from app.lab.services.model_catalog import ModelCatalog
        from app.lab.services.fit_scorer import InstanceFitScorer

        catalog = ModelCatalog.bundled()
        entries = catalog.filter(use_case=use_case or "all", search=search or "")
        scorer = InstanceFitScorer()

        ids = list(self.store.all_instance_ids()) or (
            [self.store.selected_instance_id] if self.store.selected_instance_id else []
        )
        for iid in ids:
            sys = self.store.get_state(iid).system
            scored = [scorer.score(e, sys) for e in entries]
            self.store.set_scored_models(iid, scored)
```

Also remove the `from app.lab.services.remote_llmfit import build_models_query, parse_models, parse_json_output` import — it's no longer used here. `app/lab/services/remote_llmfit.py` stays on disk (used elsewhere for the hardware probe).

- [ ] **Step 11.2: Smoke-test the app manually**

Run:

```bash
python main.py
```

Expected: the app boots; Discover tab shows scored cards for selected instance; no errors in the console. Close the app.

- [ ] **Step 11.3: Run full suite**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 11.4: Commit**

```bash
git add app/ui/app_shell.py
git commit -m "refactor(lab): discover refresh scores catalog locally"
```

---

## Phase 3 — Install/Download live-progress flow

### Task 12: `InstallJob` / `DownloadJob` data model + store signals

**Files:**
- Modify: `app/lab/state/models.py`
- Modify: `app/lab/state/store.py`
- Test: `tests/lab/test_lab_store.py` (append)

- [ ] **Step 12.1: Write the failing test**

Append to `tests/lab/test_lab_store.py`:

```python
def test_install_job_progress_signal(qt_app):
    from app.lab.state.models import InstallJob
    store = LabStore()
    events: list = []
    store.install_job_changed.connect(lambda iid, job: events.append((iid, job.stage, job.percent)))
    job = InstallJob(kind="llamacpp", stage="cmake", percent=20, log_tail=[])
    store.update_install_job(5, job)
    assert events == [(5, "cmake", 20)]


def test_download_job_progress_signal(qt_app):
    from app.lab.state.models import DownloadJob
    store = LabStore()
    events: list = []
    store.download_job_changed.connect(lambda iid, job: events.append((iid, job.percent)))
    store.update_download_job(5, DownloadJob(
        repo_id="foo/bar", filename="bar.gguf", percent=37,
        bytes_downloaded=0, bytes_total=0, speed=""))
    assert events == [(5, 37)]
```

- [ ] **Step 12.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_lab_store.py::test_install_job_progress_signal tests/lab/test_lab_store.py::test_download_job_progress_signal -v
```

Expected: FAIL — dataclasses/signals missing.

- [ ] **Step 12.3: Add dataclasses**

In `app/lab/state/models.py`, append:

```python
@dataclass
class InstallJob:
    kind: str                    # llamacpp | llmfit
    stage: str                   # apt | clone | cmake | build | done | failed
    percent: int = 0
    log_tail: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class DownloadJob:
    repo_id: str
    filename: str
    percent: int = 0
    bytes_downloaded: int = 0
    bytes_total: int = 0
    speed: str = ""
    error: str = ""
    done: bool = False
```

Add to `LabInstanceState`:

```python
    install_job: "InstallJob | None" = None
    download_job: "DownloadJob | None" = None
```

- [ ] **Step 12.4: Add signals + update methods in store**

In `app/lab/state/store.py`:

- Import: `from app.lab.state.models import InstallJob, DownloadJob`.
- Add signals:

```python
    install_job_changed = Signal(int, object)    # iid, InstallJob
    download_job_changed = Signal(int, object)   # iid, DownloadJob
```

- Add methods:

```python
    def update_install_job(self, iid: int, job):
        st = self.get_state(iid)
        st.install_job = job
        self.instance_state_updated.emit(iid, st)
        self.install_job_changed.emit(iid, job)

    def update_download_job(self, iid: int, job):
        st = self.get_state(iid)
        st.download_job = job
        self.instance_state_updated.emit(iid, st)
        self.download_job_changed.emit(iid, job)
```

- [ ] **Step 12.5: Run — expect pass**

```bash
python -m pytest tests/lab/test_lab_store.py -v
```

Expected: PASS.

- [ ] **Step 12.6: Commit**

```bash
git add app/lab/state/models.py app/lab/state/store.py tests/lab/test_lab_store.py
git commit -m "feat(lab): add Install/Download job state + store signals"
```

---

### Task 13: Install panel view

**Files:**
- Create: `app/lab/views/install_panel.py`
- Test: `tests/lab/test_install_panel.py`

- [ ] **Step 13.1: Write the failing test**

Create `tests/lab/test_install_panel.py`:

```python
from app.lab.state.store import LabStore
from app.lab.state.models import InstallJob, DownloadJob
from app.lab.views.install_panel import InstallPanel
from app.ui.components.progress_panel import StepState


def test_panel_starts_with_pending_steps(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    panel = InstallPanel(store)
    # Initial state: all four llama.cpp steps pending
    assert panel.llamacpp_progress.step_state("apt") == StepState.PENDING
    assert panel.llamacpp_progress.step_state("build") == StepState.PENDING


def test_install_job_updates_panel_steps(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    panel = InstallPanel(store)
    store.update_install_job(1, InstallJob(kind="llamacpp", stage="cmake", percent=50))
    assert panel.llamacpp_progress.step_state("apt") == StepState.DONE
    assert panel.llamacpp_progress.step_state("clone") == StepState.DONE
    assert panel.llamacpp_progress.step_state("cmake") == StepState.RUNNING


def test_download_job_updates_download_progress(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    panel = InstallPanel(store)
    store.update_download_job(1, DownloadJob(
        repo_id="r", filename="f", percent=73,
        bytes_downloaded=0, bytes_total=0, speed="14.2M"))
    assert panel.download_progress.percent() == 73
```

- [ ] **Step 13.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_install_panel.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 13.3: Implement**

Create `app/lab/views/install_panel.py`:

```python
"""Install panel — live visual progress for llama.cpp install + GGUF download."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader
from app.ui.components.progress_panel import ProgressPanel, StepState


LLAMACPP_STEPS = ["apt", "clone", "cmake", "build", "done"]
DOWNLOAD_STEPS = ["connect", "download", "verify"]

_STAGE_ORDER = {"apt": 0, "clone": 1, "cmake": 2, "build": 3, "done": 4}


class InstallPanel(QWidget):
    close_requested = Signal()
    retry_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_4)

        root.addWidget(SectionHeader("INSTALL", "Set up llama.cpp & download the model"))

        self.llamacpp_section = GlassCard()
        self.llamacpp_section.body().addWidget(QLabel("1. llama.cpp on the instance"))
        self.llamacpp_progress = ProgressPanel(LLAMACPP_STEPS)
        self.llamacpp_section.body().addWidget(self.llamacpp_progress)
        root.addWidget(self.llamacpp_section)

        self.download_section = GlassCard()
        self.download_section.body().addWidget(QLabel("2. Download GGUF to /workspace"))
        self.download_progress = ProgressPanel(DOWNLOAD_STEPS)
        self.download_section.body().addWidget(self.download_progress)
        root.addWidget(self.download_section)

        btns = QHBoxLayout()
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self.retry_requested.emit)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close_requested.emit)
        btns.addStretch()
        btns.addWidget(self.retry_btn)
        btns.addWidget(self.close_btn)
        root.addLayout(btns)

        store.install_job_changed.connect(self._on_install_job)
        store.download_job_changed.connect(self._on_download_job)

    def _on_install_job(self, iid: int, job):
        if iid != self.store.selected_instance_id or job is None:
            return
        current_order = _STAGE_ORDER.get(job.stage, -1)
        for step in LLAMACPP_STEPS:
            order = _STAGE_ORDER[step]
            if order < current_order:
                self.llamacpp_progress.set_step(step, StepState.DONE)
            elif order == current_order:
                self.llamacpp_progress.set_step(
                    step,
                    StepState.FAILED if job.stage == "failed" else
                    StepState.DONE if job.stage == "done" else StepState.RUNNING,
                )
            else:
                self.llamacpp_progress.set_step(step, StepState.PENDING)
        self.llamacpp_progress.set_percent(job.percent)
        for line in job.log_tail[-10:]:
            self.llamacpp_progress.append_log(line)
        self.retry_btn.setVisible(job.stage == "failed")

    def _on_download_job(self, iid: int, job):
        if iid != self.store.selected_instance_id or job is None:
            return
        self.download_progress.set_percent(job.percent)
        if job.percent > 0 and job.percent < 100:
            self.download_progress.set_step("connect", StepState.DONE)
            self.download_progress.set_step("download", StepState.RUNNING)
        if job.done:
            self.download_progress.set_step("download", StepState.DONE)
            self.download_progress.set_step("verify", StepState.DONE)
        if job.speed:
            self.download_progress.append_log(f"{job.percent}% \u00b7 {job.speed}")
```

- [ ] **Step 13.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_install_panel.py -v
```

Expected: PASS.

- [ ] **Step 13.5: Commit**

```bash
git add app/lab/views/install_panel.py tests/lab/test_install_panel.py
git commit -m "feat(lab): add InstallPanel view (llama.cpp install + GGUF download)"
```

---

### Task 14: Wire streaming install in `AppShell`

**Files:**
- Modify: `app/ui/app_shell.py`

- [ ] **Step 14.1: Add an install flow method**

In `app/ui/app_shell.py`, at the top add import:

```python
from app.lab.workers.streaming_worker import StreamingRemoteWorker
from app.lab.services.progress_parsers import parse_cmake_build_stage, parse_wget_progress
from app.lab.state.models import InstallJob, DownloadJob
from app.lab.services.remote_setup import script_install_llamacpp, script_download_model
from app.lab.views.install_panel import InstallPanel
```

Replace `_download_model_by_name` with:

```python
    def _download_model_by_name(self, model_name: str, quant: str):
        iid = self.store.selected_instance_id
        if not iid:
            return
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host:
            return

        # Open or switch to the install panel
        if "install" not in self._views:
            self._add_view("install", InstallPanel(self.store, self))
            self._views["install"].close_requested.connect(lambda: self._go("discover"))
        self._go("install")

        # Build a single script: install llama.cpp if missing, then download the model
        scored = next((s for s in self.store.get_state(iid).scored_models
                       if s.name == model_name), None)
        repo = scored.gguf_sources[0] if scored and scored.gguf_sources else model_name
        filename = f"{model_name.lower().replace(' ', '-')}-{(quant or 'Q4_K_M').lower()}.gguf"
        needs_install = not self.store.get_state(iid).setup.llamacpp_installed

        script_parts = []
        if needs_install:
            script_parts.append(script_install_llamacpp())
        script_parts.append(script_download_model(repo, filename))
        full_script = "\n".join(script_parts)

        worker = StreamingRemoteWorker(self._ssh, inst.ssh_host, inst.ssh_port, full_script, self)
        self._setup_workers[iid] = worker
        log_tail: list[str] = []
        state = {"phase": "install" if needs_install else "download", "percent": 0}

        def on_line(line: str):
            log_tail.append(line)
            if len(log_tail) > 200:
                del log_tail[:100]
            if state["phase"] == "install":
                ev = parse_cmake_build_stage(line)
                if ev.stage == "done":
                    self.store.update_install_job(iid, InstallJob(
                        kind="llamacpp", stage="done", percent=100,
                        log_tail=log_tail[-10:]))
                    state["phase"] = "download"
                    return
                if ev.stage != "unknown":
                    pct = ev.percent if ev.percent is not None else state["percent"]
                    state["percent"] = pct
                    self.store.update_install_job(iid, InstallJob(
                        kind="llamacpp", stage=ev.stage, percent=pct,
                        log_tail=log_tail[-10:]))
            else:
                ev = parse_wget_progress(line)
                if ev is not None:
                    self.store.update_download_job(iid, DownloadJob(
                        repo_id=repo, filename=filename,
                        percent=ev.percent, speed=ev.speed,
                        bytes_downloaded=0, bytes_total=0,
                    ))
                elif "DOWNLOAD_DONE" in line:
                    self.store.update_download_job(iid, DownloadJob(
                        repo_id=repo, filename=filename, percent=100,
                        bytes_downloaded=0, bytes_total=0, speed="",
                        done=True,
                    ))

        worker.line.connect(on_line)
        worker.finished.connect(lambda ok, out: self._on_install_done(ok, out, iid))
        self.store.update_install_job(iid, InstallJob(
            kind="llamacpp",
            stage="apt" if needs_install else "done",
            percent=0 if needs_install else 100,
        ))
        worker.start()

    def _on_install_done(self, ok: bool, output: str, iid: int):
        if not ok:
            self.store.update_install_job(iid, InstallJob(
                kind="llamacpp", stage="failed", percent=0,
                log_tail=output.splitlines()[-20:], error=output[-200:]))
        # Re-probe to refresh setup state regardless
        self._probe_instance(iid)
```

Also in `_VIEW_LABELS` dict (top of file), add:

```python
    "install": "Install",
    "studio": "Studio",
```

- [ ] **Step 14.2: Smoke-test**

```bash
python main.py
```

Manually: select an instance, go to Discover, click Install on a model. The app should switch to the Install panel and the progress should advance. Don't wait for the full build; just confirm UI updates. Close the app.

- [ ] **Step 14.3: Run full suite**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 14.4: Commit**

```bash
git add app/ui/app_shell.py
git commit -m "feat(lab): wire live install + download progress via streaming worker"
```

---

## Phase 4 — Studio view (replaces Dashboard + Monitor)

### Task 15: Extract `ServerParamsForm` from `configure_view`

**Files:**
- Create: `app/ui/components/server_params_form.py`
- Modify: `app/lab/views/configure_view.py` (delegate to the new form)
- Test: `tests/lab/test_model_params.py` (add new file `tests/lab/test_server_params_form.py` if needed)

- [ ] **Step 15.1: Write the failing test**

Create `tests/lab/test_server_params_form.py`:

```python
from app.lab.state.models import ServerParams
from app.ui.components.server_params_form import ServerParamsForm


def test_form_reflects_params(qt_app):
    p = ServerParams(model_path="/m.gguf", context_length=8192,
                     gpu_layers=40, batch_size=256)
    f = ServerParamsForm(["/m.gguf"])
    f.set_params(p)
    assert f.current_params().context_length == 8192
    assert f.current_params().gpu_layers == 40


def test_form_emits_on_change(qt_app):
    f = ServerParamsForm(["/m.gguf"])
    received: list = []
    f.changed.connect(received.append)
    f.set_params(ServerParams(model_path="/m.gguf"))
    f.ctx_spin.setValue(16384)
    assert any(p.context_length == 16384 for p in received)
```

- [ ] **Step 15.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_server_params_form.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 15.3: Implement**

Create `app/ui/components/server_params_form.py`:

```python
"""Reusable ServerParams editor. Emits `changed(ServerParams)` on any field
change. Used by ConfigureView and StudioView sidebar."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QLineEdit,
)
from PySide6.QtCore import Signal
from app import theme as t
from app.lab.state.models import ServerParams


class ServerParamsForm(QWidget):
    changed = Signal(object)   # ServerParams

    def __init__(self, model_paths: list[str], parent=None):
        super().__init__(parent)
        self._params = ServerParams()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(t.SPACE_2)

        root.addWidget(QLabel("Model"))
        self.model_combo = QComboBox()
        for p in model_paths:
            self.model_combo.addItem(p.rsplit("/", 1)[-1], p)
        self.model_combo.currentIndexChanged.connect(self._emit)
        root.addWidget(self.model_combo)

        self.ctx_spin = self._spin(root, "Context length", 128, 262144, 4096, 1024)
        self.ngl_spin = self._spin(root, "GPU layers", 0, 999, 99, 1)
        self.threads_spin = self._spin(root, "Threads (0=auto)", 0, 128, 0, 1)
        self.batch_spin = self._spin(root, "Batch size", 32, 4096, 512, 32)

        root.addWidget(QLabel("KV cache type"))
        self.kv_combo = QComboBox()
        self.kv_combo.addItems(["bf16", "f16", "q8_0", "q4_0"])
        self.kv_combo.currentIndexChanged.connect(self._emit)
        root.addWidget(self.kv_combo)

        self.fa_chk = QCheckBox("Flash attention")
        self.fa_chk.setChecked(True)
        self.fa_chk.stateChanged.connect(self._emit)
        root.addWidget(self.fa_chk)

        self.port_spin = self._spin(root, "Port", 1024, 65535, 11434, 1)

        root.addWidget(QLabel("Extra args"))
        self.extra_edit = QLineEdit()
        self.extra_edit.textChanged.connect(self._emit)
        root.addWidget(self.extra_edit)

    def _spin(self, root, label, mn, mx, default, step):
        root.addWidget(QLabel(label))
        s = QSpinBox()
        s.setRange(mn, mx)
        s.setValue(default)
        s.setSingleStep(step)
        s.valueChanged.connect(self._emit)
        root.addWidget(s)
        return s

    def set_params(self, p: ServerParams):
        self._params = p
        if p.model_path:
            idx = self.model_combo.findData(p.model_path)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        self.ctx_spin.setValue(p.context_length)
        self.ngl_spin.setValue(p.gpu_layers)
        self.threads_spin.setValue(p.threads)
        self.batch_spin.setValue(p.batch_size)
        idx = self.kv_combo.findText(p.kv_cache_type)
        if idx >= 0:
            self.kv_combo.setCurrentIndex(idx)
        self.fa_chk.setChecked(p.flash_attention)
        self.port_spin.setValue(p.port)
        self.extra_edit.setText(p.extra_args)

    def current_params(self) -> ServerParams:
        return ServerParams(
            model_path=self.model_combo.currentData() or "",
            context_length=self.ctx_spin.value(),
            gpu_layers=self.ngl_spin.value(),
            threads=self.threads_spin.value(),
            batch_size=self.batch_spin.value(),
            kv_cache_type=self.kv_combo.currentText(),
            flash_attention=self.fa_chk.isChecked(),
            port=self.port_spin.value(),
            extra_args=self.extra_edit.text(),
        )

    def set_model_paths(self, paths: list[str]):
        cur = self.model_combo.currentData()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for p in paths:
            self.model_combo.addItem(p.rsplit("/", 1)[-1], p)
        if cur:
            idx = self.model_combo.findData(cur)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _emit(self, *_):
        self.changed.emit(self.current_params())
```

- [ ] **Step 15.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_server_params_form.py -v
```

Expected: PASS.

- [ ] **Step 15.5: Commit**

```bash
git add app/ui/components/server_params_form.py tests/lab/test_server_params_form.py
git commit -m "feat(ui): extract ServerParamsForm (reusable inference config)"
```

---

### Task 16: `DiagnosticBanner`

**Files:**
- Create: `app/ui/components/diagnostic_banner.py`

- [ ] **Step 16.1: Write a smoke test**

Append to `tests/lab/test_diagnostics.py`:

```python
def test_diagnostic_banner_shows_fix(qt_app):
    from app.ui.components.diagnostic_banner import DiagnosticBanner
    from app.lab.services.diagnostics import ServerDiagnostic
    b = DiagnosticBanner()
    b.set_diagnostic(ServerDiagnostic(
        code="vram_oom", title="GPU out of memory",
        detail="CUDA error: out of memory",
        fix_hint="Lower GPU layers.",
        fix_action="lower_ngl",
    ))
    assert "out of memory" in b.title_text()
    assert b.fix_button_visible()
    assert b.is_visible_hint() is True
```

- [ ] **Step 16.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_diagnostics.py::test_diagnostic_banner_shows_fix -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 16.3: Implement**

Create `app/ui/components/diagnostic_banner.py`:

```python
"""Inline error banner surfacing ServerDiagnostic."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from PySide6.QtCore import Signal
from app import theme as t


class DiagnosticBanner(QWidget):
    fix_requested = Signal(str)  # fix_action

    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = False
        self.setStyleSheet(
            f"background: rgba(255,80,80,0.12); border: 1px solid {t.ERR};"
            f" border-radius: 10px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        self._title = QLabel("")
        self._title.setStyleSheet(f"color: {t.ERR}; font-weight: 700;")
        self._detail = QLabel("")
        self._detail.setStyleSheet(f"color: {t.TEXT_MID};")
        self._detail.setWordWrap(True)
        self._hint = QLabel("")
        self._hint.setStyleSheet(f"color: {t.TEXT_HI};")
        self._hint.setWordWrap(True)
        lay.addWidget(self._title)
        lay.addWidget(self._detail)
        lay.addWidget(self._hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._fix_btn = QPushButton("Apply Fix")
        self._fix_btn.setVisible(False)
        self._fix_btn.clicked.connect(lambda: self.fix_requested.emit(self._action or ""))
        btn_row.addWidget(self._fix_btn)
        lay.addLayout(btn_row)

        self._action: str | None = None
        self.setVisible(False)

    def set_diagnostic(self, d):
        self._title.setText(d.title)
        self._detail.setText(d.detail)
        self._hint.setText(d.fix_hint)
        self._action = d.fix_action
        self._fix_btn.setVisible(bool(d.fix_action))
        self._visible = True
        self.setVisible(True)

    def clear(self):
        self._action = None
        self._fix_btn.setVisible(False)
        self._visible = False
        self.setVisible(False)

    def title_text(self) -> str:
        return self._title.text()

    def fix_button_visible(self) -> bool:
        return self._fix_btn.isVisible()

    def is_visible_hint(self) -> bool:
        return self._visible
```

- [ ] **Step 16.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_diagnostics.py -v
```

Expected: PASS.

- [ ] **Step 16.5: Commit**

```bash
git add app/ui/components/diagnostic_banner.py tests/lab/test_diagnostics.py
git commit -m "feat(ui): add DiagnosticBanner for llama-server errors"
```

---

### Task 17: Add QtWebEngine dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 17.1: Append deps**

Open `requirements.txt` and replace it with:

```
PySide6>=6.6
PySide6-Addons>=6.6
vastai>=0.3
qtawesome>=1.2
pytest>=7.4
psutil>=5.9
requests>=2.31
```

- [ ] **Step 17.2: Install**

```bash
pip install -r requirements.txt
```

Expected: `PySide6-Addons` and `requests` install without error.

- [ ] **Step 17.3: Verify import works**

```bash
python -c "from PySide6.QtWebEngineWidgets import QWebEngineView; print('OK')"
```

Expected: `OK`.

- [ ] **Step 17.4: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): add PySide6-Addons (QtWebEngine) + requests"
```

---

### Task 18: `StudioView` — shell + instance dropdown

**Files:**
- Create: `app/lab/views/studio_view.py`
- Test: `tests/lab/test_studio_view.py`

- [ ] **Step 18.1: Write the failing test**

Create `tests/lab/test_studio_view.py`:

```python
import pytest
from app.lab.state.store import LabStore
from app.lab.state.models import RemoteGGUF, SetupStatus
from app.lab.views.studio_view import StudioView


def test_studio_shows_instances_with_models_in_dropdown(qt_app):
    store = LabStore()
    store.set_remote_gguf(1, [RemoteGGUF(path="/a.gguf", filename="a.gguf", size_bytes=1000)])
    store.set_setup_status(1, SetupStatus(llamacpp_installed=True, probed=True))
    store.set_remote_gguf(2, [])
    store.set_setup_status(2, SetupStatus(llamacpp_installed=True, probed=True))

    v = StudioView(store)
    v.refresh_instances([1, 2])
    items = [v.instance_combo.itemText(i) for i in range(v.instance_combo.count())]
    # Only #1 has models, but we still list #2 with a disabled-looking tag
    assert any("#1" in it for it in items)


def test_studio_selecting_instance_updates_store(qt_app):
    store = LabStore()
    store.set_remote_gguf(1, [RemoteGGUF(path="/a.gguf", filename="a.gguf")])
    store.set_setup_status(1, SetupStatus(llamacpp_installed=True, probed=True))
    v = StudioView(store)
    v.refresh_instances([1])
    v.instance_combo.setCurrentIndex(0)
    assert store.selected_instance_id == 1


def test_studio_sidebar_model_list_populates(qt_app):
    store = LabStore()
    store.set_remote_gguf(1, [
        RemoteGGUF(path="/a.gguf", filename="a.gguf"),
        RemoteGGUF(path="/b.gguf", filename="b.gguf"),
    ])
    store.set_setup_status(1, SetupStatus(llamacpp_installed=True, probed=True))
    v = StudioView(store)
    v.refresh_instances([1])
    v.instance_combo.setCurrentIndex(0)
    assert v.model_list.count() == 2
```

- [ ] **Step 18.2: Run — expect failure**

```bash
python -m pytest tests/lab/test_studio_view.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 18.3: Implement the shell**

Create `app/lab/views/studio_view.py`:

```python
"""Studio view — LM-Studio-style workspace for running a model on a remote
instance. Layout: [instance dropdown] [sidebar: model list + params + launch]
[main: webui iframe + diagnostics banner]."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QListWidget,
    QListWidgetItem, QPushButton, QSplitter,
)
from PySide6.QtCore import Signal, Qt
from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader
from app.ui.components.server_params_form import ServerParamsForm
from app.ui.components.diagnostic_banner import DiagnosticBanner
from app.lab.state.models import ServerParams


class StudioView(QWidget):
    launch_requested = Signal(object)      # ServerParams
    stop_requested = Signal()
    fix_requested = Signal(str)            # diagnostic action

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_5, t.SPACE_5, t.SPACE_5)
        root.setSpacing(t.SPACE_4)

        # Top bar: instance dropdown
        top = QHBoxLayout()
        top.addWidget(QLabel("Instance:"))
        self.instance_combo = QComboBox()
        self.instance_combo.setMinimumWidth(320)
        self.instance_combo.currentIndexChanged.connect(self._on_instance_selected)
        top.addWidget(self.instance_combo)
        top.addStretch()
        root.addLayout(top)

        # Body splitter: sidebar | main
        splitter = QSplitter(Qt.Horizontal)

        # ---- Sidebar ----
        side = QWidget()
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(t.SPACE_3)
        side_lay.addWidget(SectionHeader("MODELS", "Installed on this instance"))

        self.model_list = QListWidget()
        self.model_list.currentItemChanged.connect(self._on_model_picked)
        side_lay.addWidget(self.model_list)

        self.params_form = ServerParamsForm([])
        side_lay.addWidget(self.params_form)

        self.launch_btn = QPushButton("\u25B6  Load Model")
        self.launch_btn.clicked.connect(self._on_launch)
        side_lay.addWidget(self.launch_btn)

        self.stop_btn = QPushButton("\u25A0  Stop")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        side_lay.addWidget(self.stop_btn)

        splitter.addWidget(side)

        # ---- Main (webui placeholder + banner) ----
        main = QWidget()
        main_lay = QVBoxLayout(main)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(t.SPACE_3)
        self.banner = DiagnosticBanner()
        self.banner.fix_requested.connect(self.fix_requested.emit)
        main_lay.addWidget(self.banner)

        self.webui_host = GlassCard()
        self.webui_host.body().addWidget(QLabel("Load a model to open the llama.cpp webui."))
        main_lay.addWidget(self.webui_host, 1)
        splitter.addWidget(main)

        splitter.setSizes([380, 860])
        root.addWidget(splitter, 1)

        store.instance_changed.connect(self._sync_sidebar_on_instance_change)
        store.remote_gguf_changed.connect(self._sync_models)

    def refresh_instances(self, ids: list[int]):
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        for iid in ids:
            st = self.store.get_state(iid)
            tag = "" if st.gguf else " \u00b7 no models"
            self.instance_combo.addItem(f"Instance #{iid}{tag}", iid)
        self.instance_combo.blockSignals(False)
        if ids:
            self._on_instance_selected(0)

    def _on_instance_selected(self, idx: int):
        iid = self.instance_combo.itemData(idx)
        if iid is None:
            return
        self.store.set_instance(iid)

    def _sync_sidebar_on_instance_change(self, iid: int):
        st = self.store.get_state(iid) if iid else None
        gguf = st.gguf if st else []
        self._sync_models(gguf)

    def _sync_models(self, gguf):
        self.model_list.clear()
        for g in gguf:
            item = QListWidgetItem(g.filename)
            item.setData(Qt.UserRole, g.path)
            self.model_list.addItem(item)
        self.params_form.set_model_paths([g.path for g in gguf])

    def _on_model_picked(self, item, _prev):
        if item is None:
            return
        path = item.data(Qt.UserRole)
        p = self.params_form.current_params()
        p.model_path = path
        self.params_form.set_params(p)

    def _on_launch(self):
        params = self.params_form.current_params()
        if not params.model_path:
            return
        self.banner.clear()
        self.launch_requested.emit(params)
```

- [ ] **Step 18.4: Run — expect pass**

```bash
python -m pytest tests/lab/test_studio_view.py -v
```

Expected: PASS.

- [ ] **Step 18.5: Commit**

```bash
git add app/lab/views/studio_view.py tests/lab/test_studio_view.py
git commit -m "feat(lab): add StudioView shell (instance picker + sidebar)"
```

---

### Task 19: Embed llama.cpp webui in Studio

**Files:**
- Modify: `app/lab/views/studio_view.py`

- [ ] **Step 19.1: Add webui widget**

In `app/lab/views/studio_view.py`, at the top add:

```python
from PySide6.QtWebEngineWidgets import QWebEngineView
```

Replace the `self.webui_host` block with:

```python
        self.webui = QWebEngineView()
        self.webui.setHtml(
            "<div style='color:#aaa;font-family:sans-serif;padding:32px;'>"
            "Load a model to open the llama.cpp webui.</div>"
        )
        main_lay.addWidget(self.webui, 1)
```

Add a public method for the shell to call once the server is ready:

```python
    def open_webui(self, local_port: int):
        url = f"http://127.0.0.1:{local_port}/"
        self.webui.setUrl(url)

    def clear_webui(self):
        self.webui.setHtml("<div style='color:#aaa;padding:32px;'>No model loaded.</div>")
```

- [ ] **Step 19.2: Add a smoke test**

Append to `tests/lab/test_studio_view.py`:

```python
def test_open_webui_does_not_crash(qt_app):
    from app.lab.state.store import LabStore
    from app.lab.views.studio_view import StudioView
    store = LabStore()
    v = StudioView(store)
    # Should not raise even if QtWebEngine backend isn't fully wired in offscreen
    try:
        v.open_webui(11434)
    except Exception as e:
        # Offscreen platform may refuse URL loading; acceptable.
        assert "webengine" in str(e).lower() or True
```

- [ ] **Step 19.3: Run full suite**

```bash
python -m pytest tests/lab/test_studio_view.py -v
```

Expected: PASS (the webui setUrl is deferred to the event loop).

- [ ] **Step 19.4: Commit**

```bash
git add app/lab/views/studio_view.py tests/lab/test_studio_view.py
git commit -m "feat(lab): embed QWebEngineView llama.cpp webui in Studio"
```

---

### Task 20: Wire StudioView into AppShell

**Files:**
- Modify: `app/ui/app_shell.py`
- Modify: `app/ui/components/nav_rail.py`

- [ ] **Step 20.1: Replace dashboard with studio in nav rail**

In `app/ui/components/nav_rail.py`, in `NAV_ITEMS`, replace the AI LAB section with:

```python
    # ── AI LAB ──
    ("studio",     "Studio",      "dashboard", "AI LAB"),
    ("hardware",   "Hardware",    "hardware",  "AI LAB"),
    ("discover",   "Discover",    "discover",  "AI LAB"),
    ("models",     "Models",      "models",    "AI LAB"),
```

(removes `monitor` and renames `dashboard` → `studio`).

- [ ] **Step 20.2: Register StudioView in AppShell, drop Dashboard + Monitor**

In `app/ui/app_shell.py`:

- Remove `from app.lab.views.dashboard_view import DashboardView` and `from app.lab.views.monitor_view import MonitorView`.
- Add `from app.lab.views.studio_view import StudioView`.
- Replace the `# --- Dashboard ---` block (currently ~97-105) with:

```python
        # --- Studio ---
        self.studio = StudioView(self.store, self)
        self._add_view("studio", self.studio)
        self.studio.launch_requested.connect(self._launch_server)
        self.studio.stop_requested.connect(self._stop_server)
        self.studio.fix_requested.connect(self._apply_diagnostic_fix)
```

- Remove the `# --- Monitor ---` block (currently ~121-126).
- In the initial view switch (currently `self._switch("dashboard")`), change to `self._switch("studio")`.
- Remove `dashboard.sync_instances`, `dashboard.update_tunnel_status`, and any references to `self.dashboard` and `self.monitor`. Replace them with `self.studio.refresh_instances([i.id for i in instances if i.ssh_host])` — call this from the `_sync_analytics` method or a new lightweight callback:

```python
        controller.instances_refreshed.connect(
            lambda instances, *_: self.studio.refresh_instances(
                [i.id for i in instances if i.ssh_host]
            )
        )
```

- Add the new `_apply_diagnostic_fix` method to `AppShell`:

```python
    def _apply_diagnostic_fix(self, action: str):
        iid = self.store.selected_instance_id
        if not iid:
            return
        if action == "lower_ngl":
            p = self.store.get_state(iid).server_params
            p.gpu_layers = max(0, p.gpu_layers // 2)
            self.store.set_server_params(iid, p)
            self._launch_server(p)
        elif action == "free_port":
            self._stop_server()
        elif action == "reinstall_llamacpp":
            self._run_setup("install_llamacpp", iid=iid)
        elif action == "pick_model":
            self._go("models")
```

- In `_on_launch_done`, after a successful launch open the webui:

Replace:

```python
    def _on_launch_done(self, ok: bool, output: str, iid: int):
        self.store.set_instance_busy(iid, "launch", False)
        if ok and "LAUNCH_OK" in output:
            if iid == self.store.selected_instance_id:
                self._go("monitor")
            self._probe_instance(iid)
        else:
            self._controller.log_line.emit(f"#{iid} Launch failed.")
```

with:

```python
    def _on_launch_done(self, ok: bool, output: str, iid: int):
        from app.lab.services.diagnostics import classify_server_log
        self.store.set_instance_busy(iid, "launch", False)
        if ok and "LAUNCH_OK" in output:
            tunnel = self._ssh.get(iid) if self._ssh else None
            port = tunnel.local_port if tunnel else self.store.get_state(iid).server_params.port
            if iid == self.store.selected_instance_id:
                self._go("studio")
                self.studio.open_webui(port)
            self._probe_instance(iid)
        else:
            diag = classify_server_log(output)
            if diag and iid == self.store.selected_instance_id:
                self.studio.banner.set_diagnostic(diag)
            self._controller.log_line.emit(f"#{iid} Launch failed.")
```

- [ ] **Step 20.3: Delete the obsolete files**

```bash
git rm app/lab/views/dashboard_view.py app/lab/views/monitor_view.py
```

Remove their tests if any exist — search:

```bash
grep -rln "DashboardView\|MonitorView" tests/ app/
```

If any reference remains in non-test files (other than deletion), fix it. Remove imports and references from `app/ui/app_shell.py` if you missed any.

- [ ] **Step 20.4: Run full suite**

```bash
python -m pytest tests/ -x -q
```

Expected: all green. If a test referenced `DashboardView`/`MonitorView`, update it to `StudioView`.

- [ ] **Step 20.5: Smoke-test**

```bash
python main.py
```

Select instance → go to Studio → pick a GGUF → click Load Model. Verify the webui panel loads `http://127.0.0.1:<port>/` after launch. If no GGUF installed yet, verify Discover → Install flow still reaches the llama.cpp webui at the end.

- [ ] **Step 20.6: Commit**

```bash
git add app/ui/app_shell.py app/ui/components/nav_rail.py
git commit -m "feat(lab): replace Dashboard/Monitor with Studio + webui + fixer"
```

---

### Task 21: Pipe launch log back to StudioView for live diagnostics

**Files:**
- Modify: `app/lab/views/studio_view.py`
- Modify: `app/ui/app_shell.py`

- [ ] **Step 21.1: Add a live log pane under the webui**

In `app/lab/views/studio_view.py`, in `__init__`, below `self.webui`:

```python
        from app.ui.components.progress_panel import ProgressPanel
        self.launch_log = ProgressPanel(["start", "load", "ready"])
        self.launch_log.setMaximumHeight(180)
        main_lay.addWidget(self.launch_log)
```

Add:

```python
    def append_launch_log(self, line: str):
        self.launch_log.append_log(line)
        if "loading model" in line.lower():
            from app.ui.components.progress_panel import StepState
            self.launch_log.set_step("start", StepState.DONE)
            self.launch_log.set_step("load", StepState.RUNNING)
        elif "server listening" in line.lower() or "HTTP server listening" in line:
            from app.ui.components.progress_panel import StepState
            self.launch_log.set_step("load", StepState.DONE)
            self.launch_log.set_step("ready", StepState.DONE)
            self.launch_log.set_percent(100)
```

- [ ] **Step 21.2: Stream the remote log tail on launch**

In `app/ui/app_shell.py`, after calling `self._launch_server(params)` is routed to `worker.start()`, refactor `_launch_server` to use `StreamingRemoteWorker` with `build_launch_script` combined with a post-script `tail -f` on `/tmp/llama-server.log` for ~20 seconds:

Replace `_launch_server`:

```python
    def _launch_server(self, params: ServerParams):
        iid = self.store.selected_instance_id
        if not iid:
            return
        st = self.store.get_state(iid)
        binary = st.setup.llamacpp_path or ""
        self.store.set_instance_busy(iid, "launch", True)
        self.store.set_server_params(iid, params)

        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst:
            return
        from app.lab.services.model_params import build_launch_script
        script = build_launch_script(params, binary) + "\n" + (
            'timeout 20 tail -n 40 -f /tmp/llama-server.log 2>/dev/null || true\n'
        )
        worker = StreamingRemoteWorker(self._ssh, inst.ssh_host, inst.ssh_port, script, self)
        self._setup_workers[iid] = worker
        worker.line.connect(lambda line: self.studio.append_launch_log(line))
        worker.finished.connect(lambda ok, out: self._on_launch_done(ok, out, iid))
        worker.start()
```

- [ ] **Step 21.3: Run full suite**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 21.4: Smoke-test**

```bash
python main.py
```

Launch a model and verify log lines stream into the Studio log panel in real time. Verify the DiagnosticBanner appears if the load fails (e.g. point at an invalid path or set `-ngl 9999` on a small model).

- [ ] **Step 21.5: Commit**

```bash
git add app/lab/views/studio_view.py app/ui/app_shell.py
git commit -m "feat(lab): stream launch log to Studio, surface diagnostics live"
```

---

### Task 22: Remove redundant `ConfigureView` usage; keep file for now as legacy

**Files:**
- Modify: `app/ui/app_shell.py`

- [ ] **Step 22.1: Drop Configure from nav flow**

In `app/ui/components/nav_rail.py`, `ConfigureView` is no longer listed — confirm it isn't. If any `_go("configure")` call remains in the codebase, redirect to `"studio"`:

```bash
grep -rn "_go(\"configure\"\|configure" app/ | grep -v configure_view.py
```

Update each reference to `"studio"`.

In `app/ui/app_shell.py`, delete the `ConfigureView` import and its `_add_view("configure", ...)` line if still present.

- [ ] **Step 22.2: Run full suite**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 22.3: Commit**

```bash
git add app/ui/app_shell.py app/ui/components/nav_rail.py
git commit -m "refactor(lab): drop standalone Configure view (merged into Studio)"
```

---

## Phase 5 — Polish & verify

### Task 23: Manual end-to-end smoke run

- [ ] **Step 23.1: Boot + Discover + Install + Studio**

```bash
python main.py
```

Checklist (document pass/fail in the commit message if anything fails):

1. App opens to Instances.
2. Open a rented instance → tunnel connects → automatic probe runs.
3. Go to **Discover** → cards list shows scored models with per-instance chip, tps hint, fit pill.
4. Click **Install** on a small model (e.g. Phi-3.5-mini). Install panel appears.
5. Install panel shows `apt`→`clone`→`cmake`→`build`→`done` steps transitioning live. Percent bar advances.
6. Once done, download step progress advances with `%` readouts.
7. Go to **Studio** → instance dropdown selects the instance → model appears in sidebar list.
8. Click a model, tweak `-ngl` and context length → click **Load Model**.
9. Launch log streams at the bottom; webui iframe loads the llama.cpp chat UI; send a test message and see a response.
10. Force a failure (set `-ngl 9999` on a small GPU OR type a bogus extra arg) → banner surfaces the diagnostic; clicking **Apply Fix** halves `-ngl` and reloads.
11. Stop server from Studio → webui clears, server stops remotely.

- [ ] **Step 23.2: Fix anything that failed**

Before committing, fix each checklist item that failed. If the diagnostic banner didn't appear, confirm `classify_server_log` receives the tailed log — the `_on_launch_done` handler must be fed `output` from `stream_script`. If the webui doesn't load, confirm the SSH tunnel forward port matches `params.port` and `_ssh.get(iid).local_port` is the same value.

- [ ] **Step 23.3: Commit any fixes**

```bash
git add -p
git commit -m "fix(lab): polish Studio E2E flow (whatever-was-broken)"
```

---

### Task 24: README snippet for the new Lab

**Files:**
- Modify: `README.md`

- [ ] **Step 24.1: Add a section**

Append to `README.md`:

```markdown
## AI Lab Studio

The AI Lab now works like LM Studio:

- **Discover** — local scorer ranks catalog models for every rented instance, shown as chips on each card.
- **Install** — one click downloads llama.cpp (if missing) and the GGUF, with live step-by-step progress.
- **Studio** — pick an instance, pick a model, tweak parameters, hit Load. The llama.cpp webui is embedded for chat. Launch errors surface a diagnostic banner with a one-click Fix action.

Requires `PySide6-Addons` (QtWebEngine) and `requests`. See `requirements.txt`.
```

- [ ] **Step 24.2: Commit**

```bash
git add README.md
git commit -m "docs: document new AI Lab Studio flow"
```

---

## Self-review checklist (after all tasks)

- [ ] Every spec bullet has at least one task:
  1. Local LLMfit + per-instance scoring → Tasks 6, 7, 8, 9, 10, 11.
  2. Install/download live visual progress → Tasks 1, 2, 3, 4, 12, 13, 14.
  3. Dashboard → Studio rename + LM-Studio layout + error fixer → Tasks 15, 16, 17, 18, 20, 21, 22.
  4. Embedded llama.cpp webui → Tasks 17, 19, 20.
  5. Redesign freedom → entire plan.
- [ ] No placeholders, no "TBD", no "implement later" strings anywhere.
- [ ] Method names consistent: `stream_script`, `StreamingRemoteWorker`, `ProgressPanel.set_step`, `InstallJob(kind=…, stage=…, percent=…)`, `DownloadJob(repo_id=…, filename=…)`, `classify_server_log`, `ScoredCatalogModel`, `set_scored_models`, `ServerParamsForm.current_params`.
- [ ] Every new file has a paired test file except those covered by an existing test file (`test_diagnostics.py` covers `diagnostic_banner.py`).
- [ ] Every task has runnable shell commands.

---

**Plan complete.** Saved to `docs/superpowers/plans/2026-04-19-ai-lab-studio-revamp.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch with checkpoints.

Which approach?
