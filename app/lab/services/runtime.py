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

    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
