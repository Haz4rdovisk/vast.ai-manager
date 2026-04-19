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
from datetime import datetime, timedelta
import warnings
from app.billing import DailySpendTracker, burn_rate_breakdown
from app.analytics_store import AnalyticsStore, CostSnapshot
from app.services.rental_service import RentalService
from app.workers.offer_search_worker import OfferSearchWorker
from app.workers.template_worker import TemplateListWorker
from app.workers.ssh_key_worker import SshKeyWorker
from app.workers.rent_worker import RentCreateWorker
from app.models_rental import OfferQuery, RentRequest
from app.services.port_allocator import PortAllocator


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

    # ---- Store signals ----
    offers_refreshed = Signal(list, object)      # list[Offer], OfferQuery
    offers_failed    = Signal(str, str)
    templates_refreshed = Signal(list)           # list[Template]
    ssh_keys_refreshed  = Signal(list)           # list[SshKey]
    ssh_key_created     = Signal(object)         # SshKey
    rent_done   = Signal(object)                 # RentResult
    rent_failed = Signal(str, str)

    # ---- Store triggers (cross-thread) ----
    _trigger_search_offers = Signal(object)      # OfferQuery
    _trigger_refresh_templates = Signal(str)
    _trigger_refresh_ssh_keys  = Signal()
    _trigger_create_ssh_key    = Signal(str)
    _trigger_rent              = Signal(object)  # RentRequest

    # ---- Internal triggers (Qt cross-thread signals) ----
    _trigger_refresh = Signal()
    _trigger_start   = Signal(int)
    _trigger_stop    = Signal(int)
    _trigger_connect = Signal(int, int)
    _trigger_bulk    = Signal(str, list, dict)

    def __init__(self, config_store: ConfigStore, parent=None):
        super().__init__(parent)
        self.config_store = config_store
        self.config: AppConfig = config_store.load()
        self.vast: VastService | None = None
        self.ssh = SSHService(ssh_key_path=self.config.ssh_key_path)
        self.port_allocator = PortAllocator(
            default_port=self.config.default_tunnel_port,
            initial_map=self.config.port_map,
            persist=self._persist_port_map,
        )
        self.tracker = DailySpendTracker()
        self.analytics_store = AnalyticsStore(
            path=self.config_store.path.parent / "analytics.json"
        )

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

        self.rental: RentalService | None = None
        self.store_thread = QThread()
        self.offer_worker: OfferSearchWorker | None = None
        self.template_worker: TemplateListWorker | None = None
        self.ssh_key_worker: SshKeyWorker | None = None
        self.rent_worker: RentCreateWorker | None = None

        self.list_thread   = QThread()
        self.action_thread = QThread()
        self.tunnel_thread = QThread()
        self.list_worker:   ListWorker | None    = None
        self.action_worker: ActionWorker | None  = None
        self.tunnel_starter:TunnelStarter | None = None
        self.bulk_thread = QThread()
        self.bulk_worker = None
        self._bulk_in_flight = False
        self._on_passphrase_success: callable | None = None

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_timer_tick)

    # ---- Convenience ----
    def today_spend(self) -> float:
        """Persistent charges (window-aware) + live extrapolation from the
        last charge's end timestamp to now, using current running dph.
        Ensures the tile ticks up in real time between Vast billing lumps."""
        stored = self.analytics_store.today_spend()
        if not self.analytics_store.has_billing_events:
            # No charge data yet — use the live daily tracker alone.
            return self.tracker.today_spend()
        if stored <= 0 and self.tracker.today_spend() > 0:
            return self.tracker.today_spend()
        live = self._live_overlay_since(
            datetime.combine(datetime.now().date(), datetime.min.time())
        )
        return round(stored + live, 4)

    def week_spend(self) -> float:
        stored = self.analytics_store.week_spend()
        if not self.analytics_store.has_billing_events:
            return stored
        now = datetime.now()
        start = datetime.combine(
            now.date() - timedelta(days=now.weekday()),
            datetime.min.time(),
        )
        return round(stored + self._live_overlay_since(start), 4)

    def month_spend(self) -> float:
        stored = self.analytics_store.month_spend()
        if not self.analytics_store.has_billing_events:
            return stored
        now = datetime.now()
        start = datetime(now.year, now.month, 1)
        return round(stored + self._live_overlay_since(start), 4)

    def _live_overlay_since(self, window_start: datetime) -> float:
        """Extrapolate spend from max(last_charge_end, window_start) → now
        at the current running dph. Zero if no running instances or if the
        last charge is already in the future (clock skew guard)."""
        instances = getattr(self, "last_instances", None) or []
        dph = sum(
            float(getattr(i, "dph", 0.0) or 0.0)
            for i in instances
            if getattr(i, "state", None) == InstanceState.RUNNING
        )
        if dph <= 0:
            return 0.0
        last_end = self.analytics_store.last_charge_end()
        start = max(last_end, window_start) if last_end else window_start
        now = datetime.now()
        if now <= start:
            return 0.0
        hours = (now - start).total_seconds() / 3600.0
        return dph * hours

    # ---- Lifecycle ----
    def bootstrap(self):
        """Spin up workers against the current API key."""
        if not self.config.api_key:
            return
        self.vast = VastService(self.config.api_key)
        # RentalService shares the api_key; the SDK manages its own client.
        self.rental = RentalService(api_key=self.config.api_key)
        if not self.store_thread.isRunning():
            self.offer_worker = OfferSearchWorker(self.rental)
            self.template_worker = TemplateListWorker(self.rental)
            self.ssh_key_worker = SshKeyWorker(self.rental)
            self.rent_worker = RentCreateWorker(self.rental)
            for w in (self.offer_worker, self.template_worker,
                      self.ssh_key_worker, self.rent_worker):
                w.moveToThread(self.store_thread)
            # Triggers → worker slots
            self._trigger_search_offers.connect(self.offer_worker.search)
            self._trigger_refresh_templates.connect(self.template_worker.refresh)
            self._trigger_refresh_ssh_keys.connect(self.ssh_key_worker.refresh)
            self._trigger_create_ssh_key.connect(self.ssh_key_worker.create)
            self._trigger_rent.connect(self.rent_worker.rent)
            # Worker signals → controller re-emits.
            # Note: templates/ssh_keys failures share the `offers_failed` bus by design
            # — the Store surface shows a single failure banner for all rental APIs.
            self.offer_worker.results.connect(self.offers_refreshed)
            self.offer_worker.failed.connect(self.offers_failed)
            self.template_worker.results.connect(self.templates_refreshed)
            self.template_worker.failed.connect(self.offers_failed)
            self.ssh_key_worker.listed.connect(self.ssh_keys_refreshed)
            self.ssh_key_worker.created.connect(self.ssh_key_created)
            self.ssh_key_worker.failed.connect(self.offers_failed)
            self.rent_worker.done.connect(self.rent_done)
            self.rent_worker.failed.connect(self.rent_failed)
            self.store_thread.start()
        else:
            # Service rebuilt — rebind api_key on existing workers
            self.offer_worker.service = self.rental
            self.template_worker.service = self.rental
            self.ssh_key_worker.service = self.rental
            self.rent_worker.service = self.rental
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

        from app.workers.bulk_action_worker import BulkActionWorker
        self.bulk_thread = QThread()
        self.bulk_worker = BulkActionWorker(self.vast)
        self.bulk_worker.moveToThread(self.bulk_thread)
        self.bulk_worker.progress.connect(self._on_bulk_progress)
        self.bulk_worker.finished.connect(self._on_bulk_finished)
        self._trigger_bulk.connect(self.bulk_worker.run)
        self.bulk_thread.start()

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
        if self.store_thread.isRunning():
            self.store_thread.quit()
            self.store_thread.wait(2000)
        if self.bulk_thread.isRunning():
            self.bulk_thread.quit()
            self.bulk_thread.wait(2000)
        self._destroy_workers()

    def _destroy_workers(self):
        if self.list_worker is not None:
            for sig in (self._trigger_refresh, self._trigger_start,
                        self._trigger_stop, self._trigger_connect):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                self._trigger_bulk.disconnect()
        except (RuntimeError, TypeError):
            pass
        for t in (self.list_thread, self.action_thread, self.tunnel_thread, self.bulk_thread):
            if t.isRunning():
                t.quit(); t.wait(1500)

    # ---- Config ----
    def apply_config(self, cfg: AppConfig):
        changed_key = cfg.api_key != self.config.api_key
        cfg.port_map = dict(self.config.port_map)
        cfg.instance_filters = dict(self.config.instance_filters)
        self.config = cfg
        self.port_allocator = PortAllocator(
            default_port=self.config.default_tunnel_port,
            initial_map=self.config.port_map,
            persist=self._persist_port_map,
        )
        self.config_store.save(cfg)
        self.ssh.ssh_key_path = cfg.ssh_key_path
        self.log_line.emit("Configurações salvas.")
        if changed_key:
            self.bootstrap()
        else:
            self._apply_interval()

    def _persist_port_map(self, m: dict[int, int]) -> None:
        self.config.port_map = m
        self.config_store.save(self.config)

    def update_instance_filters(self, filters: dict) -> None:
        self.config.instance_filters = dict(filters)
        self.config_store.save(self.config)

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
        alive_ids = {i.id for i in instances}
        self.port_allocator.compact(alive_ids)
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
                    current_balance=user.balance,
                    sync_meta=fin_data.get("sync", {}),
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

    # ---- Store API ----
    def search_offers(self, query: OfferQuery) -> None:
        if self.rental is None:
            self.offers_failed.emit("auth", "API key not configured"); return
        self._trigger_search_offers.emit(query)

    def refresh_templates(self, q: str = "") -> None:
        if self.rental is None: return
        self._trigger_refresh_templates.emit(q)

    def refresh_ssh_keys(self) -> None:
        if self.rental is None: return
        self._trigger_refresh_ssh_keys.emit()

    def create_ssh_key(self, public_key: str) -> None:
        if self.rental is None: return
        self._trigger_create_ssh_key.emit(public_key)

    def rent(self, req: RentRequest) -> None:
        if self.rental is None:
            self.rent_failed.emit("auth", "API key not configured"); return
        self._trigger_rent.emit(req)

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
        port = self.port_allocator.get(iid)
        self._pending_tunnel.add(iid)
        self.tunnel_states[iid] = TunnelStatus.CONNECTING
        self.tunnel_status_changed.emit(iid, TunnelStatus.CONNECTING.value, "connecting")
        self.log_line.emit(f"Conectando #{iid} em :{port}...")
        self._trigger_connect.emit(iid, port)

    def disconnect_tunnel(self, iid: int):
        self.ssh.stop_tunnel(iid)
        self._stop_live_metrics(iid)
        self._stop_model_watcher(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.log_line.emit(f"Conexão #{iid} encerrada.")
        self.tunnel_status_changed.emit(iid, TunnelStatus.DISCONNECTED.value, "disconnected")

    def bulk_action(self, action: str, ids: list[int], opts: dict | None = None) -> None:
        opts = opts or {}
        if action == "connect":
            for iid in ids:
                self.connect_tunnel(iid)
            return
        if action == "disconnect":
            for iid in ids:
                self.disconnect_tunnel(iid)
            return
        if self._bulk_in_flight:
            self.toast_requested.emit("Operação em andamento, aguarde", "warning", 3000)
            return
        self._bulk_in_flight = True
        self._trigger_bulk.emit(action, list(ids), opts)

    def _on_bulk_progress(self, done: int, total: int, iid: int, msg: str) -> None:
        self.log_line.emit(f"Bulk {done}/{total} #{iid}: {msg}")

    def _on_bulk_finished(self, action: str, ok: list, fail: list) -> None:
        self._bulk_in_flight = False
        self.log_line.emit(f"✓ Bulk {action}: {len(ok)} ok, {len(fail)} fail")
        if fail:
            self.toast_requested.emit(
                f"Falhou em {len(fail)} instâncias", "error", 4000)
        else:
            self.toast_requested.emit(
                f"{action} aplicado em {len(ok)} instâncias", "success", 3000)
        self._trigger_refresh.emit()
        if action == "start" and self.config.auto_connect_on_activate:
            for iid in ok:
                self.connect_tunnel(iid)

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
            port = self.port_allocator.get(iid)
            self.toast_requested.emit(f"Conectado em http://127.0.0.1:{port}", "success", 3000)
            self._pending_tunnel.discard(iid)
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
            if self._find_instance(iid) is not None:
                self._start_model_watcher(iid, port)
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

    def _start_model_watcher(self, iid: int, port: int):
        self._stop_model_watcher(iid)
        w = ModelWatcher(iid, port)
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
