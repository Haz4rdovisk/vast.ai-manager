# Vast.ai Manager — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Target platform:** Windows 11 (primary); Linux/macOS best-effort

---

## 1. Purpose

A local desktop GUI to manage *existing* Vast.ai instances. Out of scope: creating instances, browsing offers, billing history, destroying instances.

The user should be able to:

- Save their API key once
- See all their instances with live status and metrics
- Activate / deactivate instances
- Auto-connect an SSH tunnel when an instance becomes active
- Open an interactive terminal to the instance
- See credit balance, current burn rate, and daily spend at a glance

---

## 2. Stack

| Layer | Choice |
|---|---|
| Language | Python 3.10+ |
| GUI | PySide6 (Qt 6) |
| Vast API | `vastai` Python SDK (primary), CLI fallback only if a gap appears |
| Icons | `qtawesome` |
| SSH | System `ssh.exe` (Windows built-in OpenSSH), spawned via `subprocess` |
| Terminal for interactive SSH | Windows Terminal (`wt.exe`) → `cmd.exe` fallback |
| Config storage | JSON file at `%USERPROFILE%\.vastai-app\config.json` |

No Electron. No web backend. No custom crypto (v1). No sparkline libs — native QPainter if needed.

---

## 3. Architecture

Layered, with strict one-way dataflow: **UI → Workers (QThread) → Services → SDK/subprocess**. Results return through Qt signals. UI never blocks.

```
vastai-app/
├── main.py
├── requirements.txt
├── README.md
├── docs/superpowers/specs/2026-04-14-vastai-manager-design.md
└── app/
    ├── __init__.py
    ├── config.py
    ├── models.py
    ├── theme.py
    ├── services/
    │   ├── __init__.py
    │   ├── vast_service.py
    │   └── ssh_service.py
    ├── workers/
    │   ├── __init__.py
    │   ├── list_worker.py
    │   ├── action_worker.py
    │   └── tunnel_watcher.py
    └── ui/
        ├── __init__.py
        ├── main_window.py
        ├── settings_dialog.py
        ├── billing_header.py
        ├── instance_card.py
        ├── metric_bar.py
        ├── toast.py
        └── log_panel.py
```

### Responsibilities per unit

| Unit | Responsibility |
|---|---|
| `config.py` | Read/write JSON config. Schema migrations. Path discovery. |
| `models.py` | `@dataclass Instance`, `@dataclass UserInfo`, `Enum TunnelStatus`, `Enum InstanceState`. |
| `theme.py` | QSS stylesheet + palette constants + status color helpers. |
| `services/vast_service.py` | Wraps `VastAI` SDK. Methods: `list_instances`, `start_instance`, `stop_instance`, `get_user_info`, `test_connection`. Raises typed exceptions. |
| `services/ssh_service.py` | Manages SSH subprocesses. Methods: `open_terminal(host, port)`, `start_tunnel(host, port, local_port)`, `stop_tunnel(instance_id)`, `is_tunnel_alive(instance_id)`, `wait_for_local_port(port, timeout)`. Holds a dict `{instance_id: Popen}`. |
| `workers/list_worker.py` | QThread that periodically calls `list_instances` + `get_user_info` and emits `refreshed(list, user_info)`. |
| `workers/action_worker.py` | One-shot QThread for start/stop actions. Emits `finished(instance_id, ok, message)`. |
| `workers/tunnel_watcher.py` | QThread that polls `ssh_service.is_tunnel_alive` per active tunnel, emits `status_changed(instance_id, status)`. |
| `ui/main_window.py` | QMainWindow. Holds billing header, scrollable instance list, log panel, refresh controls. |
| `ui/settings_dialog.py` | API key field + "Test connection" button + refresh interval + tunnel port default + terminal preference. |
| `ui/billing_header.py` | Widget showing balance, burn rate, autonomy, today's spend. |
| `ui/instance_card.py` | Widget for one instance. Renders state, metrics, endpoint, action buttons. |
| `ui/metric_bar.py` | Styled QProgressBar with dynamic color thresholds. |
| `ui/toast.py` | Floating non-blocking notification (bottom-right, auto-dismiss 3s). |
| `ui/log_panel.py` | Read-only QTextEdit with timestamped events, auto-scroll. |

---

## 4. Data Models

```python
class InstanceState(str, Enum):
    STOPPED = "stopped"          # actual_status in {"exited", "stopped"}
    STARTING = "starting"        # intended=running, actual!=running
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
    gpu_util: float | None       # 0-100
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
    dph: float                   # dollars per hour
    duration_seconds: int | None
    ssh_host: str | None
    ssh_port: int | None
    raw: dict                    # original payload for debug

@dataclass
class UserInfo:
    balance: float               # credit
    email: str | None

@dataclass
class AppConfig:
    api_key: str = ""
    refresh_interval_seconds: int = 30
    default_tunnel_port: int = 11434
    terminal_preference: str = "auto"   # "auto" | "wt" | "cmd" | "powershell"
    auto_connect_on_activate: bool = True
```

---

## 5. Key Flows

### 5.1 First run
1. App opens → config has empty `api_key` → show Settings dialog modally.
2. User pastes key → clicks **Testar conexão** → `vast_service.test_connection()` runs in a worker.
3. On success, save config, close dialog, trigger initial refresh.

### 5.2 Activate + auto-connect
1. User clicks **Ativar** on a stopped card.
2. Card transitions to `◌ Ativando...`.
3. `action_worker` calls `start_instance(id)`.
4. On success, `list_worker` polls every 3s (temporary boost) until `state==RUNNING` and `ssh_host` / `ssh_port` are populated. Max 90s.
5. Card transitions to `◌ Conectando...`.
6. `ssh_service.start_tunnel(host, port, local_port)` spawns `ssh -p PORT root@HOST -L LOCAL:127.0.0.1:LOCAL -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -N` in background.
7. `ssh_service.wait_for_local_port(local_port, timeout=20s)` polls with a TCP `connect()` on `127.0.0.1:LOCAL` until it succeeds.
8. On success, card shows `● Conectado` + endpoint. `tunnel_watcher` starts monitoring.
9. On failure: card shows `● Falha de conexão` with **[Tentar novamente]**. Log panel has stderr.

### 5.3 Deactivate
1. User clicks **Desativar** → confirmation modal.
2. If confirmed: stop tunnel (if any) → `action_worker` calls `stop_instance(id)` → card transitions to `◌ Desativando...` → eventually `○ Desativada`.

### 5.4 Open Terminal
1. User clicks **Abrir Terminal**.
2. `ssh_service.open_terminal(host, port)`:
   - If `terminal_preference == "auto"`: try `wt.exe new-tab -- ssh -p PORT root@HOST`. On FileNotFoundError, fall back to `cmd.exe /k ssh ...`.
   - If explicit preference, use it directly.
3. Never capture stdout/stderr — let the terminal own it. The user enters passphrase in the spawned window.

### 5.5 Tunnel health monitoring
- `tunnel_watcher` runs one thread that iterates over active tunnels every 5s.
- Per tunnel: if `Popen.poll()` is not None → tunnel died → emit `FAILED`. Card offers **[Reconectar]**.
- One automatic reconnect attempt per death. After the second death, require manual click.

### 5.6 Refresh cycle (metrics)
- `list_worker` calls `show_instances()` + `show_user()` at the configured interval (10/30/60s).
- Emits `refreshed(instances, user_info)` → main window updates cards in place (never rebuilds list DOM — just patches).
- Cards compute metric colors, update progress bars, update duration text.
- Billing header recomputes burn rate = `sum(i.dph for i in instances if i.state == RUNNING)`, autonomy = `balance / burn_rate`.

### 5.7 Today's spend (local approximation)
- In-memory accumulator keyed by instance id: `{id: {"last_seen_at": ts, "last_duration": sec, "spent_today": $}}`.
- On each refresh, delta = `(duration_now - duration_last) / 3600 * dph` added to `spent_today`.
- Reset at local midnight (check on each refresh — if date changed, zero it).
- Persist nothing. Restarting the app resets today's spend (documented limitation).

---

## 6. UI Visual Spec

### 6.1 Palette (dark theme)

| Role | Color |
|---|---|
| App background | `#1a1a2e` |
| Card background | `#16213e` |
| Card border | `#0f3460` |
| Accent (primary buttons) | `#6C63FF` |
| Accent hover | `#7D75FF` |
| Text primary | `#EAEAEA` |
| Text secondary | `#9AA0B4` |
| Success | `#00d26a` |
| Warning | `#ffc107` |
| Danger | `#f44336` |
| Info | `#3ea6ff` |
| Log background | `#0d0d1a` |

Font: Segoe UI (fallback: system sans). Monospace for log & endpoint: Consolas.

### 6.2 Billing header

```
💰 Saldo: $42.18    ⚡ Gastando: $0.70/h    ⏱ Autonomia: ~60h
📊 Gasto hoje: $3.24                                 2 ativas
```

Saldo color tiers:
- `autonomy > 24h`: success
- `6h..24h`: warning
- `< 6h`: danger
- `balance < $1`: danger + blinking + toast "Saldo baixo"

### 6.3 Instance card

Fixed header (state pill + gpu + ram) → subtitle (image · $/hr · uptime) → metrics grid (active cards only) → endpoint row (connected only) → action row.

Metric thresholds:
- 0–60%: success
- 60–85%: warning
- 85–100%: danger

GPU temp thresholds: `<70°C` success, `70–80°C` warning, `>80°C` danger.

### 6.4 Empty states

- **No API key:** big centered "Configurar API Key" button with 💡 hint.
- **No instances:** illustration (emoji OK for v1) + text "Você não tem instâncias. Crie uma pelo painel da Vast.ai."
- **Loading first fetch:** skeleton cards (3 placeholders with shimmer).

### 6.5 Toasts

Bottom-right. Auto-dismiss 3s. Stack vertically. Types: info, success, warning, error. Click to dismiss early.

---

## 7. Error Handling Matrix

| Situation | Behavior |
|---|---|
| API key invalid / 401 | Toast "API key inválida" → auto-open Settings with error banner |
| Network down | Toast "Sem conexão" → keep last known state → retry on next tick |
| `ssh.exe` not found on PATH | Toast "OpenSSH não instalado" + log link to `ms-settings:optionalfeatures` |
| `wt.exe` not found | Silent fallback to `cmd.exe` |
| Local tunnel port already in use | Toast "Porta N ocupada" + suggest changing in Settings |
| Tunnel subprocess dies | Status → FAILED, one auto-retry, then manual |
| `start_instance` returns ok but instance never reaches `running` in 90s | Status → FAILED with timeout message |
| Unknown field missing in SDK response | Use `None`, log once, don't crash |

All exceptions from services are caught at the worker boundary and converted to signals. Workers never let exceptions propagate into Qt.

---

## 8. Config File

**Path:** `%USERPROFILE%\.vastai-app\config.json`
**Created on:** first save
**Format:**
```json
{
  "api_key": "c8a3...",
  "refresh_interval_seconds": 30,
  "default_tunnel_port": 11434,
  "terminal_preference": "auto",
  "auto_connect_on_activate": true,
  "schema_version": 1
}
```

Permissions: default file permissions. No encryption in v1 (documented in README). `schema_version` reserved for future migrations.

---

## 9. Dependencies

```
PySide6>=6.6
vastai>=0.3
qtawesome>=1.2
```

Python 3.10+ required (for `|` in type hints, `match` optional).

---

## 10. Non-goals (explicit)

- Creating instances
- Searching offers
- Destroying instances
- Full billing history UI
- System tray (hook structure fine; implementation v2)
- Multiple local tunnel ports per instance simultaneously (one tunnel per instance in v1)
- Encrypted storage of API key (v2)
- Sparkline charts (v2)
- Mobile / remote access

---

## 11. Success Criteria

1. Fresh clone → `pip install -r requirements.txt` → `python main.py` opens a window.
2. User pastes API key, clicks "Testar conexão" → green feedback.
3. Instance list populates within 5s showing real data.
4. Click **Ativar** on a stopped instance → it transitions through `Ativando → Conectando → Conectado` automatically.
5. Endpoint `http://127.0.0.1:11434` is reachable from the host machine (or the chosen local port).
6. Metrics update at the configured interval without UI jank.
7. Billing header shows current balance, burn rate, and daily spend.
8. Closing the app cleanly terminates all tunnel subprocesses.

---

## 12. Open Questions (resolved during brainstorm)

- **Which SSH terminal on Windows?** Windows Terminal with `cmd.exe` fallback.
- **SDK vs CLI?** SDK as primary; CLI fallback is manual/ad-hoc, not automatic.
- **Configurable local tunnel port?** Yes, default 11434, persisted per-app (not per-instance in v1).
- **Auto-connect on activate?** Yes, controlled by `auto_connect_on_activate` flag (default true).
- **Daily spend source?** Client-side approximation. Documented limitation.

---

## 13. Next steps (post-design)

1. Write implementation plan via `writing-plans` skill.
2. Scaffold project files in order: config → models → services → workers → ui → main.
3. Manual smoke test with a real API key.
4. Write README with install / run / package instructions.
