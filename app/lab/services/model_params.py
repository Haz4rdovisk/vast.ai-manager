"""Builds the full llama-server command from a ServerParams config."""
from __future__ import annotations
from app.lab.state.models import ServerParams


def build_launch_command(params: ServerParams, binary_path: str = "") -> str:
    """Generate the full llama-server command string."""
    binary = binary_path or "/opt/llama.cpp/build/bin/llama-server"

    parts = [binary]
    parts.append(f'-m "{params.model_path}"')
    parts.append(f'--host {params.host}')
    parts.append(f'--port {params.port}')
    parts.append(f'-c {params.context_length}')
    parts.append(f'-ngl {params.gpu_layers}')

    if params.threads > 0:
        parts.append(f'-t {params.threads}')

    parts.append(f'-b {params.batch_size}')
    parts.append(f'-np {params.parallel_requests}')
    parts.append(f'--repeat-penalty {params.repeat_penalty:.2f}')

    if params.flash_attention:
        parts.append('-fa on')

    if params.kv_cache_type:
        parts.append(f'-ctk {params.kv_cache_type} -ctv {params.kv_cache_type}')

    if params.no_warmup:
        parts.append('--no-warmup')

    parts.append('--jinja')

    if params.extra_args:
        parts.append(params.extra_args)

    return " \\\n  ".join(parts)


def build_launch_script(params: ServerParams, binary_path: str = "") -> str:
    """Generate a full bash script that stops any existing server and launches a new one."""
    cmd = build_launch_command(params, binary_path)
    return f"""
# Stop existing llama-server if running
pkill -f "llama-server" 2>/dev/null
sleep 1

# Launch with nohup
nohup {cmd} \\
  > /tmp/llama-server.log 2>&1 &

LLAMA_PID=$!
echo "LAUNCH_PID=$LLAMA_PID"
sleep 2

# Quick sanity: is it still alive?
if kill -0 $LLAMA_PID 2>/dev/null; then
    echo "LAUNCH_OK"
else
    echo "LAUNCH_FAILED"
    tail -20 /tmp/llama-server.log 2>/dev/null
fi
"""


def default_params() -> ServerParams:
    """Return sensible defaults."""
    return ServerParams()


def params_summary(p: ServerParams) -> str:
    """Human-readable one-liner for display."""
    parts = [
        f"ctx={p.context_length}",
        f"ngl={p.gpu_layers}",
        f"batch={p.batch_size}",
    ]
    if p.threads > 0:
        parts.append(f"threads={p.threads}")
    if p.flash_attention:
        parts.append("FA")
    parts.append(f"kv={p.kv_cache_type}")
    return " · ".join(parts)
