from __future__ import annotations
from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QComboBox, QInputDialog, QLineEdit,
    QStackedWidget,
)
from app.lab.shell import LabShell
from app.config import ConfigStore
from app.models import AppConfig, Instance, InstanceState, TunnelStatus, UserInfo
from app.services.vast_service import VastService
from app.services.ssh_service import SSHService
from app.workers.list_worker import ListWorker
from app.workers.action_worker import ActionWorker
from app.workers.tunnel_starter import TunnelStarter
from app.workers.llama_probe import LlamaReadyProbe
from app.workers.live_metrics import LiveMetricsWorker
from app.workers.model_watcher import ModelWatcher
from app.billing import DailySpendTracker
from app.ui.billing_header import BillingHeader
from app.ui.instance_card import InstanceCard
from app.ui.log_panel import LogPanel
from app.ui.settings_dialog import SettingsDialog
from app.ui.model_manager_dialog import ModelManagerDialog
from app.ui.toast import Toast


class MainWindow(QMainWindow):
    _trigger_refresh = Signal()
    _trigger_start = Signal(int)
    _trigger_stop = Signal(int)
    _trigger_connect = Signal(int, int)

    def __init__(self, config_store: ConfigStore):
        super().__init__()
        self.setWindowTitle("Vast.ai Manager")
        self.resize(960, 800)

        self.config_store = config_store
        self.config = config_store.load()
        self.vast: VastService | None = None
        self.ssh = SSHService(ssh_key_path=self.config.ssh_key_path)
        self.tracker = DailySpendTracker()
        self.cards: dict[int, InstanceCard] = {}
        self.tunnel_states: dict[int, TunnelStatus] = {}
        self.last_instances: list[Instance] = []
        # Debounce guards: instance ids currently mid-action.
        # Prevents double-click / double-signal firing the same work twice.
        self._pending_start: set[int] = set()
        self._pending_stop: set[int] = set()
        self._pending_tunnel: set[int] = set()
        # Active llama-server readiness probes, keyed by instance id.
        # Probe survives dialog close so feedback always reaches the user.
        self._llama_probes: dict[int, LlamaReadyProbe] = {}
        self._open_model_dialogs: dict[int, ModelManagerDialog] = {}
        # Per-instance live SSH metrics streamers. Started when tunnel goes
        # CONNECTED, stopped when it leaves CONNECTED or instance stops.
        self._live_workers: dict[int, LiveMetricsWorker] = {}
        # Per-instance llama-server model watchers — drive the model badge.
        self._model_watchers: dict[int, ModelWatcher] = {}

        # Threads placeholders
        self.list_thread = QThread()
        self.action_thread = QThread()
        self.tunnel_thread = QThread()
        self.list_worker: ListWorker | None = None
        self.action_worker: ActionWorker | None = None
        self.tunnel_starter: TunnelStarter | None = None

        self._build_ui()

        if not self.config.api_key:
            QTimer.singleShot(150, self._open_settings)
        else:
            self._bootstrap_service()

    # ---------- UI ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        # Top-level shell around the existing Cloud UI + the new Lab.
        shell_root = QVBoxLayout(central)
        shell_root.setContentsMargins(0, 0, 0, 0)
        shell_root.setSpacing(0)

        toggle_bar = QWidget()
        toggle_bar.setFixedHeight(44)
        tb = QHBoxLayout(toggle_bar)
        tb.setContentsMargins(16, 6, 16, 6)
        self.toggle_cloud_btn = QPushButton("\u2601  Cloud")
        self.toggle_lab_btn = QPushButton("\u2726  Lab")
        for b in (self.toggle_cloud_btn, self.toggle_lab_btn):
            b.setObjectName("secondary")
            b.setCheckable(True)
            b.setFixedHeight(30)
        self.toggle_cloud_btn.setChecked(True)
        self.toggle_cloud_btn.clicked.connect(lambda: self._switch_workspace("cloud"))
        self.toggle_lab_btn.clicked.connect(lambda: self._switch_workspace("lab"))
        tb.addStretch()
        tb.addWidget(self.toggle_cloud_btn)
        tb.addWidget(self.toggle_lab_btn)
        tb.addStretch()
        shell_root.addWidget(toggle_bar)

        self.workspace_stack = QStackedWidget()
        self.cloud_body = QWidget()
        shell_root.addWidget(self.workspace_stack, 1)

        root = QVBoxLayout(self.cloud_body)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(16)

        # Top bar
        top_bar = QHBoxLayout()
        title = QLabel("Vast.ai Manager")
        title.setObjectName("h1")
        top_bar.addWidget(title)
        top_bar.addStretch()
        self.active_lbl = QLabel("0 ativas")
        self.active_lbl.setObjectName("secondary")
        top_bar.addWidget(self.active_lbl)

        self.refresh_interval_combo = QComboBox()
        self.refresh_interval_combo.addItems(["↺ 5s", "↺ 10s", "↺ 30s", "↺ 60s", "↺ off"])
        idx_map = {5: 0, 10: 1, 30: 2, 60: 3, 0: 4}
        self.refresh_interval_combo.setCurrentIndex(idx_map.get(self.config.refresh_interval_seconds, 2))
        self.refresh_interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        top_bar.addWidget(self.refresh_interval_combo)

        self.manual_refresh_btn = QPushButton("Atualizar")
        self.manual_refresh_btn.setObjectName("secondary")
        self.manual_refresh_btn.clicked.connect(self._on_manual_refresh)
        top_bar.addWidget(self.manual_refresh_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("secondary")
        self.settings_btn.setFixedWidth(40)
        self.settings_btn.clicked.connect(self._open_settings)
        top_bar.addWidget(self.settings_btn)
        root.addLayout(top_bar)

        # Billing header
        self.billing = BillingHeader(config=self.config)
        root.addWidget(self.billing)

        # Scrollable instance list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(14)

        self.empty_lbl = QLabel("Conecte sua API key para ver suas instâncias.")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setObjectName("secondary")
        self.empty_lbl.setStyleSheet("padding: 60px 0; font-size: 12pt;")
        self.list_layout.addWidget(self.empty_lbl)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        # Log
        self.log = LogPanel()
        root.addWidget(self.log)

        # Auto-refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_timer_tick)

        # Register Cloud body + Lab shell in the workspace stack.
        self.workspace_stack.addWidget(self.cloud_body)
        self.lab_shell = LabShell(self.config, self.config_store, self.ssh)
        self.workspace_stack.addWidget(self.lab_shell)
        self.workspace_stack.setCurrentWidget(self.cloud_body)

    def _switch_workspace(self, key: str):
        if key == "cloud":
            self.workspace_stack.setCurrentWidget(self.cloud_body)
            self.toggle_cloud_btn.setChecked(True)
            self.toggle_lab_btn.setChecked(False)
        else:
            self.workspace_stack.setCurrentWidget(self.lab_shell)
            self.toggle_cloud_btn.setChecked(False)
            self.toggle_lab_btn.setChecked(True)

    # ---------- Workers bootstrap ----------

    def _bootstrap_service(self):
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
        self.log.log("Conectando à Vast.ai...")
        self._trigger_refresh.emit()

    def _destroy_workers(self):
        # Disconnect signals only if we've previously bootstrapped (workers exist)
        if self.list_worker is not None:
            for sig in (self._trigger_refresh, self._trigger_start,
                        self._trigger_stop, self._trigger_connect):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        for t in (self.list_thread, self.action_thread, self.tunnel_thread):
            if t.isRunning():
                t.quit()
                t.wait(1500)

    def _apply_interval(self):
        secs = self.config.refresh_interval_seconds
        if secs <= 0:
            self.refresh_timer.stop()
        else:
            self.refresh_timer.start(secs * 1000)

    def _on_interval_changed(self, idx: int):
        mapping = {0: 5, 1: 10, 2: 30, 3: 60, 4: 0}
        self.config.refresh_interval_seconds = mapping[idx]
        self.config_store.save(self.config)
        self._apply_interval()

    def _on_timer_tick(self):
        if self.vast is not None:
            self._trigger_refresh.emit()

    def _on_manual_refresh(self):
        if self.vast is None:
            self._open_settings()
            return
        self._trigger_refresh.emit()

    # ---------- Settings ----------

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, cfg: AppConfig):
        changed_key = cfg.api_key != self.config.api_key
        self.config = cfg
        self.config_store.save(cfg)
        self.ssh.ssh_key_path = cfg.ssh_key_path
        self.billing.apply_config(cfg)
        self.log.log("Configurações salvas.")
        # Sync combo to new interval
        idx_map = {5: 0, 10: 1, 30: 2, 60: 3, 0: 4}
        self.refresh_interval_combo.setCurrentIndex(idx_map.get(cfg.refresh_interval_seconds, 2))
        if changed_key:
            self._bootstrap_service()
        else:
            self._apply_interval()
            # Re-render cards with new port
            self._rebuild_cards(self.last_instances)

    # ---------- Refresh ----------

    def _on_refreshed(self, instances: list, user: object):
        self.last_instances = instances
        for inst in instances:
            self.tracker.update(inst)
        self._rebuild_cards(instances)
        self.billing.update_values(user, instances, self.tracker.today_spend())
        active = sum(1 for i in instances if i.state == InstanceState.RUNNING)
        label = f"{active} ativa" if active == 1 else f"{active} ativas"
        self.active_lbl.setText(label)
        self._check_tunnels_health()
        # Ensure live-metrics workers match the set of RUNNING instances we
        # can SSH into without prompting the user. This is what makes a freshly
        # discovered active instance light up immediately, with no extra clicks.
        self._sync_live_workers(instances)

    def _on_refresh_failed(self, kind: str, message: str):
        self.log.log(f"Erro ({kind}): {message}")
        if kind == "auth":
            Toast(self, "API key inválida", "error")
            self._open_settings()
        elif kind == "network":
            Toast(self, "Sem conexão com Vast.ai", "warning")
        else:
            Toast(self, f"Falha: {message[:80]}", "error")

    def _rebuild_cards(self, instances: list):
        current_ids = {i.id for i in instances}
        for iid in list(self.cards.keys()):
            if iid not in current_ids:
                card = self.cards.pop(iid)
                self.list_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
                self.tunnel_states.pop(iid, None)

        self.empty_lbl.setVisible(not bool(instances))

        for inst in instances:
            tunnel_status = self.tunnel_states.get(inst.id, TunnelStatus.DISCONNECTED)
            if inst.id in self.cards:
                self.cards[inst.id].update_from(inst, tunnel_status, self.config.default_tunnel_port)
            else:
                card = InstanceCard(inst)
                card.activate_requested.connect(self._on_activate)
                card.deactivate_requested.connect(self._on_deactivate)
                card.reconnect_requested.connect(self._on_reconnect)
                card.disconnect_requested.connect(self._on_disconnect)
                card.open_terminal_requested.connect(self._on_open_terminal)
                card.models_requested.connect(self._on_manage_models)
                card.copy_endpoint_requested.connect(self._on_copy_endpoint)
                card.update_from(inst, tunnel_status, self.config.default_tunnel_port)
                # Insert before the final stretch
                insert_at = max(0, self.list_layout.count() - 1)
                self.list_layout.insertWidget(insert_at, card)
                self.cards[inst.id] = card

    # ---------- Actions ----------

    def _find_instance(self, iid: int) -> Instance | None:
        return next((i for i in self.last_instances if i.id == iid), None)

    def _on_activate(self, iid: int):
        if iid in self._pending_start:
            return
        # If auto-connect is on, the SSH tunnel will be started right after the
        # instance reports running. Prompt for passphrase NOW so cancelling
        # aborts the whole activation — not just the tunnel — and the user
        # doesn't get billed for a VM they decided not to connect to.
        if self.config.auto_connect_on_activate and not self._ensure_passphrase():
            self.log.log(f"Ativação de #{iid} cancelada (passphrase não fornecida).")
            return
        self._pending_start.add(iid)
        self.log.log(f"Ativando instância {iid}...")
        self._trigger_start.emit(iid)

    def _ensure_passphrase(self) -> bool:
        """Prompt for SSH passphrase if needed, validating it locally with
        ssh-keygen so we never proceed (and bill the user) on a wrong password.
        Returns False if the user cancelled."""
        if not self.ssh.is_passphrase_required() or self.ssh.passphrase_cache:
            return True
        prompt = "Digite a passphrase da sua chave SSH para continuar:"
        for _ in range(5):  # cap attempts; user can always cancel
            pwd, ok = QInputDialog.getText(
                self, "Chave SSH Protegida", prompt, QLineEdit.Password,
            )
            if not ok:
                return False
            if not pwd:
                prompt = "Passphrase vazia. Tente novamente ou cancele:"
                continue
            if self.ssh.verify_passphrase(pwd):
                self.ssh.set_passphrase(pwd)
                return True
            prompt = "Passphrase incorreta. Tente novamente ou cancele:"
        Toast(self, "Muitas tentativas incorretas. Operação cancelada.", "error")
        return False

    def _on_deactivate(self, iid: int):
        if iid in self._pending_stop:
            return
        reply = QMessageBox.question(
            self, "Desativar instância",
            "Tem certeza? A máquina será parada e a conexão encerrada.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._pending_stop.add(iid)
        self.ssh.stop_tunnel(iid)
        self._stop_live_metrics(iid)
        self._stop_model_watcher(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.log.log(f"Desativando instância {iid}...")
        self._trigger_stop.emit(iid)

    def _on_reconnect(self, iid: int):
        self._start_tunnel_for(iid)

    def _on_disconnect(self, iid: int):
        self.ssh.stop_tunnel(iid)
        self._stop_live_metrics(iid)
        self._stop_model_watcher(iid)
        self.tunnel_states[iid] = TunnelStatus.DISCONNECTED
        self._pending_tunnel.discard(iid)
        self.log.log(f"Conexão #{iid} encerrada.")
        self._refresh_card(iid)

    def _on_open_terminal(self, iid: int):
        inst = self._find_instance(iid)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            Toast(self, "SSH indisponível para esta instância", "warning")
            return
        try:
            self.ssh.open_terminal(inst.ssh_host, inst.ssh_port, self.config.terminal_preference)
            self.log.log(f"Terminal aberto para {inst.ssh_host}:{inst.ssh_port}")
        except FileNotFoundError:
            Toast(self, "Terminal não encontrado. Verifique Windows Terminal / cmd.", "error")
        except Exception as e:
            Toast(self, f"Falha ao abrir terminal: {e}", "error")

    def _on_manage_models(self, iid: int):
        inst = self._find_instance(iid)
        if not inst:
            Toast(self, "Instância não encontrada para gerenciar modelos.", "error")
            return
        if not inst.ssh_host or not inst.ssh_port:
            Toast(self, "Instância sem SSH disponível.", "warning")
            return
        # Switch to Lab workspace with this instance selected
        self._switch_workspace("lab")
        self.lab_shell.select_instance(
            iid, inst.gpu_name or "",
            inst.ssh_host, inst.ssh_port,
        )

    @Slot(int, str, str)
    def _on_deploy_status(self, iid: int, kind: str, msg: str):
        if kind == "started":
            self.log.log(f"ModelManager #{iid}: {msg}")
            self._start_llama_probe(iid)
        elif kind == "failed":
            self.log.log(f"ModelManager #{iid}: ✗ {msg}")

    def _start_llama_probe(self, iid: int):
        # Stop any prior probe for this instance (e.g. user re-deployed)
        self._stop_llama_probe(iid)
        probe = LlamaReadyProbe(local_port=self.config.default_tunnel_port,
                                timeout_s=300)
        probe.progress.connect(lambda e, h, i=iid: self._on_llama_progress(i, e, h))
        probe.ready.connect(lambda mid, i=iid: self._on_llama_ready(i, mid))
        probe.failed.connect(lambda r, i=iid: self._on_llama_failed(i, r))
        self._llama_probes[iid] = probe
        probe.start()

    def _stop_llama_probe(self, iid: int):
        probe = self._llama_probes.pop(iid, None)
        if probe is not None:
            probe.stop()
            probe.wait(2000)

    def _on_llama_progress(self, iid: int, elapsed: int, hint: str):
        # Throttled log: every 15s
        if elapsed > 0 and elapsed % 15 == 0:
            self.log.log(f"ModelManager #{iid}: ⏳ carregando modelo... {elapsed}s")

    def _on_llama_ready(self, iid: int, model_id: str):
        self._stop_llama_probe(iid)
        self.log.log(f"ModelManager #{iid}: ✓ modelo pronto — {model_id}")
        Toast(self, f"Modelo carregado: {model_id}", "success", duration_ms=4000)

    def _on_llama_failed(self, iid: int, reason: str):
        self._stop_llama_probe(iid)
        self.log.log(f"ModelManager #{iid}: ✗ {reason}")
        Toast(self, "Modelo não respondeu. Veja o log.", "error", duration_ms=5000)

    # ---------- Live metrics over SSH ----------

    def _can_ssh_silently(self) -> bool:
        """Can we open an SSH connection without prompting the user?
        - No key configured: ssh will fall back to defaults / agent.
        - Key not encrypted: nothing to ask.
        - Key encrypted: only if we already cached the passphrase.
        Used to decide whether to eagerly start the live-metrics worker."""
        if not self.ssh.ssh_key_path:
            return True
        if not self.ssh.is_passphrase_required():
            return True
        return self.ssh.passphrase_cache is not None

    def _sync_live_workers(self, instances: list):
        """Reconcile live-metrics workers with the current instance list.
        Starts a worker for every RUNNING instance we can SSH into silently;
        stops workers for anything that no longer qualifies."""
        if not self._can_ssh_silently():
            # Without credentials we can't start any new worker, but we should
            # also not tear down ones that were started after a successful
            # tunnel connect (they're still alive on the cached connection).
            return
        running_ids = {
            i.id for i in instances
            if i.state == InstanceState.RUNNING and i.ssh_host and i.ssh_port
        }
        for iid in running_ids:
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
        for iid in list(self._live_workers.keys()):
            if iid not in running_ids:
                self._stop_live_metrics(iid)

    def _start_live_metrics(self, iid: int):
        """Spawn a per-instance SSH-based metrics streamer. Replaces any prior
        worker for the same instance."""
        self._stop_live_metrics(iid)
        inst = self._find_instance(iid)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            return
        worker = LiveMetricsWorker(iid, inst.ssh_host, inst.ssh_port, self.ssh)
        worker.metrics.connect(self._on_live_metrics)
        worker.error.connect(lambda i, e: self.log.log(f"Métricas live #{i}: {e}"))
        self._live_workers[iid] = worker
        worker.start()

    def _stop_live_metrics(self, iid: int):
        worker = self._live_workers.pop(iid, None)
        if worker is not None:
            worker.stop()
            worker.wait(2000)
        card = self.cards.get(iid)
        if card is not None:
            card.clear_live_metrics()

    # ---------- Loaded-model watcher ----------

    def _start_model_watcher(self, iid: int):
        self._stop_model_watcher(iid)
        watcher = ModelWatcher(iid, self.config.default_tunnel_port)
        watcher.model_changed.connect(self._on_model_changed)
        self._model_watchers[iid] = watcher
        watcher.start()

    def _stop_model_watcher(self, iid: int):
        w = self._model_watchers.pop(iid, None)
        if w is not None:
            w.stop()
            w.wait(2000)
        card = self.cards.get(iid)
        if card is not None:
            card.set_loaded_model(None)

    @Slot(int, str)
    def _on_model_changed(self, iid: int, model_id: str):
        card = self.cards.get(iid)
        if card is None:
            return
        card.set_loaded_model(model_id or None)
        if model_id:
            self.log.log(f"#{iid}: modelo ativo — {model_id}")

    @Slot(int, dict)
    def _on_live_metrics(self, iid: int, d: dict):
        card = self.cards.get(iid)
        if card is not None:
            card.set_live_metrics(d)

    def _on_copy_endpoint(self, iid: int):
        clip = QGuiApplication.clipboard()
        clip.setText(f"http://127.0.0.1:{self.config.default_tunnel_port}")
        Toast(self, "Endereço copiado", "success", duration_ms=1500)

    def _on_action_done(self, iid: int, action: str, ok: bool, msg: str):
        if action == "start":
            self._pending_start.discard(iid)
        elif action == "stop":
            self._pending_stop.discard(iid)
        if ok:
            self.log.log(f"✓ {action} #{iid}: {msg}")
            if action == "start" and self.config.auto_connect_on_activate:
                self._start_tunnel_for(iid)
            Toast(self, msg, "success")
        else:
            self.log.log(f"✗ {action} #{iid}: {msg}")
            Toast(self, f"Falha: {msg[:80]}", "error")
        self._trigger_refresh.emit()

    def _start_tunnel_for(self, iid: int):
        if iid in self._pending_tunnel:
            return
        if not self._ensure_passphrase():
            self.log.log(f"Conexão de #{iid} cancelada (passphrase não fornecida).")
            return
        self._pending_tunnel.add(iid)
        self.tunnel_states[iid] = TunnelStatus.CONNECTING
        self._refresh_card(iid)
        self.log.log(f"Conectando #{iid}...")
        self._trigger_connect.emit(iid, self.config.default_tunnel_port)

    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        self.tunnel_states[iid] = TunnelStatus(status)
        self.log.log(f"Túnel #{iid}: {msg}")
        self._refresh_card(iid)
        if self.tunnel_states[iid] == TunnelStatus.CONNECTED:
            self._pending_tunnel.discard(iid)
            # Tunnel up confirms SSH works — start live metrics if not already.
            if iid not in self._live_workers:
                self._start_live_metrics(iid)
            self._start_model_watcher(iid)
            Toast(self, f"Conectado em http://127.0.0.1:{self.config.default_tunnel_port}", "success")
        elif self.tunnel_states[iid] == TunnelStatus.FAILED:
            self._pending_tunnel.discard(iid)
            if "permission denied" in msg.lower() or "publickey" in msg.lower() or "host key verification failed" in msg.lower():
                self.ssh.clear_passphrase()
                # Bad credentials → metrics worker is also doomed, kill it.
                self._stop_live_metrics(iid)
            self._stop_model_watcher(iid)
            Toast(self, "Falha na conexão. Veja o log.", "error", duration_ms=4000)

    def _refresh_card(self, iid: int):
        card = self.cards.get(iid)
        inst = self._find_instance(iid)
        if card and inst:
            card.update_from(
                inst,
                self.tunnel_states.get(iid, TunnelStatus.DISCONNECTED),
                self.config.default_tunnel_port,
            )

    def _check_tunnels_health(self):
        for iid, status in list(self.tunnel_states.items()):
            if status == TunnelStatus.CONNECTED:
                handle = self.ssh.get(iid)
                if handle is None or not handle.alive():
                    self.tunnel_states[iid] = TunnelStatus.FAILED
                    self._stop_live_metrics(iid)
                    self._stop_model_watcher(iid)
                    self.log.log(f"Conexão #{iid} caiu.")
                    self._refresh_card(iid)
        # Also stop live metrics for instances that left RUNNING since last refresh.
        running_ids = {i.id for i in self.last_instances if i.state == InstanceState.RUNNING}
        for iid in list(self._live_workers.keys()):
            if iid not in running_ids:
                self._stop_live_metrics(iid)
        for iid in list(self._model_watchers.keys()):
            if iid not in running_ids:
                self._stop_model_watcher(iid)

    # ---------- Window events ----------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reposition toasts stack when window resizes
        for t in list(Toast._stack):
            t._reposition_stack()

    def closeEvent(self, event):
        self.refresh_timer.stop()
        for iid in list(self._llama_probes.keys()):
            self._stop_llama_probe(iid)
        for iid in list(self._live_workers.keys()):
            self._stop_live_metrics(iid)
        for iid in list(self._model_watchers.keys()):
            self._stop_model_watcher(iid)
        self.ssh.stop_all()
        self._destroy_workers()
        super().closeEvent(event)
