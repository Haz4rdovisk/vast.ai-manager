"""HuggingFace GGUF downloader \u2014 raw urllib, resumable via HTTP Range."""
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
            existing = 0   # server ignored Range \u2014 restart
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
