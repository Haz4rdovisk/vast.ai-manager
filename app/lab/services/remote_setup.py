"""SSH script builders for remote instance setup and control.
All functions return shell script strings — the caller runs them via SSHService.run_script()."""
from __future__ import annotations


def script_check_setup() -> str:
    """Probe what's installed on the instance. Outputs structured markers."""
    return r"""
echo "===PROBE_START==="

# Check llmfit
if command -v llmfit &>/dev/null; then
    echo "LLMFIT_INSTALLED=yes"
    LLMFIT_VER=$(llmfit --version 2>/dev/null | head -1)
    echo "LLMFIT_VERSION=$LLMFIT_VER"
else
    echo "LLMFIT_INSTALLED=no"
fi

# Check if llmfit serve is running
if pgrep -f "llmfit serve" &>/dev/null; then
    echo "LLMFIT_SERVING=yes"
else
    echo "LLMFIT_SERVING=no"
fi

# Check llama.cpp
LLAMA_PATH=""
if [ -f /opt/llama.cpp/build/bin/llama-server ]; then
    LLAMA_PATH="/opt/llama.cpp/build/bin/llama-server"
elif command -v llama-server &>/dev/null; then
    LLAMA_PATH=$(which llama-server)
fi

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
    LLAMA_MODEL=$(pgrep -fa "llama-server" | grep -oP '(?<=-m )\S+' | head -1)
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
    """Start llmfit serve in background."""
    return r"""
# Kill existing llmfit serve if running
pkill -f "llmfit serve" 2>/dev/null
sleep 1
# Start in background
nohup llmfit serve --host 0.0.0.0 --port 8787 --no-dashboard > /tmp/llmfit-serve.log 2>&1 &
sleep 3
# Verify it started
if curl -sf http://127.0.0.1:8787/health >/dev/null 2>&1; then
    echo "LLMFIT_SERVE_OK"
else
    echo "LLMFIT_SERVE_FAIL"
    cat /tmp/llmfit-serve.log 2>/dev/null | tail -20
fi
"""


def script_install_llamacpp() -> str:
    """Install/build llama.cpp with CUDA on the remote instance."""
    return r"""
echo "Installing llama.cpp with CUDA..."
apt-get update -qq && apt-get install -y -qq cmake build-essential git 2>/dev/null

if [ -d /opt/llama.cpp ]; then
    cd /opt/llama.cpp && git pull
else
    git clone https://github.com/ggerganov/llama.cpp /opt/llama.cpp
fi

cd /opt/llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=native 2>&1 | tail -5
cmake --build build --config Release -j$(nproc) -- llama-server llama-cli 2>&1 | tail -10

if [ -f /opt/llama.cpp/build/bin/llama-server ]; then
    echo "INSTALL_LLAMACPP_DONE"
    /opt/llama.cpp/build/bin/llama-server --version 2>/dev/null || true
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


def script_download_model(repo_id: str, filename: str, dest_dir: str = "/workspace") -> str:
    """Download a GGUF from HuggingFace onto the instance."""
    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    dest = f"{dest_dir}/{filename}"
    return f"""
echo "Downloading {filename} from HuggingFace..."
mkdir -p "{dest_dir}"
cd "{dest_dir}"
if command -v wget &>/dev/null; then
    wget -c --progress=dot:giga -O "{dest}" "{url}" 2>&1 | tail -5
elif command -v curl &>/dev/null; then
    curl -L -C - -o "{dest}" "{url}" 2>&1 | tail -5
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
