from __future__ import annotations
from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QComboBox, QInputDialog, QLineEdit,
    QStackedWidget,
)
from app.lab.shell import LabShell
from app.controller import AppController
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

        self.controller = AppController(config_store, self)

        self.cards: dict[int, InstanceCard] = {}
        self.tunnel_states: dict[int, TunnelStatus] = {}
        self.last_instances: list[Instance] = []
        self._open_model_dialogs: dict[int, ModelManagerDialog] = {}

        self._build_ui()

        self.controller.instances_refreshed.connect(self._on_refreshed)
        self.controller.refresh_failed.connect(self._on_refresh_failed)
        self.controller.tunnel_status_changed.connect(self._on_tunnel_status)
        self.controller.action_done.connect(self._on_action_done)
        self.controller.live_metrics.connect(self._on_live_metrics)
        self.controller.model_changed.connect(self._on_model_changed)
        self.controller.log_line.connect(self.log.log)
        self.controller.passphrase_needed.connect(self._prompt_passphrase)

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

        # Register Cloud body + Lab shell in the workspace stack.
        self.workspace_stack.addWidget(self.cloud_body)
        self.lab_shell = LabShell(self.config, self.config_store, self.controller.ssh)
        self.lab_shell.attach_controller(self.controller)
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
        self.controller.bootstrap()

    def _on_interval_changed(self, idx: int):
        mapping = {0: 5, 1: 10, 2: 30, 3: 60, 4: 0}
        self.config.refresh_interval_seconds = mapping[idx]
        self.config_store.save(self.config)
        self.controller.apply_config(self.config)

    def _on_manual_refresh(self):
        self.controller.request_refresh()

    def open_settings(self):
        self._open_settings()

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, cfg: AppConfig):
        self.config = cfg
        self.billing.apply_config(cfg)
        idx_map = {5: 0, 10: 1, 30: 2, 60: 3, 0: 4}
        self.refresh_interval_combo.setCurrentIndex(idx_map.get(cfg.refresh_interval_seconds, 2))
        
        self.controller.apply_config(cfg)
        self._rebuild_cards(self.controller.last_instances)

    def _on_refreshed(self, instances: list, user: object):
        self.last_instances = instances
        self._rebuild_cards(instances)
        self.billing.update_values(user, instances, self.controller.today_spend())
        active = sum(1 for i in instances if i.state == InstanceState.RUNNING)
        label = f"{active} ativa" if active == 1 else f"{active} ativas"
        self.active_lbl.setText(label)

    def _on_refresh_failed(self, kind: str, message: str):
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
                insert_at = max(0, self.list_layout.count() - 1)
                self.list_layout.insertWidget(insert_at, card)
                self.cards[inst.id] = card

    def _find_instance(self, iid: int) -> Instance | None:
        return next((i for i in self.last_instances if i.id == iid), None)

    def _on_activate(self, iid: int):
        self.controller.activate(iid)

    def _prompt_passphrase(self):
        if not self.controller.ssh.is_passphrase_required() or self.controller.ssh.passphrase_cache:
            return True
        prompt = "Digite a passphrase da sua chave SSH para continuar:"
        for _ in range(5):
            pwd, ok = QInputDialog.getText(
                self, "Chave SSH Protegida", prompt, QLineEdit.Password,
            )
            if not ok:
                return False
            if not pwd:
                prompt = "Passphrase vazia. Tente novamente ou cancele:"
                continue
            if self.controller.ssh.verify_passphrase(pwd):
                self.controller.ssh.set_passphrase(pwd)
                return True
            prompt = "Passphrase incorreta. Tente novamente ou cancele:"
        Toast(self, "Muitas tentativas incorretas. Operação cancelada.", "error")
        return False

    def _on_deactivate(self, iid: int):
        reply = QMessageBox.question(
            self, "Desativar instância",
            "Tem certeza? A máquina será parada e a conexão encerrada.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.controller.deactivate(iid)

    def _on_reconnect(self, iid: int):
        self.controller.connect_tunnel(iid)

    def _on_disconnect(self, iid: int):
        self.controller.disconnect_tunnel(iid)

    def _on_open_terminal(self, iid: int):
        inst = self._find_instance(iid)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            Toast(self, "SSH indisponível para esta instância", "warning")
            return
        try:
            self.controller.ssh.open_terminal(inst.ssh_host, inst.ssh_port, self.config.terminal_preference)
        except Exception as e:
            Toast(self, f"Falha ao abrir terminal: {e}", "error")

    def _on_manage_models(self, iid: int):
        inst = self._find_instance(iid)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            return
        self._switch_workspace("lab")
        self.lab_shell.select_instance(
            iid, inst.gpu_name or "", inst.ssh_host, inst.ssh_port,
        )

    @Slot(int, str, str)
    def _on_tunnel_status(self, iid: int, status: str, msg: str):
        self.tunnel_states[iid] = TunnelStatus(status)
        self._refresh_card(iid)
        if TunnelStatus(status) == TunnelStatus.CONNECTED:
            Toast(self, f"Conectado em http://127.0.0.1:{self.config.default_tunnel_port}", "success")
        elif TunnelStatus(status) == TunnelStatus.FAILED:
            Toast(self, "Falha na conexão. Veja o log.", "error", duration_ms=4000)

    @Slot(int, str)
    def _on_model_changed(self, iid: int, model_id: str):
        card = self.cards.get(iid)
        if card:
            card.set_loaded_model(model_id or None)

    @Slot(int, dict)
    def _on_live_metrics(self, iid: int, d: dict):
        card = self.cards.get(iid)
        if card:
            card.set_live_metrics(d)

    def _on_copy_endpoint(self, iid: int):
        clip = QGuiApplication.clipboard()
        clip.setText(f"http://127.0.0.1:{self.config.default_tunnel_port}")
        Toast(self, "Endereço copiado", "success", duration_ms=1500)

    def _on_action_done(self, iid: int, action: str, ok: bool, msg: str):
        if ok:
            Toast(self, msg, "success")
        else:
            Toast(self, f"Falha: {msg[:80]}", "error")

    def _refresh_card(self, iid: int):
        card = self.cards.get(iid)
        inst = self._find_instance(iid)
        if card and inst:
            card.update_from(
                inst,
                self.tunnel_states.get(iid, TunnelStatus.DISCONNECTED),
                self.config.default_tunnel_port,
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reposition toasts stack when window resizes
        for t in list(Toast._stack):
            t._reposition_stack()

    def closeEvent(self, event):
        self.controller.shutdown()
        super().closeEvent(event)
