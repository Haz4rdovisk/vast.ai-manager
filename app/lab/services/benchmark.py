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
