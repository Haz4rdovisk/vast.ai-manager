from __future__ import annotations
import time
from PySide6.QtCore import QObject, Signal, Slot
from app.services.vast_service import VastService
from app.services.ssh_service import SSHService, wait_for_local_port, is_port_open
from app.models import AppConfig, InstanceState, TunnelStatus


# Total time budget for establishing a tunnel
MAX_READY_WAIT_SECONDS = 180         # wait for instance to be "running" with ssh info
SSH_PROBE_WAIT_SECONDS = 120         # wait for remote sshd to accept connections
LOCAL_PORT_WAIT_SECONDS = 60         # wait for -L port to become available locally
SSH_RETRY_ATTEMPTS = 60              # how many times to retry the ssh -L handshake (4 minutes total)


class TunnelStarter(QObject):
    status_changed = Signal(int, str, str)  # instance_id, TunnelStatus.value, message
    fix_requested = Signal(int)             # instance_id (triggers attach_ssh)

    def __init__(self, vast: VastService, ssh: SSHService, config: AppConfig):
        super().__init__()
        self.vast = vast
        self.ssh = ssh
        self.config = config

    def _emit(self, iid: int, status: TunnelStatus, msg: str):
        self.status_changed.emit(iid, status.value, msg)

    @Slot(int, int)
    def connect(self, instance_id: int, local_port: int):
        self._emit(instance_id, TunnelStatus.CONNECTING,
                   "Waiting for instance to become ready...")

        # 1. Poll until RUNNING with ssh info
        inst = self._wait_for_ready(instance_id)
        if inst is None:
            self._emit(instance_id, TunnelStatus.FAILED,
                       "Timed out waiting for instance to become ready.")
            return

        host, port = inst.ssh_host, inst.ssh_port

        # 2. Probe remote sshd until it responds cleanly
        self._emit(instance_id, TunnelStatus.CONNECTING,
                   f"Waiting for SSH on {host}:{port}...")
        if not self._wait_for_remote_ssh(host, port):
            self._emit(instance_id, TunnelStatus.FAILED,
                       f"Remote SSH did not respond within {SSH_PROBE_WAIT_SECONDS}s. "
                       "The instance may still be booting. Try again shortly.")
            return

        # 3. Open tunnel with retries
        self._emit(instance_id, TunnelStatus.CONNECTING,
                   f"Establishing tunnel to {host}:{port}...")
        last_err = ""
        for attempt in range(1, SSH_RETRY_ATTEMPTS + 1):
            try:
                handle = self.ssh.start_tunnel(instance_id, host, port, local_port)
            except FileNotFoundError:
                self._emit(instance_id, TunnelStatus.FAILED,
                           "SSH not found. Install Windows OpenSSH.")
                return
            except Exception as e:
                self._emit(instance_id, TunnelStatus.FAILED, f"Failed to start SSH: {e}")
                return

            ok = wait_for_local_port(
                local_port,
                timeout=LOCAL_PORT_WAIT_SECONDS,
                is_alive=handle.alive,
            )
            if ok:
                self._emit(instance_id, TunnelStatus.CONNECTED,
                            f"Connected at 127.0.0.1:{local_port}")
                
                # 4. Handle initialization script if present
                if self.config.on_connect_script:
                    self._emit(instance_id, TunnelStatus.CONNECTED, "Sending GPU initialization script to the server...")
                    success, output = self.ssh.run_script(host, port, self.config.on_connect_script)
                    if success:
                        self._emit(instance_id, TunnelStatus.CONNECTED, 
                                   f"✓ Script started successfully\n--- Response ---\n{output.strip()}\n--- End Response ---")
                    else:
                        self._emit(instance_id, TunnelStatus.CONNECTED, 
                                   f"⚠ Script reported an error\n--- Error ---\n{output.strip()}\n--- End Error ---")
                return

            # Collect diagnostics and retry
            last_err = self._read_stderr(handle)
            self.ssh.stop_tunnel(instance_id)

            err_lower = last_err.lower()
            if "permission denied" in err_lower or "publickey" in err_lower:
                if attempt == 1:
                    # First attempt failed with auth error — trigger AUTO-FIX
                    self._emit(instance_id, TunnelStatus.CONNECTING, 
                               "⚠ Permission error. Trying automatic key repair...")
                    self.fix_requested.emit(instance_id)
                    # Wait 10s for Vast.ai to process the new key
                    for _ in range(100):
                        if self.vast is None: break # safety
                        time.sleep(0.1)
                    self._emit(instance_id, TunnelStatus.CONNECTING, "Retrying connection after repair...")
                    continue
                else:
                    break  # Already tried fixing, still failing.

            if attempt < SSH_RETRY_ATTEMPTS:
                if "connection closed by" in err_lower:
                    msg = f"Waiting for the server to start internal services ({attempt}/{SSH_RETRY_ATTEMPTS})..."
                else:
                    msg = f"Attempt {attempt} failed, waiting... ({self._short(last_err)})"
                    
                self._emit(instance_id, TunnelStatus.CONNECTING, msg)
                time.sleep(4)

        hint = self._auth_hint(last_err)
        self._emit(instance_id, TunnelStatus.FAILED,
                   f"Could not establish tunnel. {self._short(last_err)}{hint}")

    # ---------- helpers ----------

    def _wait_for_ready(self, instance_id: int):
        deadline = time.time() + MAX_READY_WAIT_SECONDS
        last_state = None
        while time.time() < deadline:
            try:
                all_instances = self.vast.list_instances()
                inst = next((i for i in all_instances if i.id == instance_id), None)
            except Exception as e:
                self._emit(instance_id, TunnelStatus.CONNECTING, f"Checking... ({e})")
                time.sleep(4)
                continue
            if inst and inst.state != last_state:
                last_state = inst.state
                self._emit(instance_id, TunnelStatus.CONNECTING,
                           f"Instance state: {inst.state.value}")
            if (inst
                    and inst.state == InstanceState.RUNNING
                    and inst.ssh_host
                    and inst.ssh_port):
                return inst
            time.sleep(3)
        return None

    def _wait_for_remote_ssh(self, host: str, port: int) -> bool:
        deadline = time.time() + SSH_PROBE_WAIT_SECONDS
        while time.time() < deadline:
            if is_port_open(host, port, timeout=3.0):
                # Port accepts TCP — give sshd a moment to be ready for real handshakes
                time.sleep(2)
                return True
            time.sleep(3)
        return False

    @staticmethod
    def _read_stderr(handle) -> str:
        try:
            if handle.process.stderr is None:
                return ""
            # Non-blocking: only read what's already available after process exit
            if handle.process.poll() is not None:
                return (handle.process.stderr.read() or "").strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _auth_hint(msg: str) -> str:
        low = (msg or "").lower()
        if ("permission denied" in low
                or "incorrect passphrase" in low
                or "no such identity" in low
                or "publickey" in low
                or "host key verification failed" in low):
            return (" -> This looks like an SSH key issue. Check that your public key "
                    "is registered at https://cloud.vast.ai/account/ and configure the "
                    "private key path in Settings.")
        return ""

    @staticmethod
    def _short(msg: str) -> str:
        if not msg:
            return ""
        msg = msg.replace("\r", " ").replace("\n", " ").strip()
        return msg[:160]
