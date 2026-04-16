# Vast.ai Manager — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local PySide6 desktop app to manage existing Vast.ai instances — list, start, stop, auto-tunnel, open terminal, show metrics and credits.

**Architecture:** Layered Python app. UI (PySide6) → Workers (QThread) → Services (SDK/subprocess) → OS. One-way data flow with Qt signals back. Config persisted as JSON in `~/.vastai-app/`. SSH via system `ssh.exe`.

**Tech Stack:** Python 3.10+, PySide6, `vastai` SDK, `qtawesome`, Windows OpenSSH.

**Spec:** [2026-04-14-vastai-manager-design.md](../specs/2026-04-14-vastai-manager-design.md)

**Testing approach:** Unit tests for pure logic (config, models, billing math, command builders, tunnel state machine). Manual smoke test for Qt widgets and SDK calls (pure TDD for GUI + external API integration adds more complexity than value here).

---

## Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `README.md` (stub)
- Create: `.gitignore`
- Create: `app/__init__.py` (empty)
- Create: `app/services/__init__.py` (empty)
- Create: `app/workers/__init__.py` (empty)
- Create: `app/ui/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Create `requirements.txt`**

```
PySide6>=6.6
vastai>=0.3
qtawesome>=1.2
pytest>=7.4
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
build/
dist/
*.spec
.vastai-app/
```

- [ ] **Step 3: Create README stub**

```markdown
# Vast.ai Manager
Local GUI to manage existing Vast.ai instances. Full docs at the end of implementation.
```

- [ ] **Step 4: Create empty package init files**

Touch `app/__init__.py`, `app/services/__init__.py`, `app/workers/__init__.py`, `app/ui/__init__.py`, `tests/__init__.py`.

- [ ] **Step 5: Install deps**

Run: `pip install -r requirements.txt`
Expected: packages installed without errors.

---

## Task 2: Models

**Files:**
- Create: `app/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_models.py
from app.models import Instance, InstanceState, TunnelStatus, UserInfo, AppConfig


def test_instance_state_enum_values():
    assert InstanceState.RUNNING.value == "running"
    assert InstanceState.STOPPED.value == "stopped"


def test_tunnel_status_enum_values():
    assert TunnelStatus.CONNECTED.value == "connected"


def test_app_config_defaults():
    cfg = AppConfig()
    assert cfg.api_key == ""
    assert cfg.refresh_interval_seconds == 30
    assert cfg.default_tunnel_port == 11434
    assert cfg.terminal_preference == "auto"
    assert cfg.auto_connect_on_activate is True


def test_instance_minimal_construction():
    inst = Instance(
        id=1, state=InstanceState.RUNNING, gpu_name="RTX 4090", num_gpus=1,
        gpu_ram_gb=24.0, gpu_util=None, gpu_temp=None, cpu_name=None,
        cpu_cores=None, cpu_util=None, ram_total_gb=None, ram_used_gb=None,
        disk_util=None, inet_down_mbps=None, inet_up_mbps=None, image=None,
        dph=0.42, duration_seconds=None, ssh_host=None, ssh_port=None, raw={},
    )
    assert inst.id == 1
    assert inst.state == InstanceState.RUNNING
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: ModuleNotFoundError for `app.models`.

- [ ] **Step 3: Implement `app/models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class InstanceState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


class TunnelStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass
class Instance:
    id: int
    state: InstanceState
    gpu_name: str
    num_gpus: int
    gpu_ram_gb: float
    gpu_util: float | None
    gpu_temp: float | None
    cpu_name: str | None
    cpu_cores: int | None
    cpu_util: float | None
    ram_total_gb: float | None
    ram_used_gb: float | None
    disk_util: float | None
    inet_down_mbps: float | None
    inet_up_mbps: float | None
    image: str | None
    dph: float
    duration_seconds: int | None
    ssh_host: str | None
    ssh_port: int | None
    raw: dict = field(default_factory=dict)


@dataclass
class UserInfo:
    balance: float
    email: str | None = None


@dataclass
class AppConfig:
    api_key: str = ""
    refresh_interval_seconds: int = 30
    default_tunnel_port: int = 11434
    terminal_preference: str = "auto"
    auto_connect_on_activate: bool = True
    schema_version: int = 1
```

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/test_models.py -v`
Expected: 4 passed.

---

## Task 3: Config load/save

**Files:**
- Create: `app/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
import json
from pathlib import Path
from app.config import ConfigStore
from app.models import AppConfig


def test_load_returns_default_when_missing(tmp_path):
    store = ConfigStore(tmp_path / "c.json")
    cfg = store.load()
    assert cfg.api_key == ""
    assert cfg.refresh_interval_seconds == 30


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "c.json"
    store = ConfigStore(path)
    original = AppConfig(api_key="abc123", default_tunnel_port=8080)
    store.save(original)
    loaded = store.load()
    assert loaded.api_key == "abc123"
    assert loaded.default_tunnel_port == 8080


def test_load_corrupted_file_returns_default(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("{not valid json")
    store = ConfigStore(path)
    cfg = store.load()
    assert cfg.api_key == ""


def test_save_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "c.json"
    store = ConfigStore(path)
    store.save(AppConfig(api_key="x"))
    assert path.exists()
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest tests/test_config.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `app/config.py`**

```python
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from app.models import AppConfig


DEFAULT_CONFIG_PATH = Path.home() / ".vastai-app" / "config.json"


class ConfigStore:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH):
        self.path = Path(path)

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__dataclass_fields__})
        except (json.JSONDecodeError, OSError, TypeError):
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_config.py -v`
Expected: 4 passed.

---

## Task 4: Vast service (SDK wrapper)

**Files:**
- Create: `app/services/vast_service.py`
- Create: `tests/test_vast_service.py`

- [ ] **Step 1: Write failing tests (parsing only — the SDK itself is mocked)**

```python
# tests/test_vast_service.py
from app.services.vast_service import parse_instance, parse_user_info
from app.models import InstanceState


def test_parse_instance_running():
    raw = {
        "id": 123, "actual_status": "running", "intended_status": "running",
        "gpu_name": "RTX 4090", "num_gpus": 1, "gpu_ram": 24576,
        "gpu_util": 72.5, "gpu_temp": 68, "cpu_name": "EPYC", "cpu_cores": 16,
        "cpu_util": 40.0, "cpu_ram": 32768, "mem_usage": 18000, "disk_util": 0.5,
        "inet_up": 12.4, "inet_down": 100.1, "label": None,
        "image_uuid": "pytorch/pytorch:2.1", "dph_total": 0.42,
        "duration": 11400, "ssh_host": "ssh5.vast.ai", "ssh_port": 12345,
    }
    inst = parse_instance(raw)
    assert inst.id == 123
    assert inst.state == InstanceState.RUNNING
    assert inst.gpu_name == "RTX 4090"
    assert inst.gpu_ram_gb == 24.0
    assert inst.gpu_util == 72.5
    assert inst.dph == 0.42
    assert inst.ssh_host == "ssh5.vast.ai"
    assert inst.ssh_port == 12345
    assert inst.image == "pytorch/pytorch:2.1"


def test_parse_instance_stopped():
    raw = {"id": 7, "actual_status": "exited", "intended_status": "stopped",
           "gpu_name": "RTX 3090", "num_gpus": 1, "gpu_ram": 24576, "dph_total": 0.28}
    inst = parse_instance(raw)
    assert inst.state == InstanceState.STOPPED


def test_parse_instance_starting():
    raw = {"id": 8, "actual_status": "loading", "intended_status": "running",
           "gpu_name": "A100", "num_gpus": 1, "gpu_ram": 40960, "dph_total": 1.10}
    inst = parse_instance(raw)
    assert inst.state == InstanceState.STARTING


def test_parse_user_info():
    raw = {"credit": 42.18, "email": "u@example.com"}
    u = parse_user_info(raw)
    assert u.balance == 42.18
    assert u.email == "u@example.com"


def test_parse_user_info_missing_fields():
    u = parse_user_info({})
    assert u.balance == 0.0
    assert u.email is None
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest tests/test_vast_service.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `app/services/vast_service.py`**

```python
from __future__ import annotations
from typing import Any
from app.models import Instance, InstanceState, UserInfo


class VastAuthError(Exception):
    pass


class VastNetworkError(Exception):
    pass


def _derive_state(actual: str | None, intended: str | None) -> InstanceState:
    a = (actual or "").lower()
    i = (intended or "").lower()
    if a == "running":
        return InstanceState.RUNNING
    if a in ("exited", "stopped", "offline"):
        if i == "running":
            return InstanceState.STARTING
        return InstanceState.STOPPED
    if a in ("loading", "scheduling", "created"):
        return InstanceState.STARTING
    if i == "stopped" and a != "running":
        return InstanceState.STOPPING
    return InstanceState.UNKNOWN


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_instance(raw: dict) -> Instance:
    gpu_ram_mb = _to_float(raw.get("gpu_ram")) or 0.0
    cpu_ram_mb = _to_float(raw.get("cpu_ram"))
    mem_usage_mb = _to_float(raw.get("mem_usage"))
    disk_util = _to_float(raw.get("disk_util"))
    # disk_util in Vast is a ratio 0-1; normalize to percent
    if disk_util is not None and disk_util <= 1.0:
        disk_util = disk_util * 100.0

    image = raw.get("label") or raw.get("image_uuid")

    return Instance(
        id=int(raw["id"]),
        state=_derive_state(raw.get("actual_status"), raw.get("intended_status")),
        gpu_name=raw.get("gpu_name") or "Unknown GPU",
        num_gpus=_to_int(raw.get("num_gpus")) or 1,
        gpu_ram_gb=gpu_ram_mb / 1024.0,
        gpu_util=_to_float(raw.get("gpu_util")),
        gpu_temp=_to_float(raw.get("gpu_temp")),
        cpu_name=raw.get("cpu_name"),
        cpu_cores=_to_int(raw.get("cpu_cores")),
        cpu_util=_to_float(raw.get("cpu_util")),
        ram_total_gb=(cpu_ram_mb / 1024.0) if cpu_ram_mb else None,
        ram_used_gb=(mem_usage_mb / 1024.0) if mem_usage_mb else None,
        disk_util=disk_util,
        inet_down_mbps=_to_float(raw.get("inet_down")),
        inet_up_mbps=_to_float(raw.get("inet_up")),
        image=image,
        dph=_to_float(raw.get("dph_total")) or 0.0,
        duration_seconds=_to_int(raw.get("duration")),
        ssh_host=raw.get("ssh_host") or raw.get("public_ipaddr"),
        ssh_port=_to_int(raw.get("ssh_port")),
        raw=raw,
    )


def parse_user_info(raw: dict) -> UserInfo:
    return UserInfo(
        balance=_to_float(raw.get("credit")) or 0.0,
        email=raw.get("email"),
    )


class VastService:
    """Wraps the vastai SDK. Holds the api_key and exposes typed methods."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._sdk = None

    def _client(self):
        if self._sdk is None:
            try:
                from vastai import VastAI
            except ImportError as e:
                raise RuntimeError("vastai package not installed") from e
            self._sdk = VastAI(api_key=self.api_key)
        return self._sdk

    def test_connection(self) -> UserInfo:
        try:
            raw = self._client().show_user()
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "unauthori" in msg or "forbidden" in msg:
                raise VastAuthError(str(e)) from e
            raise VastNetworkError(str(e)) from e
        return parse_user_info(_normalize_response(raw))

    def list_instances(self) -> list[Instance]:
        try:
            raw = self._client().show_instances()
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "unauthori" in msg:
                raise VastAuthError(str(e)) from e
            raise VastNetworkError(str(e)) from e
        items = _normalize_response(raw)
        if isinstance(items, dict) and "instances" in items:
            items = items["instances"]
        if not isinstance(items, list):
            return []
        return [parse_instance(i) for i in items]

    def start_instance(self, instance_id: int) -> None:
        try:
            self._client().start_instance(ID=instance_id)
        except Exception as e:
            raise VastNetworkError(str(e)) from e

    def stop_instance(self, instance_id: int) -> None:
        try:
            self._client().stop_instance(ID=instance_id)
        except Exception as e:
            raise VastNetworkError(str(e)) from e

    def get_user_info(self) -> UserInfo:
        return self.test_connection()


def _normalize_response(raw):
    """SDK methods sometimes return strings (printed output) or dicts. Handle both."""
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        import json
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if raw is not None else {}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_vast_service.py -v`
Expected: 5 passed.

---

## Task 5: SSH command builders + tunnel port probe

**Files:**
- Create: `app/services/ssh_service.py`
- Create: `tests/test_ssh_service.py`

- [ ] **Step 1: Write failing tests for pure helpers**

```python
# tests/test_ssh_service.py
from app.services.ssh_service import (
    build_ssh_command, build_tunnel_command, build_terminal_launch,
)


def test_build_ssh_command():
    cmd = build_ssh_command("ssh5.vast.ai", 12345)
    assert cmd == ["ssh", "-p", "12345", "root@ssh5.vast.ai"]


def test_build_tunnel_command_default_port():
    cmd = build_tunnel_command("ssh5.vast.ai", 12345, 11434)
    assert cmd == [
        "ssh", "-p", "12345", "root@ssh5.vast.ai",
        "-L", "11434:127.0.0.1:11434",
        "-N",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
    ]


def test_build_terminal_launch_wt():
    launch = build_terminal_launch(["ssh", "-p", "22", "root@h"], prefer="wt")
    assert launch[0] == "wt.exe"
    assert "ssh" in launch


def test_build_terminal_launch_cmd():
    launch = build_terminal_launch(["ssh", "-p", "22", "root@h"], prefer="cmd")
    assert launch[0] == "cmd.exe"
    assert launch[1] == "/k"


def test_build_terminal_launch_powershell():
    launch = build_terminal_launch(["ssh", "-p", "22", "root@h"], prefer="powershell")
    assert launch[0] == "powershell.exe"
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest tests/test_ssh_service.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `app/services/ssh_service.py`**

```python
from __future__ import annotations
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable


def build_ssh_command(host: str, port: int) -> list[str]:
    return ["ssh", "-p", str(port), f"root@{host}"]


def build_tunnel_command(host: str, port: int, local_port: int) -> list[str]:
    return [
        "ssh", "-p", str(port), f"root@{host}",
        "-L", f"{local_port}:127.0.0.1:{local_port}",
        "-N",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
    ]


def build_terminal_launch(ssh_cmd: list[str], prefer: str = "auto") -> list[str]:
    """Wrap ssh_cmd in a terminal launcher appropriate for Windows.
    prefer: auto | wt | cmd | powershell
    """
    if prefer == "auto":
        if shutil.which("wt.exe") or shutil.which("wt"):
            prefer = "wt"
        else:
            prefer = "cmd"
    if prefer == "wt":
        return ["wt.exe", "new-tab", "--", *ssh_cmd]
    if prefer == "powershell":
        return ["powershell.exe", "-NoExit", "-Command", " ".join(ssh_cmd)]
    # cmd fallback
    return ["cmd.exe", "/k", *ssh_cmd]


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def wait_for_local_port(port: int, timeout: float = 20.0, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_open("127.0.0.1", port):
            return True
        time.sleep(interval)
    return False


@dataclass
class TunnelHandle:
    instance_id: int
    local_port: int
    process: subprocess.Popen

    def alive(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        if self.alive():
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            except Exception:
                pass


class SSHService:
    """Owns SSH subprocesses. Not thread-safe by itself — call from one worker."""

    def __init__(self):
        self._tunnels: dict[int, TunnelHandle] = {}

    def open_terminal(self, host: str, port: int, prefer: str = "auto") -> None:
        ssh_cmd = build_ssh_command(host, port)
        launch = build_terminal_launch(ssh_cmd, prefer)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        subprocess.Popen(launch, creationflags=creationflags)

    def start_tunnel(self, instance_id: int, host: str, port: int, local_port: int) -> TunnelHandle:
        self.stop_tunnel(instance_id)
        cmd = build_tunnel_command(host, port, local_port)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            text=True,
        )
        handle = TunnelHandle(instance_id=instance_id, local_port=local_port, process=proc)
        self._tunnels[instance_id] = handle
        return handle

    def stop_tunnel(self, instance_id: int) -> None:
        h = self._tunnels.pop(instance_id, None)
        if h is not None:
            h.stop()

    def get(self, instance_id: int) -> TunnelHandle | None:
        return self._tunnels.get(instance_id)

    def all_active(self) -> list[TunnelHandle]:
        return list(self._tunnels.values())

    def stop_all(self) -> None:
        for h in list(self._tunnels.values()):
            h.stop()
        self._tunnels.clear()
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_ssh_service.py -v`
Expected: 5 passed.

---

## Task 6: Billing math helpers

**Files:**
- Create: `app/billing.py`
- Create: `tests/test_billing.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_billing.py
from datetime import date
from app.billing import burn_rate, autonomy_hours, DailySpendTracker
from app.models import Instance, InstanceState


def _inst(id_, state, dph, duration=None):
    return Instance(
        id=id_, state=state, gpu_name="x", num_gpus=1, gpu_ram_gb=24.0,
        gpu_util=None, gpu_temp=None, cpu_name=None, cpu_cores=None, cpu_util=None,
        ram_total_gb=None, ram_used_gb=None, disk_util=None,
        inet_down_mbps=None, inet_up_mbps=None, image=None, dph=dph,
        duration_seconds=duration, ssh_host=None, ssh_port=None, raw={},
    )


def test_burn_rate_sums_running():
    insts = [
        _inst(1, InstanceState.RUNNING, 0.42),
        _inst(2, InstanceState.STOPPED, 0.28),
        _inst(3, InstanceState.RUNNING, 0.30),
    ]
    assert burn_rate(insts) == 0.72


def test_autonomy_hours_zero_burn():
    assert autonomy_hours(10.0, 0.0) is None


def test_autonomy_hours_normal():
    assert autonomy_hours(10.0, 2.0) == 5.0


def test_daily_tracker_accumulates_delta():
    tracker = DailySpendTracker(today_fn=lambda: date(2026, 4, 14))
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=3600))
    assert tracker.today_spend() == 0.0  # first sample sets baseline
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=7200))
    assert abs(tracker.today_spend() - 1.0) < 1e-6  # +1h × $1


def test_daily_tracker_resets_on_new_day():
    current = [date(2026, 4, 14)]
    tracker = DailySpendTracker(today_fn=lambda: current[0])
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=3600))
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=7200))
    assert tracker.today_spend() > 0
    current[0] = date(2026, 4, 15)
    tracker.update(_inst(1, InstanceState.RUNNING, 1.0, duration=10800))
    assert tracker.today_spend() == 0.0
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest tests/test_billing.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `app/billing.py`**

```python
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
    today_fn: Callable[[], date] = field(default=lambda: date.today())
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_billing.py -v`
Expected: 5 passed.

---

## Task 7: Theme module

**Files:**
- Create: `app/theme.py`

- [ ] **Step 1: Implement theme module** (no tests — pure constants + stylesheet)

```python
from __future__ import annotations

# Palette
BG = "#1a1a2e"
CARD_BG = "#16213e"
CARD_BORDER = "#0f3460"
ACCENT = "#6C63FF"
ACCENT_HOVER = "#7D75FF"
TEXT = "#EAEAEA"
TEXT_SECONDARY = "#9AA0B4"
SUCCESS = "#00d26a"
WARNING = "#ffc107"
DANGER = "#f44336"
INFO = "#3ea6ff"
LOG_BG = "#0d0d1a"


def metric_color(percent: float | None) -> str:
    if percent is None:
        return TEXT_SECONDARY
    if percent < 60:
        return SUCCESS
    if percent < 85:
        return WARNING
    return DANGER


def temp_color(temp: float | None) -> str:
    if temp is None:
        return TEXT_SECONDARY
    if temp < 70:
        return SUCCESS
    if temp < 80:
        return WARNING
    return DANGER


def autonomy_color(hours: float | None) -> str:
    if hours is None:
        return TEXT_SECONDARY
    if hours > 24:
        return SUCCESS
    if hours > 6:
        return WARNING
    return DANGER


STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Segoe UI", sans-serif;
    font-size: 10pt;
}}
QWidget {{ color: {TEXT}; }}
QLabel#secondary {{ color: {TEXT_SECONDARY}; }}
QLabel#h1 {{ font-size: 16pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 600; }}
QLabel#mono {{ font-family: Consolas, "Courier New", monospace; }}

QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton:disabled {{ background-color: #3a3a4e; color: {TEXT_SECONDARY}; }}
QPushButton#secondary {{
    background-color: transparent;
    border: 1px solid {CARD_BORDER};
    color: {TEXT};
}}
QPushButton#secondary:hover {{ background-color: {CARD_BORDER}; }}
QPushButton#danger {{ background-color: {DANGER}; }}
QPushButton#danger:hover {{ background-color: #d32f2f; }}

QFrame#card {{
    background-color: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 10px;
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    color: {TEXT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QTextEdit#log {{
    background-color: {LOG_BG};
    color: {TEXT};
    border: 1px solid {CARD_BORDER};
    border-radius: 6px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 9pt;
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {CARD_BORDER}; border-radius: 5px; }}
"""
```

---

## Task 8: MetricBar widget

**Files:**
- Create: `app/ui/metric_bar.py`

- [ ] **Step 1: Implement MetricBar**

```python
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar, QSizePolicy
from PySide6.QtCore import Qt
from app import theme


class MetricBar(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.label = QLabel(label)
        self.label.setFixedWidth(60)
        self.label.setObjectName("secondary")

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.value_label = QLabel("—")
        self.value_label.setFixedWidth(80)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lay.addWidget(self.label)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.value_label)

    def set_value(self, percent: float | None, text: str | None = None):
        if percent is None:
            self.bar.setValue(0)
            self.value_label.setText("—")
            self._apply_color(theme.TEXT_SECONDARY)
            return
        p = max(0.0, min(100.0, percent))
        self.bar.setValue(int(p))
        self.value_label.setText(text if text is not None else f"{p:.0f}%")
        self._apply_color(theme.metric_color(p))

    def _apply_color(self, color: str):
        self.bar.setStyleSheet(
            f"QProgressBar {{ background-color: {theme.BG}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}"
        )
```

---

## Task 9: Toast notification

**Files:**
- Create: `app/ui/toast.py`

- [ ] **Step 1: Implement Toast**

```python
from __future__ import annotations
from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtCore import Qt, QTimer
from app import theme


class Toast(QLabel):
    COLORS = {
        "info": theme.INFO,
        "success": theme.SUCCESS,
        "warning": theme.WARNING,
        "error": theme.DANGER,
    }

    def __init__(self, parent: QWidget, message: str, kind: str = "info", duration_ms: int = 3000):
        super().__init__(parent)
        self.setText(message)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignCenter)
        color = self.COLORS.get(kind, theme.INFO)
        self.setStyleSheet(
            f"background-color: {theme.CARD_BG}; color: white; border-left: 4px solid {color};"
            f"border-radius: 6px; padding: 10px 16px; font-weight: 500;"
        )
        self.setFixedWidth(320)
        self.adjustSize()
        self._position()
        self.show()
        QTimer.singleShot(duration_ms, self.close)
        self.mousePressEvent = lambda e: self.close()

    def _position(self):
        if self.parent() is None:
            return
        parent = self.parent()
        margin = 20
        x = parent.width() - self.width() - margin
        y = parent.height() - self.height() - margin
        self.move(x, y)
```

---

## Task 10: Log panel

**Files:**
- Create: `app/ui/log_panel.py`

- [ ] **Step 1: Implement LogPanel**

```python
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import QTextEdit


class LogPanel(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("log")
        self.setReadOnly(True)
        self.setFixedHeight(120)

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.append(f"[{ts}] {message}")
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())
```

---

## Task 11: Billing header widget

**Files:**
- Create: `app/ui/billing_header.py`

- [ ] **Step 1: Implement BillingHeader**

```python
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel
from app import theme
from app.billing import burn_rate, autonomy_hours
from app.models import Instance, UserInfo


class BillingHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(24)
        self.balance_lbl = QLabel("💰 Saldo: —")
        self.balance_lbl.setObjectName("h2")
        self.burn_lbl = QLabel("⚡ Gastando: $0.00/h")
        self.burn_lbl.setObjectName("h2")
        self.autonomy_lbl = QLabel("⏱ Autonomia: —")
        self.autonomy_lbl.setObjectName("h2")
        top_row.addWidget(self.balance_lbl)
        top_row.addWidget(self.burn_lbl)
        top_row.addWidget(self.autonomy_lbl)
        top_row.addStretch()

        self.today_lbl = QLabel("📊 Gasto hoje: $0.00")
        self.today_lbl.setObjectName("secondary")

        outer.addLayout(top_row)
        outer.addWidget(self.today_lbl)

    def update_values(self, user: UserInfo | None, instances: list[Instance], today_spend: float):
        if user is None:
            self.balance_lbl.setText("💰 Saldo: —")
            self.balance_lbl.setStyleSheet("")
        else:
            self.balance_lbl.setText(f"💰 Saldo: ${user.balance:.2f}")

        burn = burn_rate(instances)
        self.burn_lbl.setText(f"⚡ Gastando: ${burn:.2f}/h")

        hours = autonomy_hours(user.balance if user else 0.0, burn)
        if hours is None:
            self.autonomy_lbl.setText("⏱ Autonomia: —")
            self.autonomy_lbl.setStyleSheet("")
        else:
            self.autonomy_lbl.setText(f"⏱ Autonomia: ~{hours:.0f}h")
            color = theme.autonomy_color(hours)
            self.autonomy_lbl.setStyleSheet(f"color: {color};")
            self.balance_lbl.setStyleSheet(f"color: {color};")

        self.today_lbl.setText(f"📊 Gasto hoje: ${today_spend:.2f}")
```

---

## Task 12: Instance card widget

**Files:**
- Create: `app/ui/instance_card.py`

- [ ] **Step 1: Implement InstanceCard**

```python
from __future__ import annotations
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt
from app import theme
from app.models import Instance, InstanceState, TunnelStatus
from app.ui.metric_bar import MetricBar


STATE_LABELS = {
    InstanceState.RUNNING: ("● Conectado", theme.SUCCESS),
    InstanceState.STOPPED: ("○ Desativada", theme.TEXT_SECONDARY),
    InstanceState.STARTING: ("◌ Ativando...", theme.WARNING),
    InstanceState.STOPPING: ("◌ Desativando...", theme.WARNING),
    InstanceState.UNKNOWN: ("? Desconhecido", theme.TEXT_SECONDARY),
}

TUNNEL_LABELS = {
    TunnelStatus.DISCONNECTED: ("● Desconectado", theme.TEXT_SECONDARY),
    TunnelStatus.CONNECTING: ("◌ Conectando...", theme.WARNING),
    TunnelStatus.CONNECTED: ("● Conectado", theme.SUCCESS),
    TunnelStatus.FAILED: ("● Falha de conexão", theme.DANGER),
}


def _format_duration(seconds: int | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


class InstanceCard(QFrame):
    activate_requested = Signal(int)
    deactivate_requested = Signal(int)
    reconnect_requested = Signal(int)
    disconnect_requested = Signal(int)
    open_terminal_requested = Signal(int)
    copy_endpoint_requested = Signal(int)

    def __init__(self, instance: Instance, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.instance = instance
        self.tunnel_status = TunnelStatus.DISCONNECTED
        self.local_port = 11434

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        # Header row: status + gpu
        header = QHBoxLayout()
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("h2")
        self.gpu_lbl = QLabel()
        self.gpu_lbl.setObjectName("secondary")
        self.gpu_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.status_lbl)
        header.addStretch()
        header.addWidget(self.gpu_lbl)
        lay.addLayout(header)

        self.subtitle_lbl = QLabel()
        self.subtitle_lbl.setObjectName("secondary")
        lay.addWidget(self.subtitle_lbl)

        # Metrics container (hidden when not running)
        self.metrics_container = QFrame()
        mlay = QVBoxLayout(self.metrics_container)
        mlay.setContentsMargins(0, 6, 0, 6)
        mlay.setSpacing(6)
        self.gpu_bar = MetricBar("GPU")
        self.cpu_bar = MetricBar("CPU")
        self.ram_bar = MetricBar("RAM")
        self.disk_bar = MetricBar("Disco")
        self.net_lbl = QLabel("Rede   ↓ — / ↑ —")
        self.net_lbl.setObjectName("secondary")
        mlay.addWidget(self.gpu_bar)
        mlay.addWidget(self.cpu_bar)
        mlay.addWidget(self.ram_bar)
        mlay.addWidget(self.disk_bar)
        mlay.addWidget(self.net_lbl)
        lay.addWidget(self.metrics_container)

        # Endpoint row
        self.endpoint_row = QHBoxLayout()
        self.endpoint_lbl = QLabel("")
        self.endpoint_lbl.setObjectName("mono")
        self.endpoint_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.copy_btn = QPushButton("Copiar")
        self.copy_btn.setObjectName("secondary")
        self.copy_btn.clicked.connect(lambda: self.copy_endpoint_requested.emit(self.instance.id))
        self.endpoint_row.addWidget(self.endpoint_lbl)
        self.endpoint_row.addStretch()
        self.endpoint_row.addWidget(self.copy_btn)
        self.endpoint_wrap = QFrame()
        self.endpoint_wrap.setLayout(self.endpoint_row)
        lay.addWidget(self.endpoint_wrap)

        # Action buttons
        actions = QHBoxLayout()
        self.primary_btn = QPushButton()
        self.primary_btn.clicked.connect(self._on_primary_click)
        self.terminal_btn = QPushButton("Abrir Terminal")
        self.terminal_btn.setObjectName("secondary")
        self.terminal_btn.clicked.connect(lambda: self.open_terminal_requested.emit(self.instance.id))
        self.disconnect_btn = QPushButton("Desconectar")
        self.disconnect_btn.setObjectName("secondary")
        self.disconnect_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.instance.id))
        self.deactivate_btn = QPushButton("Desativar")
        self.deactivate_btn.setObjectName("danger")
        self.deactivate_btn.clicked.connect(lambda: self.deactivate_requested.emit(self.instance.id))
        actions.addWidget(self.primary_btn)
        actions.addWidget(self.terminal_btn)
        actions.addWidget(self.disconnect_btn)
        actions.addStretch()
        actions.addWidget(self.deactivate_btn)
        lay.addLayout(actions)

        self.update_from(instance, self.tunnel_status, self.local_port)

    def _on_primary_click(self):
        if self.instance.state == InstanceState.STOPPED:
            self.activate_requested.emit(self.instance.id)
        elif self.tunnel_status == TunnelStatus.FAILED:
            self.reconnect_requested.emit(self.instance.id)
        elif self.tunnel_status == TunnelStatus.DISCONNECTED and self.instance.state == InstanceState.RUNNING:
            self.reconnect_requested.emit(self.instance.id)

    def update_from(self, inst: Instance, tunnel_status: TunnelStatus, local_port: int):
        self.instance = inst
        self.tunnel_status = tunnel_status
        self.local_port = local_port

        # Header
        if inst.state == InstanceState.RUNNING:
            label, color = TUNNEL_LABELS[tunnel_status]
        else:
            label, color = STATE_LABELS[inst.state]
        self.status_lbl.setText(label)
        self.status_lbl.setStyleSheet(f"color: {color};")
        self.gpu_lbl.setText(f"{inst.num_gpus}× {inst.gpu_name} · {inst.gpu_ram_gb:.0f} GB VRAM")

        parts = []
        if inst.image:
            parts.append(inst.image)
        parts.append(f"${inst.dph:.2f}/h")
        if inst.state == InstanceState.RUNNING and inst.duration_seconds:
            parts.append(f"ativa há {_format_duration(inst.duration_seconds)}")
        self.subtitle_lbl.setText(" · ".join(parts))

        # Metrics
        is_running = inst.state == InstanceState.RUNNING
        self.metrics_container.setVisible(is_running)
        if is_running:
            gpu_text = None
            if inst.gpu_util is not None:
                temp = f"  {inst.gpu_temp:.0f}°C" if inst.gpu_temp is not None else ""
                gpu_text = f"{inst.gpu_util:.0f}%{temp}"
            self.gpu_bar.set_value(inst.gpu_util, gpu_text)
            self.cpu_bar.set_value(inst.cpu_util)
            if inst.ram_total_gb and inst.ram_used_gb is not None:
                pct = (inst.ram_used_gb / inst.ram_total_gb) * 100
                self.ram_bar.set_value(pct, f"{pct:.0f}% ({inst.ram_used_gb:.0f} / {inst.ram_total_gb:.0f} GB)")
            else:
                self.ram_bar.set_value(None)
            self.disk_bar.set_value(inst.disk_util)
            down = f"{inst.inet_down_mbps:.1f}" if inst.inet_down_mbps is not None else "—"
            up = f"{inst.inet_up_mbps:.1f}" if inst.inet_up_mbps is not None else "—"
            self.net_lbl.setText(f"Rede   ↓ {down} Mbps / ↑ {up} Mbps")

        # Endpoint row
        show_endpoint = is_running and tunnel_status == TunnelStatus.CONNECTED
        self.endpoint_wrap.setVisible(show_endpoint)
        if show_endpoint:
            self.endpoint_lbl.setText(f"🔗 http://127.0.0.1:{local_port}")

        # Buttons
        self._update_buttons()

    def _update_buttons(self):
        state = self.instance.state
        tunnel = self.tunnel_status

        if state == InstanceState.STOPPED:
            self.primary_btn.setText("Ativar")
            self.primary_btn.setVisible(True)
            self.primary_btn.setEnabled(True)
            self.terminal_btn.setVisible(False)
            self.disconnect_btn.setVisible(False)
            self.deactivate_btn.setVisible(False)
        elif state in (InstanceState.STARTING, InstanceState.STOPPING):
            self.primary_btn.setText("Aguarde...")
            self.primary_btn.setVisible(True)
            self.primary_btn.setEnabled(False)
            self.terminal_btn.setVisible(False)
            self.disconnect_btn.setVisible(False)
            self.deactivate_btn.setVisible(True)
            self.deactivate_btn.setEnabled(False)
        else:  # RUNNING
            self.terminal_btn.setVisible(True)
            self.deactivate_btn.setVisible(True)
            self.deactivate_btn.setEnabled(True)
            if tunnel == TunnelStatus.CONNECTED:
                self.primary_btn.setVisible(False)
                self.disconnect_btn.setVisible(True)
            elif tunnel == TunnelStatus.CONNECTING:
                self.primary_btn.setText("Conectando...")
                self.primary_btn.setVisible(True)
                self.primary_btn.setEnabled(False)
                self.disconnect_btn.setVisible(False)
            elif tunnel == TunnelStatus.FAILED:
                self.primary_btn.setText("Tentar novamente")
                self.primary_btn.setVisible(True)
                self.primary_btn.setEnabled(True)
                self.disconnect_btn.setVisible(False)
            else:  # DISCONNECTED
                self.primary_btn.setText("Reconectar")
                self.primary_btn.setVisible(True)
                self.primary_btn.setEnabled(True)
                self.disconnect_btn.setVisible(False)
```

---

## Task 13: Workers (list + actions)

**Files:**
- Create: `app/workers/list_worker.py`
- Create: `app/workers/action_worker.py`
- Create: `app/workers/tunnel_starter.py`

- [ ] **Step 1: Implement list_worker**

```python
# app/workers/list_worker.py
from __future__ import annotations
from PySide6.QtCore import QObject, QTimer, Signal, Slot, QThread
from app.services.vast_service import VastService, VastAuthError, VastNetworkError
from app.models import Instance, UserInfo


class ListWorker(QObject):
    refreshed = Signal(list, object)  # list[Instance], UserInfo | None
    failed = Signal(str, str)  # kind, message

    def __init__(self, service: VastService):
        super().__init__()
        self.service = service

    @Slot()
    def refresh(self):
        try:
            user = self.service.get_user_info()
            insts = self.service.list_instances()
            self.refreshed.emit(insts, user)
        except VastAuthError as e:
            self.failed.emit("auth", str(e))
        except VastNetworkError as e:
            self.failed.emit("network", str(e))
        except Exception as e:
            self.failed.emit("unknown", str(e))
```

- [ ] **Step 2: Implement action_worker**

```python
# app/workers/action_worker.py
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.services.vast_service import VastService


class ActionWorker(QObject):
    finished = Signal(int, str, bool, str)  # instance_id, action, ok, message

    def __init__(self, service: VastService):
        super().__init__()
        self.service = service

    @Slot(int)
    def start(self, instance_id: int):
        try:
            self.service.start_instance(instance_id)
            self.finished.emit(instance_id, "start", True, "Ativação solicitada")
        except Exception as e:
            self.finished.emit(instance_id, "start", False, str(e))

    @Slot(int)
    def stop(self, instance_id: int):
        try:
            self.service.stop_instance(instance_id)
            self.finished.emit(instance_id, "stop", True, "Desativação solicitada")
        except Exception as e:
            self.finished.emit(instance_id, "stop", False, str(e))
```

- [ ] **Step 3: Implement tunnel_starter (waits for instance to be running, then opens tunnel, then waits for local port)**

```python
# app/workers/tunnel_starter.py
from __future__ import annotations
import time
from PySide6.QtCore import QObject, Signal, Slot
from app.services.vast_service import VastService
from app.services.ssh_service import SSHService, wait_for_local_port
from app.models import InstanceState, TunnelStatus


class TunnelStarter(QObject):
    status_changed = Signal(int, str, str)  # instance_id, TunnelStatus.value, message

    def __init__(self, vast: VastService, ssh: SSHService):
        super().__init__()
        self.vast = vast
        self.ssh = ssh

    @Slot(int, int)
    def connect(self, instance_id: int, local_port: int):
        self.status_changed.emit(instance_id, TunnelStatus.CONNECTING.value, "Aguardando instância ficar pronta...")

        # 1. Poll until RUNNING with ssh info (90s max)
        deadline = time.time() + 90
        inst = None
        while time.time() < deadline:
            try:
                all_instances = self.vast.list_instances()
                inst = next((i for i in all_instances if i.id == instance_id), None)
                if inst and inst.state == InstanceState.RUNNING and inst.ssh_host and inst.ssh_port:
                    break
            except Exception as e:
                self.status_changed.emit(instance_id, TunnelStatus.FAILED.value, f"Erro: {e}")
                return
            time.sleep(3)

        if not inst or inst.state != InstanceState.RUNNING or not inst.ssh_host or not inst.ssh_port:
            self.status_changed.emit(instance_id, TunnelStatus.FAILED.value, "Timeout esperando instância ficar pronta")
            return

        self.status_changed.emit(instance_id, TunnelStatus.CONNECTING.value, f"Estabelecendo túnel em {inst.ssh_host}:{inst.ssh_port}...")

        # 2. Start tunnel process
        try:
            handle = self.ssh.start_tunnel(instance_id, inst.ssh_host, inst.ssh_port, local_port)
        except Exception as e:
            self.status_changed.emit(instance_id, TunnelStatus.FAILED.value, f"Falha ao iniciar SSH: {e}")
            return

        # 3. Wait for local port to accept connections
        if not wait_for_local_port(local_port, timeout=25.0):
            # Grab any stderr for diagnostics
            stderr_msg = ""
            try:
                if handle.process.poll() is not None:
                    stderr_msg = (handle.process.stderr.read() or "")[:400]
            except Exception:
                pass
            self.ssh.stop_tunnel(instance_id)
            self.status_changed.emit(instance_id, TunnelStatus.FAILED.value, f"Porta local não respondeu. {stderr_msg}")
            return

        self.status_changed.emit(instance_id, TunnelStatus.CONNECTED.value, f"Conectado em 127.0.0.1:{local_port}")
```

---

## Task 14: Settings dialog

**Files:**
- Create: `app/ui/settings_dialog.py`

- [ ] **Step 1: Implement SettingsDialog**

```python
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QFormLayout,
)
from PySide6.QtCore import Qt, QThread, Signal
from app.models import AppConfig
from app.services.vast_service import VastService, VastAuthError


class SettingsDialog(QDialog):
    saved = Signal(object)  # AppConfig

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.setMinimumWidth(460)
        self.config = config

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel("Configurações")
        title.setObjectName("h1")
        lay.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.api_key_input = QLineEdit(config.api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("cole sua Vast.ai API key")
        form.addRow("API Key:", self.api_key_input)

        self.interval_input = QComboBox()
        self.interval_input.addItems(["10", "30", "60"])
        self.interval_input.setCurrentText(str(config.refresh_interval_seconds))
        form.addRow("Intervalo de atualização (s):", self.interval_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(config.default_tunnel_port)
        form.addRow("Porta local padrão:", self.port_input)

        self.terminal_input = QComboBox()
        self.terminal_input.addItems(["auto", "wt", "cmd", "powershell"])
        self.terminal_input.setCurrentText(config.terminal_preference)
        form.addRow("Terminal preferido:", self.terminal_input)

        self.auto_connect_input = QCheckBox("Conectar automaticamente ao ativar")
        self.auto_connect_input.setChecked(config.auto_connect_on_activate)
        form.addRow("", self.auto_connect_input)

        lay.addLayout(form)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        lay.addWidget(self.status_lbl)

        btns = QHBoxLayout()
        self.test_btn = QPushButton("Testar conexão")
        self.test_btn.setObjectName("secondary")
        self.test_btn.clicked.connect(self._on_test)
        self.save_btn = QPushButton("Salvar")
        self.save_btn.clicked.connect(self._on_save)
        btns.addWidget(self.test_btn)
        btns.addStretch()
        btns.addWidget(self.save_btn)
        lay.addLayout(btns)

    def _current_config(self) -> AppConfig:
        return AppConfig(
            api_key=self.api_key_input.text().strip(),
            refresh_interval_seconds=int(self.interval_input.currentText()),
            default_tunnel_port=self.port_input.value(),
            terminal_preference=self.terminal_input.currentText(),
            auto_connect_on_activate=self.auto_connect_input.isChecked(),
        )

    def _on_test(self):
        from app import theme
        cfg = self._current_config()
        if not cfg.api_key:
            self._set_status("Cole sua API key primeiro.", theme.WARNING)
            return
        self.status_lbl.setText("Testando...")
        self.test_btn.setEnabled(False)
        try:
            svc = VastService(cfg.api_key)
            user = svc.test_connection()
            self._set_status(f"✓ Conectado. Saldo atual: ${user.balance:.2f}", theme.SUCCESS)
        except VastAuthError:
            self._set_status("✗ API key inválida.", theme.DANGER)
        except Exception as e:
            self._set_status(f"✗ Falha: {e}", theme.DANGER)
        finally:
            self.test_btn.setEnabled(True)

    def _on_save(self):
        from app import theme
        cfg = self._current_config()
        if not cfg.api_key:
            self._set_status("API key é obrigatória.", theme.DANGER)
            return
        self.saved.emit(cfg)
        self.accept()

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {color}; font-weight: 500;")
```

---

## Task 15: Main window

**Files:**
- Create: `app/ui/main_window.py`

- [ ] **Step 1: Implement MainWindow**

```python
from __future__ import annotations
from datetime import datetime
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QComboBox,
)
from app import theme
from app.config import ConfigStore
from app.models import AppConfig, Instance, InstanceState, TunnelStatus, UserInfo
from app.services.vast_service import VastService
from app.services.ssh_service import SSHService, build_ssh_command, build_tunnel_command
from app.workers.list_worker import ListWorker
from app.workers.action_worker import ActionWorker
from app.workers.tunnel_starter import TunnelStarter
from app.billing import DailySpendTracker
from app.ui.billing_header import BillingHeader
from app.ui.instance_card import InstanceCard
from app.ui.log_panel import LogPanel
from app.ui.settings_dialog import SettingsDialog
from app.ui.toast import Toast


class MainWindow(QMainWindow):
    _trigger_refresh = Signal()
    _trigger_start = Signal(int)
    _trigger_stop = Signal(int)
    _trigger_connect = Signal(int, int)

    def __init__(self, config_store: ConfigStore):
        super().__init__()
        self.setWindowTitle("Vast.ai Manager")
        self.resize(920, 760)

        self.config_store = config_store
        self.config = config_store.load()
        self.vast: VastService | None = None
        self.ssh = SSHService()
        self.tracker = DailySpendTracker()
        self.cards: dict[int, InstanceCard] = {}
        self.tunnel_states: dict[int, TunnelStatus] = {}
        self.last_instances: list[Instance] = []

        self._build_ui()
        self._init_workers()

        if not self.config.api_key:
            QTimer.singleShot(100, self._open_settings_initial)
        else:
            self._bootstrap_service()

    # ---------- UI ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # Top bar
        top_bar = QHBoxLayout()
        title = QLabel("Vast.ai Manager")
        title.setObjectName("h1")
        top_bar.addWidget(title)
        top_bar.addStretch()
        self.active_lbl = QLabel("0 ativas")
        self.active_lbl.setObjectName("secondary")
        top_bar.addWidget(self.active_lbl)
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("secondary")
        self.settings_btn.setFixedWidth(40)
        self.settings_btn.clicked.connect(self._open_settings)
        top_bar.addWidget(self.settings_btn)
        self.refresh_interval_combo = QComboBox()
        self.refresh_interval_combo.addItems(["↺ 10s", "↺ 30s", "↺ 60s", "↺ off"])
        idx_map = {10: 0, 30: 1, 60: 2}
        self.refresh_interval_combo.setCurrentIndex(idx_map.get(self.config.refresh_interval_seconds, 1))
        self.refresh_interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        top_bar.addWidget(self.refresh_interval_combo)
        self.manual_refresh_btn = QPushButton("Atualizar")
        self.manual_refresh_btn.setObjectName("secondary")
        self.manual_refresh_btn.clicked.connect(lambda: self._trigger_refresh.emit())
        top_bar.addWidget(self.manual_refresh_btn)
        root.addLayout(top_bar)

        self.billing = BillingHeader()
        root.addWidget(self.billing)

        # Scrollable instance list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(12)
        self.empty_lbl = QLabel("Conecte-se para ver suas instâncias.")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setObjectName("secondary")
        self.list_layout.addWidget(self.empty_lbl)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        # Log
        self.log = LogPanel()
        root.addWidget(self.log)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(lambda: self._trigger_refresh.emit())

    # ---------- Workers ----------

    def _init_workers(self):
        self.list_thread = QThread()
        self.action_thread = QThread()
        self.tunnel_thread = QThread()

        self.list_worker: ListWorker | None = None
        self.action_worker: ActionWorker | None = None
        self.tunnel_starter: TunnelStarter | None = None

    def _bootstrap_service(self):
        self.vast = VastService(self.config.api_key)
        # Spin up fresh workers bound to the new service
        self._destroy_workers()
        self.list_worker = ListWorker(self.vast)
        self.list_worker.moveToThread(self.list_thread)
        self.list_worker.refreshed.connect(self._on_refreshed)
        self.list_worker.failed.connect(self._on_refresh_failed)
        self._trigger_refresh.connect(self.list_worker.refresh)
        self.list_thread.start()

        self.action_worker = ActionWorker(self.vast)
        self.action_worker.moveToThread(self.action_thread)
        self.action_worker.finished.connect(self._on_action_done)
        self._trigger_start.connect(self.action_worker.start)
        self._trigger_stop.connect(self.action_worker.stop)
        self.action_thread.start()

        self.tunnel_starter = TunnelStarter(self.vast, self.ssh)
        self.tunnel_starter.moveToThread(self.tunnel_thread)
        self.tunnel_starter.status_changed.connect(self._on_tunnel_status)
        self._trigger_connect.connect(self.tunnel_starter.connect)
        self.tunnel_thread.start()

        self._apply_interval()
        self._trigger_refresh.emit()

    def _destroy_workers(self):
        for t in (self.list_thread, self.action_thread, self.tunnel_thread):
            if t.isRunning():
                t.quit()
                t.wait(1500)
        self.list_thread = QThread()
        self.action_thread = QThread()
        self.tunnel_thread = QThread()

    def _apply_interval(self):
        secs = self.config.refresh_interval_seconds
        if secs <= 0:
            self.refresh_timer.stop()
        else:
            self.refresh_timer.start(secs * 1000)

    def _on_interval_changed(self, idx: int):
        mapping = {0: 10, 1: 30, 2: 60, 3: 0}
        self.config.refresh_interval_seconds = mapping[idx]
        self.config_store.save(self.config)
        self._apply_interval()

    # ---------- Settings ----------

    def _open_settings_initial(self):
        dlg = SettingsDialog(self.config, self)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, cfg: AppConfig):
        changed_key = cfg.api_key != self.config.api_key
        self.config = cfg
        self.config_store.save(cfg)
        self.log.log("Configurações salvas.")
        if changed_key:
            self._bootstrap_service()
        else:
            self._apply_interval()

    # ---------- Refresh ----------

    def _on_refreshed(self, instances: list[Instance], user: UserInfo | None):
        self.last_instances = instances
        for inst in instances:
            self.tracker.update(inst)
        self._rebuild_cards(instances)
        self.billing.update_values(user, instances, self.tracker.today_spend())
        active = sum(1 for i in instances if i.state == InstanceState.RUNNING)
        self.active_lbl.setText(f"{active} ativa{'s' if active != 1 else ''}")
        self._check_tunnels_health()

    def _on_refresh_failed(self, kind: str, message: str):
        self.log.log(f"Erro ({kind}): {message}")
        if kind == "auth":
            Toast(self, "API key inválida", "error")
            self._open_settings()
        elif kind == "network":
            Toast(self, "Sem conexão com Vast.ai", "warning")
        else:
            Toast(self, f"Falha: {message[:80]}", "error")

    def _rebuild_cards(self, instances: list[Instance]):
        current_ids = {i.id for i in instances}
        # Remove stale
        for iid in list(self.cards.keys()):
            if iid not in current_ids:
                card = self.cards.pop(iid)
                card.setParent(None)
                card.deleteLater()
                self.tunnel_states.pop(iid, None)

        # Update / create
        if instances:
            self.empty_lbl.setVisible(False)
        else:
            self.empty_lbl.setVisible(True)

        for inst in instances:
            tunnel_status = self.tunnel_states.get(inst.id, TunnelStatus.DISCONNECTED)
            if inst.id in self.cards:
                self.cards[inst.id].update_from(inst, tunnel_status, self.config.default_tunnel_port)
            else:
                card = InstanceCard(inst)
                card.activate_requested.connect(self._on_activate)
                card.deactivate_requested.connect(self._on_deactivate)
                card.reconnect_requested.connect(self._on_reconnect)
                card.disconnect_requested.connect(self._on_disconnect)
                card.open_terminal_requested.connect(self._on_open_terminal)
                card.copy_endpoint_requested.connect(self._on_copy_endpoint)
                card.update_from(inst, tunnel_status, self.config.default_tunnel_port)
                # Insert before the stretch (last item)
                self.list_layout.insertWidget(self.list_layout.count() - 1, card)
                self.cards[inst.id] = card

    # ---------- Actions ----------

    def _find_instance(self, iid: int) -> Instance | None:
        return next((i for i in self.last_instances if i.id == iid), None)

    def _on_activate(self, iid: int):
        self.log.log(f"Ativando instância {iid}...")
        self._trigger_start.emit(iid)

    def _on_deactivate(self, iid: int):
        reply = QMessageBox.question(
            self, "Desativar instância",
            "Tem certeza? A máquina será parada e a conexão encerrada.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.ssh.stop_tunnel(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self.log.log(f"Desativando instância {iid}...")
        self._trigger_stop.emit(iid)

    def _on_reconnect(self, iid: int):
        self._start_tunnel_for(iid)

    def _on_disconnect(self, iid: int):
        self.ssh.stop_tunnel(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self.log.log(f"Túnel {iid} encerrado.")
        self._refresh_card(iid)

    def _on_open_terminal(self, iid: int):
        inst = self._find_instance(iid)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            Toast(self, "SSH indisponível para esta instância", "warning")
            return
        try:
            self.ssh.open_terminal(inst.ssh_host, inst.ssh_port, self.config.terminal_preference)
            self.log.log(f"Terminal aberto para {inst.ssh_host}:{inst.ssh_port}")
        except FileNotFoundError:
            Toast(self, "Terminal não encontrado. Verifique se o Windows Terminal está instalado.", "error")
        except Exception as e:
            Toast(self, f"Falha ao abrir terminal: {e}", "error")

    def _on_copy_endpoint(self, iid: int):
        clip = QGuiApplication.clipboard()
        clip.setText(f"http://127.0.0.1:{self.config.default_tunnel_port}")
        Toast(self, "Endereço copiado", "success", duration_ms=1500)

    def _on_action_done(self, iid: int, action: str, ok: bool, msg: str):
        if ok:
            self.log.log(f"✓ {action} #{iid}: {msg}")
            if action == "start" and self.config.auto_connect_on_activate:
                self._start_tunnel_for(iid)
            Toast(self, msg, "success")
        else:
            self.log.log(f"✗ {action} #{iid}: {msg}")
            Toast(self, f"Falha: {msg[:80]}", "error")
        self._trigger_refresh.emit()

    def _start_tunnel_for(self, iid: int):
        self.tunnel_states[iid] = TunnelStatus.CONNECTING
        self._refresh_card(iid)
        self.log.log(f"Conectando túnel para instância {iid}...")
        self._trigger_connect.emit(iid, self.config.default_tunnel_port)

    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        self.tunnel_states[iid] = TunnelStatus(status)
        self.log.log(f"Túnel #{iid}: {msg}")
        self._refresh_card(iid)
        if self.tunnel_states[iid] == TunnelStatus.CONNECTED:
            Toast(self, f"Conectado em http://127.0.0.1:{self.config.default_tunnel_port}", "success")
        elif self.tunnel_states[iid] == TunnelStatus.FAILED:
            Toast(self, "Falha na conexão", "error")

    def _refresh_card(self, iid: int):
        card = self.cards.get(iid)
        inst = self._find_instance(iid)
        if card and inst:
            card.update_from(inst, self.tunnel_states.get(iid, TunnelStatus.DISCONNECTED),
                             self.config.default_tunnel_port)

    def _check_tunnels_health(self):
        for iid, status in list(self.tunnel_states.items()):
            if status == TunnelStatus.CONNECTED:
                handle = self.ssh.get(iid)
                if handle is None or not handle.alive():
                    self.tunnel_states[iid] = TunnelStatus.FAILED
                    self.log.log(f"Túnel #{iid} caiu.")
                    self._refresh_card(iid)

    # ---------- Cleanup ----------

    def closeEvent(self, event):
        self.ssh.stop_all()
        for t in (self.list_thread, self.action_thread, self.tunnel_thread):
            if t.isRunning():
                t.quit()
                t.wait(1500)
        super().closeEvent(event)
```

---

## Task 16: Entry point

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement main.py**

```python
from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from app.config import ConfigStore
from app import theme
from app.ui.main_window import MainWindow


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
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

- [ ] **Step 2: Smoke test**

Run: `python main.py`
Expected: Window opens; if no API key, Settings dialog appears.

---

## Task 17: Finalize README with full docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write complete README**

Include: purpose, install steps, run steps, dependencies, config file location, packaging instructions (PyInstaller), limitations, next steps.

---

## Self-review (against spec)

| Spec section | Task(s) |
|---|---|
| Purpose | covered by all |
| Stack | Task 1 |
| Architecture & file structure | Task 1, 15 |
| Models | Task 2 |
| Key flows (activate+auto-connect, deactivate, open terminal, tunnel health, refresh, today spend) | Tasks 13, 15, 6 |
| UI visual (palette, header, cards, empty, toasts) | Tasks 7, 9, 11, 12, 15 |
| Error handling matrix | Tasks 13, 15 (_on_refresh_failed, _on_open_terminal) |
| Config file | Task 3 |
| Dependencies | Task 1 |
| Non-goals | respected (no create/destroy/offers) |
| Success criteria | all addressable after Task 17 smoke test |

No placeholders. Types consistent across tasks (`Instance`, `TunnelStatus`, `AppConfig` used identically).
