"""SSH script builders for remote instance setup and control.
All functions return shell script strings — the caller runs them via SSHService.run_script()."""
from __future__ import annotations


_DETECTION_LOOP = r"""
LLAMA_PATH=""
for p in "/opt/llama.cpp/build/bin/llama-server" "/opt/llama.cpp/llama-server" "/usr/local/bin/llama-server" "/root/llama.cpp/build/bin/llama-server" "/workspace/llama.cpp/build/bin/llama-server"; do
    if [ -f "$p" ]; then
        LLAMA_PATH="$p"
        break
    fi
done
if [ -z "$LLAMA_PATH" ] && command -v llama-server &>/dev/null; then
    LLAMA_PATH=$(which llama-server)
fi
"""


def script_master_probe() -> str:
    """Unified probe for status, health and models in one SSH call."""
    return f"""
echo "===SETUP_START==="
# Check llmfit
if command -v llmfit &>/dev/null; then
    echo "LLMFIT_INSTALLED=yes"
    LLMFIT_VER=$(llmfit --version 2>/dev/null | head -1)
    echo "LLMFIT_VERSION=$LLMFIT_VER"
else
    echo "LLMFIT_INSTALLED=no"
fi

# Check if llmfit serve is responding via API
if curl -sf http://127.0.0.1:8787/health &>/dev/null; then
    echo "LLMFIT_SERVING=yes"
    SERVING=1
elif pgrep -f "llmfit serve" &>/dev/null; then
    echo "LLMFIT_SERVING=starting"
    SERVING=0
else
    echo "LLMFIT_SERVING=no"
    SERVING=0
fi

# Check llama.cpp
{_DETECTION_LOOP}

if [ -n "$LLAMA_PATH" ]; then
    echo "LLAMACPP_INSTALLED=yes"
    echo "LLAMACPP_PATH=$LLAMA_PATH"
else
    echo "LLAMACPP_INSTALLED=no"
    echo "LLAMACPP_PATH="
fi

# Check if llama-server is running
if pgrep -f "llama-server" &>/dev/null; then
    echo "LLAMA_RUNNING=yes"
    # Robust port/model extraction using ps
    RAW_CMD=$(ps -ww -fp $(pgrep -f "llama-server" | head -1) -o args= 2>/dev/null)
    echo "LLAMA_MODEL=$(echo "$RAW_CMD" | grep -oE '\\-m [^ ]+' | cut -d' ' -f2 | head -1)"
    echo "LLAMA_PORT=$(echo "$RAW_CMD" | grep -oE '\\-\\-port [0-9]+' | cut -d' ' -f2 | head -1 | grep -E '^[0-9]+$' || echo 11434)"
else
    echo "LLAMA_RUNNING=no"
fi

# Count GGUF models
MODEL_COUNT=$(find /workspace /models /root -type f -name '*.gguf' 2>/dev/null | wc -l)
echo "MODEL_COUNT=$MODEL_COUNT"
echo "===SETUP_END==="

echo "===MODELS_START==="
find /workspace /models /root -type f -name '*.gguf' 2>/dev/null | while read f; do
    SIZE=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
    echo "GGUF|$f|$SIZE"
done
echo "===MODELS_END==="

if [ "$SERVING" -eq 1 ]; then
    echo "===SYSTEM_START==="
    curl -s http://127.0.0.1:8787/system || echo "{{}}"
    echo "===SYSTEM_END==="
    
    echo "===RECOMMEND_START==="
    curl -s http://127.0.0.1:8787/models || echo "[]"
    echo "===RECOMMEND_END==="
fi

echo "===TELEMETRY_START==="
# 1. CPU Load & Cores
IDLE=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\\([0-9.]*\\)%* id.*/\\1/" | awk '{{print 100 - $1}}')
echo "CPU_LOAD=$IDLE"
echo "CPU_CORES=$(nproc 2>/dev/null || echo 0)"

# 2. RAM Usage
read TOTAL USED <<< $(free -m | awk '/Mem:/ {{print $2, $3}}')
PERCENT=$(awk "BEGIN {{print ($USED/$TOTAL)*100}}")
echo "RAM_TOTAL_MB=$TOTAL"
echo "RAM_USED_MB=$USED"
echo "RAM_PERCENT=$PERCENT"

# 3. GPU Metrics (if available)
if command -v nvidia-smi &>/dev/null; then
    METRICS=$(nvidia-smi --query-gpu=utilization.gpu,utilization.memory,temperature.gpu,memory.total,memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [ -n "$METRICS" ]; then
        IFS=', ' read GPU_UTIL VRAM_UTIL TEMP VRAM_TOTAL VRAM_USED <<< "$METRICS"
        echo "GPU_LOAD=$GPU_UTIL"
        echo "GPU_TEMP=$TEMP"
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        echo "GPU_NAME=${{GPU_NAME:-GPU}}"
        echo "VRAM_TOTAL_MB=$VRAM_TOTAL"
        echo "VRAM_USED_MB=$VRAM_USED"
        VRAM_PCT=$(awk "BEGIN {{print ($VRAM_USED/$VRAM_TOTAL)*100}}")
        echo "VRAM_PERCENT=$VRAM_PCT"
    fi
fi

# 4. Disk Usage (/workspace as reference)
read D_TOT D_USED D_PCT <<< $(df -m /workspace 2>/dev/null | tail -1 | awk '{{print $2, $3, $5}}' | sed 's/%//')
echo "DISK_TOTAL_MB=${{D_TOT:-0}}"
echo "DISK_USED_MB=${{D_USED:-0}}"
echo "DISK_PERCENT=${{D_PCT:-0}}"

# 5. Network Throughput (1s delta)
IFACE=$(ip route | grep default | awk '{{print $5}}' | head -1)
if [ -n "$IFACE" ]; then
    R1=$(cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null || echo 0)
    T1=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
    sleep 1
    R2=$(cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null || echo 0)
    T2=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
    echo "NET_RX_KBPS=$(( (R2 - R1) / 1024 ))"
    echo "NET_TX_KBPS=$(( (T2 - T1) / 1024 ))"
else
    echo "NET_RX_KBPS=0"
    echo "NET_TX_KBPS=0"
fi

# 6. Uptime
echo "UPTIME_SEC=$(awk '{{print int($1)}}' /proc/uptime)"
echo "===TELEMETRY_END==="
"""


def script_check_setup() -> str:
    """Probe what's installed on the instance. Outputs structured markers."""
    return f"""
echo "===PROBE_START==="
# Check llmfit
if command -v llmfit &>/dev/null; then
    echo "LLMFIT_INSTALLED=yes"
    LLMFIT_VER=$(llmfit --version 2>/dev/null | head -1)
    echo "LLMFIT_VERSION=$LLMFIT_VER"
else
    echo "LLMFIT_INSTALLED=no"
fi

# Check if llmfit serve is responding via API
if curl -sf http://127.0.0.1:8787/health &>/dev/null; then
    echo "LLMFIT_SERVING=yes"
elif pgrep -f "llmfit serve" &>/dev/null; then
    echo "LLMFIT_SERVING=starting"
else
    echo "LLMFIT_SERVING=no"
fi

# Check llama.cpp
{_DETECTION_LOOP}

if [ -n "$LLAMA_PATH" ]; then
    echo "LLAMACPP_INSTALLED=yes"
    echo "LLAMACPP_PATH=$LLAMA_PATH"
else
    echo "LLAMACPP_INSTALLED=no"
    echo "LLAMACPP_PATH="
fi

# Check if llama-server is running
if pgrep -f "llama-server" &>/dev/null; then
    echo "LLAMA_RUNNING=yes"
    LLAMA_MODEL=$(pgrep -fa "llama-server" | grep -oP '(?<=-m )\\S+' | head -1)
    echo "LLAMA_MODEL=$LLAMA_MODEL"
else
    echo "LLAMA_RUNNING=no"
    echo "LLAMA_MODEL="
fi

# Count GGUF models
MODEL_COUNT=$(find /workspace /models /root -type f -name '*.gguf' 2>/dev/null | wc -l)
echo "MODEL_COUNT=$MODEL_COUNT"
echo "===PROBE_END==="
"""


def parse_probe_output(output: str) -> dict:
    """Parse probe output into a dict."""
    result = {}
    for line in output.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("==="):
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def script_install_llmfit() -> str:
    """Install llmfit on remote instance."""
    return r"""
echo "Installing llmfit..."
curl -fsSL https://llmfit.axjns.dev/install.sh | sh
echo "INSTALL_LLMFIT_DONE"
llmfit --version 2>/dev/null || echo "INSTALL_LLMFIT_FAILED"
"""


def script_start_llmfit_serve() -> str:
    """Start llmfit serve in background with extreme persistence."""
    return r"""
# Kill existing llmfit serve if running
pkill -f "llmfit serve" 2>/dev/null
sleep 1

# Start in background using setsid + disown (and try screen if available)
if command -v screen &>/dev/null; then
    screen -dmS llmfit llmfit serve --host 0.0.0.0 --port 8787 --no-dashboard
else
    setsid llmfit serve --host 0.0.0.0 --port 8787 --no-dashboard > /tmp/llmfit-serve.log 2>&1 &
    disown
fi

# Intelligent health polling instead of fixed sleep
for i in {1..10}; do
    if curl -sf http://127.0.0.1:8787/health >/dev/null 2>&1; then
        echo "LLMFIT_SERVE_OK"
        exit 0
    fi
    sleep 1
done

echo "LLMFIT_SERVE_FAIL"
echo "--- Last 20 lines of LLMfit log ---"
cat /tmp/llmfit-serve.log 2>/dev/null | tail -20
"""


def script_install_llamacpp(job_key: str | None = None) -> str:
    """Install/build llama.cpp with CUDA on the remote instance."""
    if job_key is not None:
        state = f"/workspace/.vastai-app/jobs/{job_key}.json"
        log = f"/tmp/install-{job_key}.log"
        return f"""
mkdir -p /workspace/.vastai-app/jobs
STATE_PATH="{state}"
LOG_PATH="{log}"
JOB_PID=$$
exec > >(tee -a "$LOG_PATH") 2>&1

write_state() {{
  python3 - "$STATE_PATH" "$JOB_PID" "$1" "${{2:-0}}" "${{3:-0}}" "${{4:-0}}" "${{5:-}}" <<'PYEOF'
import json, sys, time
path, pid, stage, pct, bytes_d, bytes_total, speed = sys.argv[1:8]
with open(path, "w") as fh:
    payload = {{
        "pid": int(pid),
        "stage": stage,
        "percent": int(pct or 0),
        "bytes_downloaded": int(bytes_d or 0),
        "bytes_total": int(bytes_total or 0),
        "speed": speed or "",
        "updated_at": int(time.time()),
    }}
    json.dump(payload, fh)
PYEOF
}}

echo "Installing llama.cpp with CUDA..."
write_state apt 0
apt-get update -qq && apt-get install -y -qq cmake build-essential git 2>/dev/null

write_state clone 10
SKIP_BUILD=0
if [ -d /opt/llama.cpp ]; then
    cd /opt/llama.cpp
    PULL_OUT=$(git pull 2>&1)

    # Use detection loop logic locally too for consistency
    {_DETECTION_LOOP}
    
    if echo "$PULL_OUT" | grep -q "Already up to date" && [ -n "$LLAMA_PATH" ]; then
        echo "LLAMACPP_ALREADY_UP_TO_DATE (Found at: $LLAMA_PATH)"
        write_state done 100
        echo "INSTALL_LLAMACPP_DONE"
        SKIP_BUILD=1
    fi
else
    git clone https://github.com/ggerganov/llama.cpp /opt/llama.cpp
fi

if [ "$SKIP_BUILD" -ne 1 ]; then
    # 3. Build llama.cpp
    # We detect CUDA arch manually because 'native' often fails in Docker/minimal images
    CUDA_ARCH=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n 1 | tr -d '.')
    if [ -z "$CUDA_ARCH" ]; then CUDA_ARCH="native"; fi
    
    write_state cmake 20
    cd /opt/llama.cpp
    cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH 2>&1
    
    write_state build 40
    cmake --build build --config Release -j $(nproc) 2>&1
    
    write_state build 90
    # Search for server binary
    {_DETECTION_LOOP}

    if [ -n "$LLAMA_PATH" ]; then
        write_state done 100
        echo "INSTALL_LLAMACPP_DONE"
        "$LLAMA_PATH" --version 2>/dev/null || true
    else
        write_state failed 0
        echo "INSTALL_LLAMACPP_FAILED"
    fi
fi
"""

    return f"""
echo "Installing llama.cpp with CUDA..."
apt-get update -qq && apt-get install -y -qq cmake build-essential git 2>/dev/null

if [ -d /opt/llama.cpp ]; then
    cd /opt/llama.cpp
    PULL_OUT=$(git pull 2>&1)
    
    {_DETECTION_LOOP}

    if echo "$PULL_OUT" | grep -q "Already up to date" && [ -n "$LLAMA_PATH" ]; then
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

{_DETECTION_LOOP}

if [ -n "$LLAMA_PATH" ]; then
    echo "INSTALL_LLAMACPP_DONE"
    "$LLAMA_PATH" --version 2>/dev/null || true
else
    echo "INSTALL_LLAMACPP_FAILED"
fi
"""


def script_list_models() -> str:
    """List all GGUF files on the instance."""
    return r"""
echo "===MODELS_START==="
find /workspace /models /root -type f -name '*.gguf' 2>/dev/null | while read f; do
    SIZE=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
    echo "GGUF|$f|$SIZE"
done
echo "===MODELS_END==="
"""


def parse_model_list(output: str) -> list[dict]:
    """Parse model listing output."""
    models = []
    in_block = False
    for line in output.splitlines():
        line = line.strip()
        if line == "===MODELS_START===":
            in_block = True
            continue
        if line == "===MODELS_END===":
            break
        if in_block and line.startswith("GGUF|"):
            parts = line.split("|", 2)
            if len(parts) >= 3:
                import os
                path = parts[1]
                size = int(parts[2]) if parts[2].isdigit() else 0
                size_gb = size / (1024 ** 3)
                models.append({
                    "path": path,
                    "filename": os.path.basename(path),
                    "size_bytes": size,
                    "size_display": f"{size_gb:.1f} GB" if size_gb >= 1 else f"{size / (1024**2):.0f} MB",
                })
    return models


def script_download_model(
    repo_id: str,
    filename: str,
    dest_dir: str = "/workspace",
    job_key: str | None = None,
) -> str:
    """Download a GGUF from HuggingFace onto the instance."""
    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    dest = f"{dest_dir}/{filename}"
    if job_key is not None:
        state = f"/workspace/.vastai-app/jobs/{job_key}.json"
        log = f"/tmp/install-{job_key}.log"
        return f"""
mkdir -p /workspace/.vastai-app/jobs
STATE_PATH="{state}"
LOG_PATH="{log}"
JOB_PID=$$
exec > >(tee -a "$LOG_PATH") 2>&1

write_state() {{
  python3 - "$STATE_PATH" "$JOB_PID" "$1" "${{2:-0}}" "${{3:-0}}" "${{4:-0}}" "${{5:-}}" <<'PYEOF'
import json, sys, time
path, pid, stage, pct, bytes_d, bytes_total, speed = sys.argv[1:8]
with open(path, "w") as fh:
    payload = {{
        "pid": int(pid),
        "stage": stage,
        "percent": int(pct or 0),
        "bytes_downloaded": int(bytes_d or 0),
        "bytes_total": int(bytes_total or 0),
        "speed": speed or "",
        "updated_at": int(time.time()),
    }}
    json.dump(payload, fh)
PYEOF
}}

format_speed() {{
  BPS="${{1:-0}}"
  python3 - "$BPS" <<'PYEOF'
import sys

try:
    bps = int(float(sys.argv[1] or 0))
except Exception:
    bps = 0

if bps >= 1048576:
    print(f"{{bps / 1048576:.1f}} MB/s")
elif bps >= 1024:
    print(f"{{bps / 1024:.1f}} KB/s")
else:
    print(f"{{bps}} B/s")
PYEOF
}}

echo "Downloading {filename} from HuggingFace..."
write_state download 0
mkdir -p "{dest_dir}"
cd "{dest_dir}"

TOTAL_BYTES=$(python3 - "{url}" <<'PYEOF' 2>/dev/null
import sys
from urllib.request import Request, urlopen

url = sys.argv[1]
try:
    req = Request(url, method="HEAD")
    with urlopen(req, timeout=20) as resp:
        print(resp.headers.get("Content-Length") or 0)
except Exception:
    print(0)
PYEOF
)
if ! echo "$TOTAL_BYTES" | grep -Eq '^[0-9]+$'; then
    TOTAL_BYTES=0
fi

DL_PID=""
MONITOR_PID=""
cleanup() {{
  if [ -n "$MONITOR_PID" ]; then
    kill -TERM "$MONITOR_PID" 2>/dev/null || true
  fi
  if [ -n "$DL_PID" ]; then
    kill -TERM "$DL_PID" 2>/dev/null || true
  fi
}}
trap cleanup TERM INT

monitor_progress() {{
  LAST_BYTES=0
  LAST_TS=$(date +%s)
  while kill -0 "$DL_PID" 2>/dev/null; do
    CUR_BYTES=$(stat -c%s "{dest}" 2>/dev/null || stat -f%z "{dest}" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    DELTA_TS=$((NOW - LAST_TS))
    if [ "$DELTA_TS" -le 0 ]; then
      DELTA_TS=1
    fi
    DELTA_BYTES=$((CUR_BYTES - LAST_BYTES))
    if [ "$DELTA_BYTES" -lt 0 ]; then
      DELTA_BYTES=0
    fi
    SPEED_TEXT=$(format_speed $((DELTA_BYTES / DELTA_TS)))
    if [ "$TOTAL_BYTES" -gt 0 ]; then
      PCT=$((CUR_BYTES * 100 / TOTAL_BYTES))
      if [ "$PCT" -gt 99 ]; then
        PCT=99
      fi
    else
      PCT=0
    fi
    write_state download "$PCT" "$CUR_BYTES" "$TOTAL_BYTES" "$SPEED_TEXT"
    echo "DOWNLOAD_PROGRESS|$PCT|$CUR_BYTES|$TOTAL_BYTES|$SPEED_TEXT"
    LAST_BYTES=$CUR_BYTES
    LAST_TS=$NOW
    sleep 1
  done
}}

if command -v wget &>/dev/null; then
    wget -c --progress=dot:giga -O "{dest}" "{url}" 2>&1 &
elif command -v curl &>/dev/null; then
    curl -L -C - -o "{dest}" "{url}" 2>&1 &
else
    echo "DOWNLOAD_FAILED|missing_downloader"
    write_state failed 0
    exit 1
fi

DL_PID=$!
monitor_progress &
MONITOR_PID=$!
wait "$DL_PID"
DL_STATUS=$?
kill -TERM "$MONITOR_PID" 2>/dev/null || true
wait "$MONITOR_PID" 2>/dev/null || true

if [ "$DL_STATUS" -eq 0 ] && [ -f "{dest}" ]; then
    SIZE=$(stat -c%s "{dest}" 2>/dev/null || echo 0)
    write_state done 100 "$SIZE" "$SIZE"
    echo "DOWNLOAD_DONE|{dest}|$SIZE"
else
    write_state failed 0
    echo "DOWNLOAD_FAILED"
fi
"""
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


def script_delete_model(path: str) -> str:
    """Delete a GGUF file from the instance."""
    return f'rm -f "{path}" && echo "DELETE_OK" || echo "DELETE_FAIL"'


def script_stop_llama_server() -> str:
    """Stop llama-server on the instance."""
    return r"""
pkill -f "llama-server" 2>/dev/null
sleep 1
if pgrep -f "llama-server" &>/dev/null; then
    pkill -9 -f "llama-server" 2>/dev/null
    echo "STOP_FORCED"
else
    echo "STOP_OK"
fi
"""


def script_fetch_log(lines: int = 200) -> str:
    """Fetch llama-server log tail."""
    return f"""
echo "=== ps llama-server ==="
pgrep -fa llama-server || echo "(no llama-server process)"
echo
echo "=== port {11434} ==="
ss -lnt 'sport = :11434' 2>/dev/null || netstat -lnt 2>/dev/null | grep 11434 || echo "(port not listening)"
echo
echo "=== tail -{lines} /tmp/llama-server.log ==="
tail -{lines} /tmp/llama-server.log 2>/dev/null || echo "(no log file)"
"""


def script_check_remote_updates() -> str:
    """Check for pending updates on remote components."""
    return r"""
echo "===UPDATE_CHECK_START==="

# 1. Check Llama.cpp updates
if [ -d /opt/llama.cpp ]; then
    cd /opt/llama.cpp
    git fetch &>/dev/null
    BEHIND=$(git rev-list HEAD..origin/master --count 2>/dev/null || echo 0)
    echo "LLAMACPP_BEHIND=$BEHIND"
else
    echo "LLAMACPP_BEHIND=999"
fi

# 2. Check LLMfit updates
if command -v llmfit &>/dev/null; then
    # Simple check: compare local version with latest available on pypi/github (conceptually)
    if [ -d /root/llmfit ]; then
        cd /root/llmfit
        git fetch &>/dev/null
        LLMFIT_BEHIND=$(git rev-list HEAD..origin/master --count 2>/dev/null || echo 0)
        echo "LLMFIT_BEHIND=$LLMFIT_BEHIND"
    else
        echo "LLMFIT_BEHIND=0"
    fi
else
    echo "LLMFIT_BEHIND=999"
fi

echo "===UPDATE_CHECK_END==="
"""


def script_check_job(job_key: str) -> str:
    state = f"/workspace/.vastai-app/jobs/{job_key}.json"
    return f"""
STATE="{state}"
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
STATE="{state}"
if [ -f "$STATE" ]; then
    PID=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pid',''))" "$STATE" 2>/dev/null)
    if [ -n "$PID" ]; then
        kill -TERM "$PID" 2>/dev/null || true
    fi
    rm -f "$STATE"
    echo "CANCEL_OK"
else
    echo "CANCEL_NOOP"
fi
"""


def parse_check_job_output(output: str) -> tuple[str, dict]:
    """Parse script_check_job output into a status and state dict."""
    import json

    lines = output.strip().splitlines()
    if not lines:
        return "MISSING", {}
    status = lines[0].strip()
    if status not in {"RUNNING", "DONE", "STALE", "MISSING"}:
        return "MISSING", {}
    if len(lines) < 2:
        return status, {}
    try:
        state = json.loads("\n".join(lines[1:]))
    except Exception:
        return status, {}
    return status, state if isinstance(state, dict) else {}


def script_stream_job_log(job_key: str) -> str:
    """Stream a remote job log and exit cleanly when the job stops."""
    state = f"/workspace/.vastai-app/jobs/{job_key}.json"
    log = f"/tmp/install-{job_key}.log"
    return f"""
STATE="{state}"
LOG="{log}"
LAST_LINE=0
touch "$LOG" 2>/dev/null || true

dump_new_lines() {{
  if [ ! -f "$LOG" ]; then
    return
  fi
  CUR_LINES=$(wc -l < "$LOG" 2>/dev/null || echo 0)
  if [ "$CUR_LINES" -gt "$LAST_LINE" ]; then
    START=$((LAST_LINE + 1))
    sed -n "${{START}},${{CUR_LINES}}p" "$LOG" 2>/dev/null || true
    LAST_LINE=$CUR_LINES
  fi
}}

while true; do
  dump_new_lines
  if [ ! -f "$STATE" ]; then
    break
  fi
  META=$(python3 - "$STATE" <<'PYEOF'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception:
    print("missing")
    print("")
    raise SystemExit
print(str(data.get("stage", "")))
print(str(data.get("pid", "")))
PYEOF
)
  STAGE=$(echo "$META" | sed -n '1p')
  PID=$(echo "$META" | sed -n '2p')
  if [ "$STAGE" = "done" ] || [ "$STAGE" = "failed" ] || [ "$STAGE" = "cancelled" ]; then
    break
  fi
  if [ -n "$PID" ] && ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

dump_new_lines
"""


def script_wipe_llamacpp() -> str:
    """Safely remove the llama.cpp installation for a fresh setup test."""
    return r"""
echo "Wiping llama.cpp from /opt/llama.cpp..."
pkill -f "llama-server" 2>/dev/null || true
rm -rf /opt/llama.cpp
echo "WIPE_DONE"
"""
