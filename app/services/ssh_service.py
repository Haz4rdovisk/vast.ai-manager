from __future__ import annotations
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass


def is_key_encrypted(key_path: str) -> bool:
    if not key_path or not os.path.isfile(key_path):
        return False
    # Use ssh-keygen to check if it needs a passphrase
    # -y reads private key and prints public key. -P "" tries an empty passphrase.
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", key_path],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        # If it returns non-zero, it likely needs a passphrase (or is invalid)
        if proc.returncode != 0 and "passphrase" in proc.stderr.lower():
            return True
        return False
    except Exception:
        # Fallback if ssh-keygen is missing
        try:
            with open(key_path, 'r', encoding='utf-8') as f:
                return "ENCRYPTED" in f.read(2048)
        except Exception:
            return False


def build_ssh_command(host: str, port: int, key_path: str = "") -> list[str]:
    cmd = ["ssh", "-p", str(port)]
    if key_path:
        cmd += ["-i", key_path]
    cmd.append(f"root@{host}")
    return cmd


def build_tunnel_command(host: str, port: int, local_port: int, key_path: str = "", use_askpass: bool = False) -> list[str]:
    cmd = ["ssh", "-p", str(port)]
    if key_path:
        # IdentitiesOnly ensures ssh uses only this key, not also agent/default keys
        cmd += ["-i", key_path, "-o", "IdentitiesOnly=yes"]
    cmd += [
        f"root@{host}",
        "-L", f"{local_port}:127.0.0.1:{local_port}",
        "-N",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if not use_askpass:
        cmd += ["-o", "BatchMode=yes"]
    return cmd


def build_terminal_launch(ssh_cmd: list[str], prefer: str = "auto") -> list[str]:
    """Wrap ssh_cmd in a terminal launcher.
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


def wait_for_local_port(port: int, timeout: float = 20.0, interval: float = 0.5,
                        is_alive=None) -> bool:
    """Poll until local port is open, or is_alive() returns False, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_open("127.0.0.1", port):
            return True
        if is_alive is not None and not is_alive():
            return False
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

    def __init__(self, ssh_key_path: str = ""):
        self._tunnels: dict[int, TunnelHandle] = {}
        self.ssh_key_path = ssh_key_path
        self.passphrase_cache: str | None = None
        self._askpass_bat: str | None = None

    def is_passphrase_required(self) -> bool:
        return is_key_encrypted(self.ssh_key_path)

    def verify_passphrase(self, pwd: str) -> bool:
        """Validate a passphrase locally against the configured private key.
        Uses `ssh-keygen -y -P <pwd> -f <key>` which decrypts the key in-memory
        and prints the public part. Exit 0 == correct passphrase. No network."""
        if not self.ssh_key_path or not os.path.isfile(self.ssh_key_path):
            return False
        try:
            proc = subprocess.run(
                ["ssh-keygen", "-y", "-P", pwd, "-f", self.ssh_key_path],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def set_passphrase(self, pwd: str):
        self.passphrase_cache = pwd

    def clear_passphrase(self):
        self.passphrase_cache = None

    def _create_askpass_env(self) -> tuple[bool, dict | None]:
        use_askpass = bool(self.passphrase_cache)
        env = None
        if use_askpass:
            if not self._askpass_bat:
                import tempfile
                fd, path = tempfile.mkstemp(suffix=".bat", prefix="vast_askpass_")
                with os.fdopen(fd, "wb") as f:
                    script = f'@"{sys.executable}" -c "import os, sys; sys.stdout.write(os.environ.get(\'VAST_SSH_PASSPHRASE\', \'\'))"\n'
                    f.write(script.encode('utf-8'))
                self._askpass_bat = path
            
            env = os.environ.copy()
            env["SSH_ASKPASS"] = self._askpass_bat
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["VAST_SSH_PASSPHRASE"] = self.passphrase_cache
            env["DISPLAY"] = "dummy:0"
        return use_askpass, env

    def open_terminal(self, host: str, port: int, prefer: str = "auto") -> None:
        ssh_cmd = build_ssh_command(host, port, self.ssh_key_path)
        launch = build_terminal_launch(ssh_cmd, prefer)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        subprocess.Popen(launch, creationflags=creationflags)

    def start_tunnel(self, instance_id: int, host: str, port: int, local_port: int) -> TunnelHandle:
        self.stop_tunnel(instance_id)

        use_askpass, env = self._create_askpass_env()
        cmd = build_tunnel_command(host, port, local_port, self.ssh_key_path, use_askpass)
        
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            env=env,
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

    def run_script(self, host: str, port: int, script: str) -> tuple[bool, str]:
        """Runs a blocking SSH command by piping script into bash -s."""
        use_askpass, env = self._create_askpass_env()
        
        cmd = ["ssh", "-p", str(port)]
        if self.ssh_key_path:
            cmd += ["-i", self.ssh_key_path, "-o", "IdentitiesOnly=yes"]
        cmd += [
            "-o", "StrictHostKeyChecking=accept-new",
        ]
        if not use_askpass:
            cmd += ["-o", "BatchMode=yes"]
            
        cmd += [f"root@{host}", "bash", "-l", "-s"]

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        # Normalize to LF and append a trailing newline so the last line runs.
        script = "\n".join(line.rstrip() for line in script.replace("\r", "").splitlines()) + "\n"

        # IMPORTANT: send as bytes (text=False) — on Windows, subprocess with
        # text=True wraps stdin in a TextIOWrapper that translates \n -> \r\n,
        # which makes bash see lines like $'echo\r' and choke. Encoding to
        # bytes ourselves disables that translation.
        try:
            res = subprocess.run(
                cmd,
                input=script.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=creationflags,
            )
            out = res.stdout.decode("utf-8", errors="replace").strip()
            return (res.returncode == 0), out
        except Exception as e:
            return False, str(e)
