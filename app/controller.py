"""Single orchestrator for Vast.ai services, workers, SSH and billing.
The app shell/views subscribe to signals; all state lives here."""
from __future__ import annotations
from PySide6.QtCore import QObject, QTimer, Signal, QThread
from app.config import ConfigStore
from app.models import AppConfig, Instance, InstanceState, TunnelStatus, UserInfo
from app.services.vast_service import VastService
from app.services.ssh_service import SSHService
from app.workers.list_worker import ListWorker
from app.workers.action_worker import ActionWorker
from app.workers.tunnel_starter import TunnelStarter
from app.workers.live_metrics import LiveMetricsWorker
from app.workers.model_watcher import ModelWatcher
from app.workers.llama_probe import LlamaReadyProbe
from app.billing import DailySpendTracker, burn_rate_breakdown
from app.analytics_store import AnalyticsStore, CostSnapshot


class AppController(QObject):
    # ---- High-level signals the shell/views subscribe to ----
    instances_refreshed = Signal(list, object)   # list[Instance], UserInfo
    refresh_failed      = Signal(str, str)       # kind, message
    tunnel_status_changed = Signal(int, str, str)  # iid, status, message
    action_done         = Signal(int, str, bool, str)  # iid, action, ok, msg
    live_metrics        = Signal(int, dict)      # iid, payload
    model_changed       = Signal(int, str)       # iid, model_id
    log_line            = Signal(str)            # log message
    passphrase_needed   = Signal()               # shell must prompt
    toast_requested     = Signal(str, str, int)  # msg, level, duration_ms

    # ---- Internal triggers (Qt cross-thread signals) ----
    _trigger_refresh = Signal()
    _trigger_start   = Signal(int)
    _trigger_stop    = Signal(int)
    _trigger_connect = Signal(int, int)

    def __init__(self, config_store: ConfigStore, parent=None):
        super().__init__(parent)
        self.config_store = config_store
        self.config: AppConfig = config_store.load()
        self.vast: VastService | None = None
        self.ssh = SSHService(ssh_key_path=self.config.ssh_key_path)
        self.tracker = DailySpendTracker()
        self.analytics_store = AnalyticsStore()

        self.last_instances: list[Instance] = []
        self.last_user: UserInfo | None = None
        self.tunnel_states: dict[int, TunnelStatus] = {}

        self._pending_start: set[int] = set()
        self._force_next_backfill = False
        self._pending_stop:  set[int] = set()
        self._pending_tunnel:set[int] = set()

        self._live_workers:   dict[int, LiveMetricsWorker] = {}
        self._model_watchers: dict[int, ModelWatcher] = {}
        self._llama_probes:   dict[int, LlamaReadyProbe] = {}

        self.list_thread   = QThread()
        self.action_thread = QThread()
        self.tunnel_thread = QThread()
        self.list_worker:   ListWorker | None    = None
        self.action_worker: ActionWorker | None  = None
        self.tunnel_starter:TunnelStarter | None = None
        self._on_passphrase_success: callable | None = None

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_timer_tick)

    # ---- Convenience ----
    def today_spend(self) -> float:
        """Real persistent today spend from analytics store."""
        stored = self.analytics_store.today_spend()
        return stored if stored > 0 else self.tracker.today_spend()

    # ---- Lifecycle ----
    def bootstrap(self):
        """Spin up workers against the current API key."""
        if not self.config.api_key:
            return
        self.vast = VastService(self.config.api_key)
        self._destroy_workers()

        self.list_thread = QThread()
        self.list_worker = ListWorker(self.vast)
        self.list_worker.moveToThread(self.list_thread)
        self.list_worker.refreshed.connect(self._on_refreshed)
        self.list_worker.failed.connect(self._on_refresh_failed)
        self._trigger_refresh.connect(self.list_worker.refresh)
        self.list_thread.start()

        self.action_thread = QThread()
        self.action_worker = ActionWorker(self.vast)
        self.action_worker.moveToThread(self.action_thread)
        self.action_worker.finished.connect(self._on_action_done)
        self._trigger_start.connect(self.action_worker.start)
        self._trigger_stop.connect(self.action_worker.stop)
        self.action_thread.start()

        self.tunnel_thread = QThread()
        self.tunnel_starter = TunnelStarter(self.vast, self.ssh, self.config)
        self.tunnel_starter.moveToThread(self.tunnel_thread)
        self.tunnel_starter.status_changed.connect(self._on_tunnel_status)
        self._trigger_connect.connect(self.tunnel_starter.connect)
        self.tunnel_thread.start()

        self._apply_interval()
        self.log_line.emit("Conectando à Vast.ai...")
        self._trigger_refresh.emit()

    def shutdown(self):
        self.refresh_timer.stop()
        for iid in list(self._live_workers.keys()):
            self._stop_live_metrics(iid)
        for iid in list(self._model_watchers.keys()):
            self._stop_model_watcher(iid)
        for iid in list(self._llama_probes.keys()):
            probe = self._llama_probes.pop(iid)
            probe.stop(); probe.wait(2000)
        if self.ssh is not None:
            self.ssh.stop_all()
        self._destroy_workers()

    def _destroy_workers(self):
        if self.list_worker is not None:
            for sig in (self._trigger_refresh, self._trigger_start,
                        self._trigger_stop, self._trigger_connect):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        for t in (self.list_thread, self.action_thread, self.tunnel_thread):
            if t.isRunning():
                t.quit(); t.wait(1500)

    # ---- Config ----
    def apply_config(self, cfg: AppConfig):
        changed_key = cfg.api_key != self.config.api_key
        self.config = cfg
        self.config_store.save(cfg)
        self.ssh.ssh_key_path = cfg.ssh_key_path
        self.log_line.emit("Configurações salvas.")
        if changed_key:
            self.bootstrap()
        else:
            self._apply_interval()

    def _apply_interval(self):
        secs = self.config.refresh_interval_seconds
        if secs <= 0:
            self.refresh_timer.stop()
        else:
            self.refresh_timer.start(secs * 1000)

    def _on_timer_tick(self):
        if self.vast is not None:
            self._trigger_refresh.emit()

    def request_refresh(self):
        if self.vast is not None:
            self._trigger_refresh.emit()

    # ---- Refresh callbacks ----
    def _on_refreshed(self, instances: list, user):
        self.last_instances = instances
        self.last_user = user
        
        # Force disconnect metadata for non-running instances
        from app.models import InstanceState, TunnelStatus
        for inst in instances:
            self.tracker.update(inst)
            if inst.state != InstanceState.RUNNING:
                if self.tunnel_states.get(inst.id) != TunnelStatus.DISCONNECTED:
                    self.tunnel_states[inst.id] = TunnelStatus.DISCONNECTED
                    self.tunnel_status_changed.emit(inst.id, TunnelStatus.DISCONNECTED, "instance-not-running")

        # Log cost snapshot for persistent analytics
        self._log_analytics_snapshot(instances, user, force_backfill=self._force_next_backfill)
        self._force_next_backfill = False # Reset flag

        self._check_tunnels_health()
        self._sync_live_workers(instances)
        self.log_line.emit(f"✓ Dados sincronizados ({len(instances)} instâncias)")
        self.instances_refreshed.emit(instances, user)

    def _log_analytics_snapshot(self, instances: list, user, force_backfill: bool = False):
        """Persist a cost snapshot for the analytics dashboard."""
        if not user:
            self.log_line.emit("⌛ Aguardando dados do usuário para snapshot...")
            return

        # 1. Backfill history IF store is almost empty OR requested (Sync Now)
        if self.analytics_store.entry_count < 2 or force_backfill:
            try:
                self.log_line.emit("⌛ Reconstruindo histórico (Invoices + Charges)...")
                fin_data = self.vast.fetch_financial_data()
                
                # Combine both data streams for a complete forensic reconstruction
                self.analytics_store.import_history(
                    invoices=fin_data.get("invoices", []),
                    charges=fin_data.get("charges", []),
                    current_balance=user.balance
                )
                
                count = len(fin_data.get("invoices", [])) + len(fin_data.get("charges", []))
                self.log_line.emit(f"✓ Histórico reconstruído ({count} registros)")
            except Exception as e:
                self.log_line.emit(f"⚠ Falha ao importar histórico: {str(e)}")

        from datetime import datetime
        cfg = self.config
        bd = burn_rate_breakdown(
            instances,
            include_storage=cfg.include_storage_in_burn_rate,
            estimated_network_cost_per_hour=cfg.estimated_network_cost_per_hour,
        )
        snap = CostSnapshot(
            ts=datetime.now().isoformat(timespec="seconds"),
            balance=user.balance,
            burn_total=bd["total"],
            burn_gpu=bd["gpu"],
            burn_storage=bd["storage"],
            burn_network=bd["network"],
            instances=bd["instances"],
        )
        self.log_line.emit(f"📊 Gravando snapshot (Saldo: ${user.balance:.2f}, Gasto: ${bd['total']:.3f}/h)")
        self.analytics_store.log_snapshot(snap)

    def _on_refresh_failed(self, kind: str, message: str):
        self.log_line.emit(f"✗ Erro ao sincronizar: {message}")
        self.refresh_failed.emit(kind, message)
        if kind == "auth":
            self.toast_requested.emit("API key inválida", "error", 3000)
        elif kind == "network":
            self.toast_requested.emit("Sem conexão com Vast.ai", "warning", 3000)
        else:
            self.toast_requested.emit(f"Falha: {message[:80]}", "error", 3000)

    def request_deep_sync(self):
        """Force a deep history scan on the next refresh."""
        self._force_next_backfill = True
        self._trigger_refresh.emit()

    # ---- Actions ----
    def _find_instance(self, iid: int) -> Instance | None:
        return next((i for i in self.last_instances if i.id == iid), None)

    def activate(self, iid: int) -> bool:
        if iid in self._pending_start:
            return False
        if self.config.auto_connect_on_activate and not self._has_usable_passphrase():
            self._on_passphrase_success = lambda: self.activate(iid)
            self.passphrase_needed.emit()
            return False
        self._pending_start.add(iid)
        self.log_line.emit(f"Ativando instância {iid}...")
        self._trigger_start.emit(iid)
        return True

    def deactivate(self, iid: int):
        if iid in self._pending_stop:
            return
        self._pending_stop.add(iid)
        self.ssh.stop_tunnel(iid)
        self._stop_live_metrics(iid)
        self._stop_model_watcher(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.log_line.emit(f"Desativando instância {iid}...")
        self._trigger_stop.emit(iid)

    def connect_tunnel(self, iid: int):
        if iid in self._pending_tunnel:
            return
        if not self._has_usable_passphrase():
            self._on_passphrase_success = lambda: self.connect_tunnel(iid)
            self.passphrase_needed.emit()
            return
        self._pending_tunnel.add(iid)
        self.tunnel_states[iid] = TunnelStatus.CONNECTING
        self.tunnel_status_changed.emit(iid, TunnelStatus.CONNECTING.value, "connecting")
        self.log_line.emit(f"Conectando #{iid}...")
        self._trigger_connect.emit(iid, self.config.default_tunnel_port)

    def disconnect_tunnel(self, iid: int):
        self.ssh.stop_tunnel(iid)
        self._stop_live_metrics(iid)
        self._stop_model_watcher(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.log_line.emit(f"Conexão #{iid} encerrada.")
        self.tunnel_status_changed.emit(iid, TunnelStatus.DISCONNECTED.value, "disconnected")

    def _on_action_done(self, iid: int, action: str, ok: bool, msg: str):
        if action == "start":
            self._pending_start.discard(iid)
        elif action == "stop":
            self._pending_stop.discard(iid)
        if ok:
            self.log_line.emit(f"✓ {action} #{iid}: {msg}")
            if action == "start" and self.config.auto_connect_on_activate:
                self.connect_tunnel(iid)
        else:
            self.log_line.emit(f"✗ {action} #{iid}: {msg}")
        self.action_done.emit(iid, action, ok, msg)
        if ok:
            self.toast_requested.emit(msg, "success", 3000)
        else:
            self.toast_requested.emit(f"Falha: {msg[:80]}", "error", 3000)
        self._trigger_refresh.emit()

    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        self.tunnel_states[iid] = TunnelStatus(status)
        self.log_line.emit(f"Túnel #{iid}: {msg}")
        if self.tunnel_states[iid] == TunnelStatus.CONNECTED:
            self.toast_requested.emit(f"Conectado em http://127.0.0.1:{self.config.default_tunnel_port}", "success", 3000)
            self._pending_tunnel.discard(iid)
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
            self._start_model_watcher(iid)
        elif self.tunnel_states[iid] == TunnelStatus.FAILED:
            self.toast_requested.emit("Falha na conexão. Veja o log.", "error", 4000)
            self._pending_tunnel.discard(iid)
            low = msg.lower()
            if ("permission denied" in low or "publickey" in low
                    or "host key verification failed" in low):
                self.ssh.clear_passphrase()
                self._stop_live_metrics(iid)
            self._stop_model_watcher(iid)
        self.tunnel_status_changed.emit(iid, status, msg)

    # ---- Live metrics ----
    def _has_usable_passphrase(self) -> bool:
        if not self.ssh.ssh_key_path:
            return True
        if not self.ssh.is_passphrase_required():
            return True
        return self.ssh.passphrase_cache is not None

    def set_ssh_passphrase(self, pwd: str):
        """Cache passphrase and resume pending action."""
        self.ssh.set_passphrase(pwd)
        if self._on_passphrase_success:
            callback = self._on_passphrase_success
            self._on_passphrase_success = None
            callback()
        # Also kick off metrics that were blocked
        self._trigger_refresh.emit()

    def _sync_live_workers(self, instances: list):
        if not self._has_usable_passphrase():
            return
        running = {i.id for i in instances
                   if i.state == InstanceState.RUNNING and i.ssh_host and i.ssh_port}
        for iid in running:
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
        for iid in list(self._live_workers.keys()):
            if iid not in running:
                self._stop_live_metrics(iid)

    def _start_live_metrics(self, iid: int):
        self._stop_live_metrics(iid)
        inst = self._find_instance(iid)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            return
        w = LiveMetricsWorker(iid, inst.ssh_host, inst.ssh_port, self.ssh)
        w.metrics.connect(self.live_metrics)
        w.error.connect(lambda i, e: self.log_line.emit(f"Métricas live #{i}: {e}"))
        self._live_workers[iid] = w
        w.start()

    def _stop_live_metrics(self, iid: int):
        w = self._live_workers.pop(iid, None)
        if w is not None:
            w.stop(); w.wait(2000)

    def _start_model_watcher(self, iid: int):
        self._stop_model_watcher(iid)
        w = ModelWatcher(iid, self.config.default_tunnel_port)
        w.model_changed.connect(self.model_changed)
        self._model_watchers[iid] = w
        w.start()

    def _stop_model_watcher(self, iid: int):
        w = self._model_watchers.pop(iid, None)
        if w is not None:
            w.stop(); w.wait(2000)

    def _check_tunnels_health(self):
        for iid, status in list(self.tunnel_states.items()):
            if status == TunnelStatus.CONNECTED:
                handle = self.ssh.get(iid)
                if handle is None or not handle.alive():
                    self.tunnel_states[iid] = TunnelStatus.FAILED
                    self._stop_live_metrics(iid)
                    self._stop_model_watcher(iid)
                    self.log_line.emit(f"Conexão #{iid} caiu.")
                    self.tunnel_status_changed.emit(iid, TunnelStatus.FAILED.value, "health-check-failed")
        running_ids = {i.id for i in self.last_instances if i.state == InstanceState.RUNNING}
        for iid in list(self._live_workers.keys()):
            if iid not in running_ids:
                self._stop_live_metrics(iid)
        for iid in list(self._model_watchers.keys()):
            if iid not in running_ids:
                self._stop_model_watcher(iid)
