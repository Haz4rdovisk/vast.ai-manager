from __future__ import annotations
import subprocess
import sys
import time
from PySide6.QtCore import QThread, Signal

from app.services.ssh_service import build_ssh_command


# Single long-running command on the remote: emit a TICK marker, then a few
# easy-to-parse lines per sample, every 2 seconds. One SSH connection serves
# the whole session (no per-sample handshake cost) and the output is a
# self-delimiting stream that's trivial to parse.
REMOTE_LOOP = (
    "while sleep 2; do "
    "echo TICK; "
    "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu "
    "--format=csv,noheader,nounits 2>/dev/null; "
    "free -m 2>/dev/null | awk '/^Mem:/{printf \"MEM %s %s\\n\",$3,$2}'; "
    "cat /proc/loadavg 2>/dev/null | awk '{printf \"LOAD %s\\n\",$1}'; "
    "df -B1G --output=used,size / 2>/dev/null | awk 'NR==2{printf \"DISK %s %s\\n\",$1,$2}'; "
    "done"
)

# Auto-restart the worker if SSH dies (network blip etc.). Cap with a short
# backoff so we don't hammer a permanently-down host.
RESTART_BACKOFF_SECONDS = 5


class LiveMetricsWorker(QThread):
    """Streams real-time host telemetry from inside the container via SSH.

    Emits `metrics(instance_id, dict)` every ~2s. The dict contains any subset
    of: gpu_util, gpu_temp, vram_used_mb, vram_total_mb, ram_used_mb,
    ram_total_mb, load1, disk_used_gb, disk_total_gb.
    """
    metrics = Signal(int, dict)
    error = Signal(int, str)

    def __init__(self, instance_id: int, host: str, port: int, ssh_service, parent=None):
        super().__init__(parent)
        self.instance_id = instance_id
        self.host = host
        self.port = port
        self.ssh = ssh_service
        self._stop = False
        self._proc: subprocess.Popen | None = None

    def stop(self):
        self._stop = True
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def run(self):
        while not self._stop:
            try:
                self._run_once()
            except Exception as e:
                self.error.emit(self.instance_id, str(e))
            if self._stop:
                return
            # Brief backoff before reconnecting (network glitch, sshd hiccup, etc.)
            for _ in range(RESTART_BACKOFF_SECONDS * 10):
                if self._stop:
                    return
                time.sleep(0.1)

    def _run_once(self):
        cmd = build_ssh_command(self.host, self.port, self.ssh.ssh_key_path)
        cmd += ["-o", "StrictHostKeyChecking=accept-new",
                "-o", "ServerAliveInterval=15"]
        if self.ssh.ssh_key_path:
            cmd += ["-o", "IdentitiesOnly=yes"]
        use_askpass, env = self.ssh._create_askpass_env()
        if not use_askpass:
            cmd += ["-o", "BatchMode=yes"]
        cmd.append(REMOTE_LOOP)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        # Bytes mode (text=False) — see ssh_service.run_script for why.
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=creationflags,
            bufsize=1,
        )

        block: list[str] = []
        try:
            assert self._proc.stdout is not None
            for raw in iter(self._proc.stdout.readline, b""):
                if self._stop:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if line == "TICK":
                    if block:
                        d = _parse_block(block)
                        if d:
                            self.metrics.emit(self.instance_id, d)
                    block = []
                elif line:
                    block.append(line)
        finally:
            proc = self._proc
            self._proc = None
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass


def _parse_block(lines: list[str]) -> dict:
    d: dict = {}
    for line in lines:
        if line.startswith("MEM "):
            p = line.split()
            if len(p) >= 3:
                try:
                    d["ram_used_mb"] = float(p[1])
                    d["ram_total_mb"] = float(p[2])
                except ValueError:
                    pass
        elif line.startswith("LOAD "):
            p = line.split()
            if len(p) >= 2:
                try:
                    d["load1"] = float(p[1])
                except ValueError:
                    pass
        elif line.startswith("DISK "):
            p = line.split()
            if len(p) >= 3:
                try:
                    d["disk_used_gb"] = float(p[1])
                    d["disk_total_gb"] = float(p[2])
                except ValueError:
                    pass
        else:
            # nvidia-smi CSV: gpu_util, mem_used_mb, mem_total_mb, temp
            parts = [x.strip() for x in line.split(",")]
            if len(parts) == 4:
                try:
                    d["gpu_util"] = float(parts[0])
                    d["vram_used_mb"] = float(parts[1])
                    d["vram_total_mb"] = float(parts[2])
                    d["gpu_temp"] = float(parts[3])
                except ValueError:
                    pass
    return d
