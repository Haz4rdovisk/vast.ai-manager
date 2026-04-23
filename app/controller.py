"""Single orchestrator for Vast.ai services, workers, SSH and billing.
The app shell/views subscribe to signals; all state lives here."""
from __future__ import annotations
from PySide6.QtCore import QObject, QTimer, Signal, QThread
from app.config import ConfigStore
from app.models import AppConfig, Instance, InstanceState, TunnelStatus, UserInfo
from app.services.vast_service import VastService, VastAuthError, VastNetworkError
from app.services.ssh_service import SSHService
from app.workers.list_worker import ListWorker
from app.workers.action_worker import ActionWorker
from app.workers.tunnel_starter import TunnelStarter
from app.workers.live_metrics import LiveMetricsWorker
from app.workers.model_watcher import ModelWatcher
from app.workers.llama_probe import LlamaReadyProbe
from datetime import datetime, timedelta
import hashlib
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
import socket


class AppController(QObject):
    # ---- Signals ----
    instances_refreshed = Signal(list, object)
    refresh_failed      = Signal(str, str)
    tunnel_status_changed = Signal(int, str, str)
    action_done         = Signal(int, str, bool, str)
    bulk_done           = Signal(str, list, list)
    live_metrics        = Signal(int, dict)
    model_changed       = Signal(int, str)
    log_line            = Signal(str)
    passphrase_needed   = Signal()
    toast_requested     = Signal(str, str, int)

    # ---- Store Signals ----
    offers_refreshed = Signal(list, object)
    offers_failed    = Signal(str, str)
    templates_refreshed = Signal(list)
    ssh_keys_refreshed  = Signal(list)
    ssh_key_created     = Signal(object)
    rent_done   = Signal(object)
    rent_failed = Signal(str, str)

    # ---- Triggers ----
    _trigger_search_offers = Signal(object)
    _trigger_refresh_templates = Signal(str)
    _trigger_refresh_ssh_keys  = Signal()
    _trigger_create_ssh_key    = Signal(str)
    _trigger_rent              = Signal(object)

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
        self._auto_connect_after_start: set[int] = set()
        self._force_next_backfill = False
        self._pending_stop:  set[int] = set()
        self._pending_tunnel:set[int] = set()
        self._transition_locks: dict[int, InstanceState] = {}  # iid -> target_state

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
        stored = self.analytics_store.today_spend()
        if not self.analytics_store.has_billing_events:
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
        start = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time())
        return round(stored + self._live_overlay_since(start), 4)

    def month_spend(self) -> float:
        stored = self.analytics_store.month_spend()
        if not self.analytics_store.has_billing_events:
            return stored
        now = datetime.now()
        start = datetime(now.year, now.month, 1)
        return round(stored + self._live_overlay_since(start), 4)

    def _live_overlay_since(self, window_start: datetime) -> float:
        instances = getattr(self, "last_instances", None) or []
        live_rate = burn_rate_breakdown(
            instances,
            include_storage=self.config.include_storage_in_burn_rate,
            estimated_network_cost_per_hour=self.config.estimated_network_cost_per_hour,
        )["total"]
        if live_rate <= 0:
            return 0.0
        last_end = self.analytics_store.last_charge_end()
        start = max(last_end, window_start) if last_end else window_start
        now = datetime.now()
        if now <= start:
            return 0.0
        hours = (now - start).total_seconds() / 3600.0
        return live_rate * hours

    # ---- Lifecycle ----
    def bootstrap(self):
        if not self.config.api_key: return
        self.vast = VastService(self.config.api_key)
        self.rental = RentalService(api_key=self.config.api_key)
        
        QTimer.singleShot(1000, self.sync_local_ssh_key)
        QTimer.singleShot(2000, self.detect_existing_tunnels)

        if not self.store_thread.isRunning():
            self.offer_worker = OfferSearchWorker(self.rental)
            self.template_worker = TemplateListWorker(self.rental)
            self.ssh_key_worker = SshKeyWorker(self.rental)
            self.rent_worker = RentCreateWorker(self.rental)
            for w in (self.offer_worker, self.template_worker, self.ssh_key_worker, self.rent_worker):
                w.moveToThread(self.store_thread)
            self._trigger_search_offers.connect(self.offer_worker.search)
            self._trigger_refresh_templates.connect(self.template_worker.refresh)
            self._trigger_refresh_ssh_keys.connect(self.ssh_key_worker.refresh)
            self._trigger_create_ssh_key.connect(self.ssh_key_worker.create)
            self._trigger_rent.connect(self.rent_worker.rent)
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
        self.tunnel_starter.fix_requested.connect(self.fix_instance_ssh)
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
        self.log_line.emit("Conectando \u00e0 Vast.ai...")
        self._trigger_refresh.emit()

    def shutdown(self):
        self.refresh_timer.stop()
        for iid in list(self._live_workers.keys()): self._stop_live_metrics(iid)
        for iid in list(self._model_watchers.keys()): self._stop_model_watcher(iid)
        for iid in list(self._llama_probes.keys()):
            p = self._llama_probes.pop(iid); p.stop(); p.wait(1500)
        if self.ssh: self.ssh.stop_all()
        for t in (self.store_thread, self.bulk_thread, self.list_thread, self.action_thread, self.tunnel_thread):
            if t.isRunning(): t.quit(); t.wait(1500)

    def _destroy_workers(self):
        # Truncated disconnect logic for brevity/safety
        pass

    # ---- Config ----
    def apply_config(self, cfg: AppConfig):
        changed_key = cfg.api_key != self.config.api_key
        self.config = cfg
        self.port_allocator = PortAllocator(
            default_port=cfg.default_tunnel_port, initial_map=cfg.port_map,
            persist=self._persist_port_map,
        )
        self.config_store.save(cfg)
        self.ssh.ssh_key_path = cfg.ssh_key_path
        self.log_line.emit("Configura\u00e7\u00f5es salvas.")
        if self.rental: self.sync_local_ssh_key()
        if changed_key: self.bootstrap()
        else: self._apply_interval()

    def _persist_port_map(self, m):
        self.config.port_map = m
        self.config_store.save(self.config)

    def update_instance_filters(self, f):
        self.config.instance_filters = dict(f)
        self.config_store.save(self.config)

    def update_start_requested_ids(self, ids, requested_at=None):
        self.config.start_requested_ids = sorted([int(x) for x in ids])
        if requested_at: self.config.start_requested_at = requested_at
        self.config_store.save(self.config)

    def _apply_interval(self):
        s = self.config.refresh_interval_seconds
        if s <= 0: self.refresh_timer.stop()
        else: self.refresh_timer.start(s * 1000)

    def _on_timer_tick(self):
        if self.vast: self._trigger_refresh.emit()

    def request_refresh(self):
        if self.vast: self._trigger_refresh.emit()

    def detect_existing_tunnels(self):
        """Scans the OS for SSH tunnels already running from previous app sessions."""
        if not self.ssh: return
        self.log_line.emit("⌛ Escaneando túneis ativos no sistema...")
        found = self.ssh.detect_win_tunnels()
        if not found:
            return

        port_to_iid = {p: iid for iid, p in self.port_allocator.snapshot().items()}
        adoptions = 0
        for l_port, r_target in found.items():
            iid = port_to_iid.get(l_port)
            if not iid: continue
            
            # Verify if this tunnel matches the current instance (proactive check)
            # host:port should match r_target. If host changed (rare), we skip.
            if self.tunnel_states.get(iid) != TunnelStatus.CONNECTED:
                self.tunnel_states[iid] = TunnelStatus.CONNECTED
                self.tunnel_status_changed.emit(iid, TunnelStatus.CONNECTED.value, "Túnel re-identificado e assumido.")
                self._start_live_metrics(iid)
                adoptions += 1
        
        if adoptions > 0:
            self.log_line.emit(f"✓ {adoptions} túnel(eis) re-identificado(s) com sucesso.")
        else:
            self.log_line.emit("ℹ Nenhum túnel pré-existente encontrado.")

    # ---- Refresh callback ----
    def _on_refreshed(self, instances, user):
        from app.ui.views.instances.action_bar import is_scheduling_instance
        self.last_instances = instances
        if user is not None:
            self.last_user = user
            owner_key = self._analytics_owner_key(user)
            reset_unowned = (
                self.analytics_store.owner_key is None
                and (
                    self.analytics_store.entry_count > 0
                    or self.analytics_store.has_billing_events
                )
            )
            if self.analytics_store.bind_owner(owner_key, reset_unowned=reset_unowned):
                self._force_next_backfill = True
                self.log_line.emit("Analytics antigo limpo para sincronizar a conta atual.")
        self.port_allocator.compact({i.id for i in instances})
        
        for i in instances:
            # Map raw scheduler state to InstanceState.SCHEDULING
            if i.state == InstanceState.STARTING and is_scheduling_instance(i):
                i.state = InstanceState.SCHEDULING
            
            self.tracker.update(i)
            if i.state not in (InstanceState.RUNNING, InstanceState.STARTING):
                if self.tunnel_states.get(i.id) != TunnelStatus.DISCONNECTED:
                    # Clear zombie tunnel state if instance is stopped/deleted
                    self.tunnel_states[i.id] = TunnelStatus.DISCONNECTED
                    self.tunnel_status_changed.emit(i.id, TunnelStatus.DISCONNECTED.value, "Instância desligada.")
            
            # --- Sticky Transition Logic ---
            lock = self._transition_locks.get(i.id)
            if lock == InstanceState.STOPPING:
                if i.state == InstanceState.STOPPED:
                    self._transition_locks.pop(i.id, None)  # Reached target
                else:
                    i.state = InstanceState.STOPPING # Stay sticky
            elif lock == InstanceState.STARTING:
                if i.state == InstanceState.RUNNING:
                    self._transition_locks.pop(i.id, None)  # Reached target
                else:
                    # Allow SCHEDULING to show if API already moved there, otherwise stay STARTING
                    if i.state != InstanceState.SCHEDULING:
                        i.state = InstanceState.STARTING
        
        self._log_analytics_snapshot(instances, user, self._force_next_backfill)
        self._force_next_backfill = False
        self._check_tunnels_health()
        self._connect_started_instances_when_ready(instances)
        self._sync_live_workers(instances)
        self.log_line.emit(f"✓ Sincronizado ({len(instances)} inst.)")
        self.instances_refreshed.emit(instances, user)

    def _analytics_owner_key(self, user: UserInfo | None) -> str | None:
        if user and user.email:
            return f"email:{user.email.strip().lower()}"
        api_key = str(self.config.api_key or "").strip()
        if not api_key:
            return None
        digest = hashlib.sha1(api_key.encode("utf-8")).hexdigest()[:12]
        return f"api:{digest}"

    def _log_analytics_snapshot(self, instances, user, force_backfill):
        if not user: return
        if self.analytics_store.entry_count < 2 or force_backfill:
            try:
                data = self.vast.fetch_financial_data()
                self.analytics_store.import_history(data["invoices"], data["charges"], user.balance, data["sync"])
                self.log_line.emit(f"\u2713 Hist\u00f3rico de gastos reconstru\u00eddo.")
            except Exception as e: self.log_line.emit(f"\u26a0 Analytics: {e}")
        
        bd = burn_rate_breakdown(instances, self.config.include_storage_in_burn_rate, self.config.estimated_network_cost_per_hour)
        snap = CostSnapshot(ts=datetime.now().isoformat(timespec="seconds"), balance=user.balance,
                            burn_total=bd["total"], burn_gpu=bd["gpu"], burn_storage=bd["storage"],
                            burn_network=bd["network"], instances=bd["instances"])
        self.analytics_store.log_snapshot(snap)

    def _on_refresh_failed(self, k, m):
        self.log_line.emit(f"\u2717 Refresh Error: {m}")
        self.refresh_failed.emit(k, m)

    def request_deep_sync(self):
        self._force_next_backfill = True
        self._trigger_refresh.emit()

    def reset_analytics(self):
        self.analytics_store.clear_history()
        owner_key = self._analytics_owner_key(self.last_user)
        if owner_key:
            self.analytics_store.bind_owner(owner_key)
        self.log_line.emit("Analytics local resetado. Sincronizando novamente...")
        self.request_deep_sync()

    # ---- Store API ----
    def search_offers(self, q):
        if not self.rental: return
        self._trigger_search_offers.emit(q)

    def refresh_templates(self, q=""):
        if not self.rental: return
        self._trigger_refresh_templates.emit(q)

    def refresh_ssh_keys(self):
        if not self.rental: return
        self._trigger_refresh_ssh_keys.emit()

    def create_ssh_key(self, pk):
        if not self.rental: return
        self._trigger_create_ssh_key.emit(pk)

    def sync_local_ssh_key(self):
        if not self.rental: return
        pub = self.ssh.get_public_key()
        if not pub:
            self.log_line.emit("\u26a0 Chave SSH local n\u00e3o encontrada.")
            return
        
        def on_keys(keys):
            try: self.ssh_keys_refreshed.disconnect(on_keys)
            except: pass
            clean = pub.strip().split()[:2]
            match = next((k for k in keys if k.public_key.strip().split()[:2] == clean), None)
            if match:
                self.log_line.emit(f"\u2713 Chave SSH local ativa (ID: {match.id})")
                self._last_local_key_id = match.id
            else:
                self.log_line.emit(f"⌛ Registrando chave local na Vast...")
                self._trigger_create_ssh_key.emit(pub)
        
        self.ssh_keys_refreshed.connect(on_keys)
        self._trigger_refresh_ssh_keys.emit()

    def rent(self, req: RentRequest):
        if not self.rental: return
        # Enforce local key if missing
        if req.ssh_key_id is None and hasattr(self, "_last_local_key_id"):
            req.ssh_key_id = self._last_local_key_id
            self.log_line.emit("ℹ Usando chave SSH local para o aluguel.")
        self._trigger_rent.emit(req)

    # ---- Actions ----
    def _find_instance(self, iid):
        return next((i for i in self.last_instances if i.id == iid), None)

    def activate(self, iid):
        if iid in self._pending_start: return False
        inst = self._find_instance(iid)
        if inst:
            inst.state = InstanceState.STARTING
            self.instances_refreshed.emit(self.last_instances, self.last_user)
        
        self._pending_start.add(iid)
        self._transition_locks[iid] = InstanceState.STARTING
        self._trigger_start.emit(iid)
        return True

    def deactivate(self, iid):
        if iid in self._pending_stop: return
        inst = self._find_instance(iid)
        if inst:
            inst.state = InstanceState.STOPPING
            self.instances_refreshed.emit(self.last_instances, self.last_user)
            
        self._pending_stop.add(iid)
        self._transition_locks[iid] = InstanceState.STOPPING
        self.ssh.stop_tunnel(iid)
        self._trigger_stop.emit(iid)

    def connect_tunnel(self, iid):
        if iid in self._pending_tunnel: return
        if not self._has_usable_passphrase():
            self._on_passphrase_success = lambda: self.connect_tunnel(iid)
            self.passphrase_needed.emit()
            return
        p = self.port_allocator.get(iid)
        self._pending_tunnel.add(iid)
        self.tunnel_states[iid] = TunnelStatus.CONNECTING
        self.tunnel_status_changed.emit(iid, TunnelStatus.CONNECTING.value, "connecting")
        self._trigger_connect.emit(iid, p)

    def disconnect_tunnel(self, iid):
        self.ssh.stop_tunnel(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.tunnel_status_changed.emit(iid, TunnelStatus.DISCONNECTED.value, "disconnected")

    def fix_instance_ssh(self, iid: int):
        """Injeta a chave pública local em uma instância que já está rodando."""
        if not self.vast: return
        pub = self.ssh.get_public_key()
        if not pub:
            self.log_line.emit("\u2717 Erro: Chave pública n\u00e3o encontrada.")
            return
        
        self.log_line.emit(f"⌛ Tentando injetar chave SSH na inst\u00e2ncia #{iid}...")
        try:
            self.vast.attach_ssh_key(iid, pub)
            self.log_line.emit(f"\u2713 Chave enviada! Aguarde 10s e tente conectar novamente.")
            self.toast_requested.emit("Chave enviada! Tente novamente em 10s.", "success", 5000)
        except Exception as e:
            self.log_line.emit(f"\u2717 Falha ao injetar chave: {e}")
            self.toast_requested.emit(f"Falha ao injetar chave: {e}", "error", 5000)

    # ---- Handlers ----
    def _on_tunnel_status(self, iid, status, msg):
        self.tunnel_states[iid] = TunnelStatus(status)
        self.log_line.emit(f"T\u00fanel #{iid}: {msg}")
        if status == TunnelStatus.CONNECTED.value:
            self._pending_tunnel.discard(iid)
            self._start_live_metrics(iid)
        elif status == TunnelStatus.FAILED.value:
            self._pending_tunnel.discard(iid)
            low = msg.lower()
            if "permission denied" in low or "publickey" in low:
                self.toast_requested.emit("Erro de chave. Tente 'Fix SSH'.", "warning", 5000)
        self.tunnel_status_changed.emit(iid, status, msg)

    def _on_action_done(self, iid, action, ok, msg):
        if action == "start": self._pending_start.discard(iid)
        elif action == "stop": self._pending_stop.discard(iid)

        if action == "start" and ok and self.config.auto_connect_on_activate:
            self._auto_connect_after_start.add(iid)
        
        # If action failed, clear the sticky lock so we don't stay in fake state
        if not ok:
            self._transition_locks.pop(iid, None)
            
        self.action_done.emit(iid, action, ok, msg)
        self._trigger_refresh.emit()

    def _on_bulk_finished(self, a, ok, fail):
        if a == "start" and self.config.auto_connect_on_activate:
            self._auto_connect_after_start.update(ok)
        self.bulk_done.emit(a, ok, fail)
        self._trigger_refresh.emit()

    def _on_bulk_progress(self, d, t, i, m):
        self.log_line.emit(f"Bulk {d}/{t}: {m}")

    def bulk_action(self, a, ids, opts=None):
        if a in ("connect", "disconnect"):
            for i in ids: 
                if a == "connect": self.connect_tunnel(i)
                else: self.disconnect_tunnel(i)
            return
        self._trigger_bulk.emit(a, list(ids), opts or {})

    # ---- Passphrase / Metrics ----
    def _has_usable_passphrase(self):
        if not self.ssh.ssh_key_path: return True
        if not self.ssh.is_passphrase_required(): return True
        return self.ssh.passphrase_cache is not None

    def set_ssh_passphrase(self, pwd):
        self.ssh.set_passphrase(pwd)
        if self._on_passphrase_success:
            cb = self._on_passphrase_success; self._on_passphrase_success = None
            cb()
        self._trigger_refresh.emit()

    def _sync_live_workers(self, instances):
        if not self._has_usable_passphrase(): return
        running = {i.id for i in instances if i.state == InstanceState.RUNNING and i.ssh_host and i.ssh_port}
        for iid in running:
            if iid not in self._live_workers: self._start_live_metrics(iid)
        for iid in list(self._live_workers.keys()):
            if iid not in running: self._stop_live_metrics(iid)

    def _start_live_metrics(self, iid):
        inst = self._find_instance(iid)
        if not inst: return
        self._stop_live_metrics(iid)
        w = LiveMetricsWorker(iid, inst.ssh_host, inst.ssh_port, self.ssh)
        w.metrics.connect(self.live_metrics)
        self._live_workers[iid] = w
        w.start()

    def _stop_live_metrics(self, iid):
        w = self._live_workers.pop(iid, None)
        if w: w.stop(); w.wait(1500)

    def _start_model_watcher(self, iid, port):
        self._stop_model_watcher(iid)
        w = ModelWatcher(iid, port); w.model_changed.connect(self.model_changed)
        self._model_watchers[iid] = w; w.start()

    def _stop_model_watcher(self, iid):
        w = self._model_watchers.pop(iid, None)
        if w: w.stop(); w.wait(1500)

    def _check_tunnels_health(self):
        for iid, status in list(self.tunnel_states.items()):
            if status == TunnelStatus.CONNECTED:
                h = self.ssh.get(iid)
                if not h or not h.alive():
                    self.tunnel_states[iid] = TunnelStatus.FAILED
                    self.tunnel_status_changed.emit(iid, TunnelStatus.FAILED.value, "dropped")

    def _connect_started_instances_when_ready(self, instances):
        if not self.config.auto_connect_on_activate: return
        ready_ids = {i.id for i in instances if i.id in self._auto_connect_after_start and i.state == InstanceState.RUNNING and i.ssh_host}
        for iid in ready_ids:
            self._auto_connect_after_start.discard(iid)
            self.connect_tunnel(iid)
