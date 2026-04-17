"""LabShell V2 — remote instance-first AI Lab workspace.
Manages views, workers, and wiring against a selected Vast.ai instance."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QStackedWidget, QLabel, QVBoxLayout, QMessageBox,
)
from PySide6.QtCore import Qt, Slot, QTimer
from app import theme as t
from app.ui.components.nav_rail import NavRail, NAV_ITEMS
from app.lab.state.store import LabStore
from app.lab.state.models import RemoteGGUF, ServerParams
from app.models import TunnelStatus
from app.lab.views.dashboard_view import DashboardView
from app.lab.views.discover_view import DiscoverView
from app.lab.views.models_view import ModelsView
from app.controller import AppController
from app.ui.views.instances_view import InstancesView
from app.lab.views.configure_view import ConfigureView
from app.lab.views.monitor_view import MonitorView
from app.lab.workers.remote_probe import RemoteProbeWorker
from app.lab.workers.remote_setup_worker import RemoteSetupWorker
from app.lab.services.remote_llmfit import (
    build_models_query, parse_models, parse_json_output,
)
from app.lab.services.remote_setup import script_fetch_log


class AppShell(QWidget):
    def __init__(self, config=None, config_store=None,
                 ssh_service=None, parent=None):
        super().__init__(parent)
        self.setObjectName("app-shell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.store = LabStore(self)
        self._config = config
        self._config_store = config_store
        self._ssh = ssh_service
        self._host: str = ""
        self._port: int = 0
        
        self._probe_workers: dict[int, RemoteProbeWorker] = {}
        self._setup_workers: dict[int, RemoteSetupWorker] = {}
        self._controller: AppController | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavRail(self)
        self.nav.selected.connect(self._switch)
        root.addWidget(self.nav)

        self.stack = QStackedWidget(self)
        self._views: dict[str, QWidget] = {}
        root.addWidget(self.stack, 1)

        # --- Dashboard ---
        self.dashboard = DashboardView(self.store, self)
        self._add_view("dashboard", self.dashboard)
        self.dashboard.probe_requested.connect(self._manual_probe)
        self.dashboard.setup_requested.connect(self._run_setup)
        self.dashboard.navigate_requested.connect(self._go)
        # New: Dashboard emits iid for actions
        self.dashboard.instance_action_requested.connect(self._on_dashboard_instance_action)

        # --- Discover ---
        self.discover = DiscoverView(self.store, self)
        self._add_view("discover", self.discover)
        self.discover.refresh_requested.connect(self._refresh_llmfit_models)
        self.discover.download_requested.connect(self._download_model_by_name)

        # --- Models ---
        self.models_view = ModelsView(self.store, self)
        self._add_view("models", self.models_view)
        self.models_view.load_requested.connect(self._load_model)
        self.models_view.delete_requested.connect(self._delete_model)
        self.models_view.rescan_requested.connect(self._manual_probe)
        self.models_view.navigate_requested.connect(self._go)

        # --- Configure ---
        self.configure = ConfigureView(self.store, self)
        self._add_view("configure", self.configure)
        self.configure.launch_requested.connect(self._launch_server)

        # --- Monitor ---
        self.monitor = MonitorView(self.store, self)
        self._add_view("monitor", self.monitor)
        self.monitor.stop_requested.connect(self._stop_server)
        self.monitor.restart_requested.connect(self._restart_server)
        self.monitor.fetch_log_requested.connect(self._fetch_log)
        self.monitor.navigate_requested.connect(self._go)

        self._switch("dashboard")

        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+R"), self,
                  activated=lambda: self._controller and self._controller.request_refresh())
        QShortcut(QKeySequence("Ctrl+,"), self,
                  activated=lambda: self.window().open_settings()
                                     if hasattr(self.window(), "open_settings") else None)

    # --- View management ---

    def _add_view(self, key: str, widget: QWidget):
        self.stack.addWidget(widget)
        self._views[key] = widget

    def _switch(self, key: str):
        v = self._views.get(key)
        if v is not None:
            self.stack.setCurrentWidget(v)

    def _go(self, key: str):
        self.nav.set_active(key)
        self._switch(key)

    def attach_controller(self, controller: AppController):
        if self._controller is not None:
            return
        self._controller = controller
        self.instances = InstancesView(controller, self)
        self._add_view("instances", self.instances)
        self.instances.open_lab_requested.connect(self._on_open_lab_from_card)
        self.instances.open_settings_requested.connect(
            lambda: self.parent() and self.parent().open_settings())
        
        # Proactive: listen to tunnel status
        controller.tunnel_status_changed.connect(self._on_tunnel_status_changed)
        # Sync dashboard with current active instances
        controller.instances_refreshed.connect(self.dashboard.sync_instances)
        
        # Landing view
        self._switch("instances")
        self.nav.set_active("instances")

    def _on_tunnel_status_changed(self, iid: int, status: str, msg: str):
        if status == TunnelStatus.CONNECTED.value:
            # Automatic probe!
            QTimer.singleShot(500, lambda: self._probe_instance(iid))

    def _on_open_lab_from_card(self, iid: int):
        """User clicked "Abrir no Lab" on an instance card. Select the instance
        and jump to Dashboard."""
        self.select_instance(iid)
        self._go("dashboard")

    def _on_dashboard_instance_action(self, iid: int, action: str):
        """Action requested from a specific dashboard card."""
        if action == "select":
            self.select_instance(iid)
        elif action == "probe":
            self._probe_instance(iid)
        elif action == "setup_all":
            self._run_setup("all", iid=iid)

    # --- Instance selection ---

    def select_instance(self, iid: int):
        """Focus the entire Lab on a specific instance (Discover, Models, etc.)"""
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst:
            return
        
        self._host = inst.ssh_host or ""
        self._port = inst.ssh_port or 0
        self.store.set_instance(iid)
        
        # Ensure it has been probed at least once
        if not self.store.get_state(iid).setup.probed:
            self._probe_instance(iid)

    def _manual_probe(self):
        """Trigger probe for the CURRENT selected instance."""
        if self.store.selected_instance_id:
            self._probe_instance(self.store.selected_instance_id)

    # --- Remote probe ---

    def _probe_instance(self, iid: int):
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            return
        
        if iid in self._probe_workers and self._probe_workers[iid].isRunning():
            return
            
        self.store.set_instance_busy(iid, "probe", True)
        worker = RemoteProbeWorker(self._ssh, inst.ssh_host, inst.ssh_port, self)
        self._probe_workers[iid] = worker
        
        worker.setup_ready.connect(lambda s: self.store.set_setup_status(iid, s))
        worker.system_ready.connect(lambda s: self.store.set_remote_system(iid, s))
        worker.models_ready.connect(lambda m: self.store.set_remote_models(iid, m))
        worker.gguf_ready.connect(lambda g: self.store.set_remote_gguf(iid, g))
        
        worker.finished.connect(lambda: self.store.set_instance_busy(iid, "probe", False))
        worker.start()

    # --- Remote setup ---

    def _run_setup(self, what: str, iid: int = None):
        if iid is None:
            iid = self.store.selected_instance_id
        if iid is None:
            return
            
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host:
            return
            
        if iid in self._setup_workers and self._setup_workers[iid].isRunning():
            return

        if what == "all":
            self._chain_setup(["install_llmfit", "start_llmfit", "install_llamacpp"], iid)
            return

        self._run_single_setup(what if what != "llamacpp" else "install_llamacpp", iid=iid)

    def _chain_setup(self, actions: list[str], iid: int):
        if not actions:
            self._probe_instance(iid)
            return
        action = actions.pop(0)
        self.store.set_instance_busy(iid, "setup", True)
        
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        worker = RemoteSetupWorker(self._ssh, inst.ssh_host, inst.ssh_port, action)
        self._setup_workers[iid] = worker
        
        # TODO: how to show progress per card? For now we can use toast or global log
        worker.progress.connect(lambda msg: self._controller.log_line.emit(f"#{iid}: {msg}"))
        worker.finished.connect(lambda ok, out: self._on_chain_step_done(ok, out, actions, iid))
        worker.start()

    def _on_chain_step_done(self, ok: bool, output: str, remaining: list[str], iid: int):
        self.store.set_instance_busy(iid, "setup", False)
        if not ok:
            self._controller.log_line.emit(f"#{iid} Setup step failed: {output[:100]}")
            return
        if remaining:
            self._chain_setup(remaining, iid)
        else:
            self._probe_instance(iid)

    def _run_single_setup(self, action: str, iid: int, **kwargs):
        self.store.set_instance_busy(iid, "setup", True)
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        worker = RemoteSetupWorker(self._ssh, inst.ssh_host, inst.ssh_port, action, **kwargs)
        self._setup_workers[iid] = worker
        worker.finished.connect(lambda ok, out: self._on_setup_done(ok, out, iid))
        worker.start()

    def _on_setup_done(self, ok: bool, output: str, iid: int):
        self.store.set_instance_busy(iid, "setup", False)
        if ok:
            self._probe_instance(iid)
        else:
            self._controller.log_line.emit(f"#{iid} Setup failed: {output[:100]}")

    # --- LLMfit model refresh ---

    def _refresh_llmfit_models(self, use_case: str, search: str):
        iid = self.store.selected_instance_id
        if not iid or not self._ssh: return
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host: return

        script = build_models_query(use_case=use_case, search=search)
        self.store.set_instance_busy(iid, "discover", True)

        worker = RemoteSetupWorker(self._ssh, inst.ssh_host, inst.ssh_port, "_raw_script")
        worker._build_script = lambda: script
        worker.finished.connect(lambda ok, out: self._on_llmfit_models_done(ok, out, iid))
        worker.start()
        self._setup_workers[iid] = worker

    def _on_llmfit_models_done(self, ok: bool, output: str, iid: int):
        self.store.set_instance_busy(iid, "discover", False)
        if ok:
            data = parse_json_output(output)
            if data:
                self.store.set_remote_models(iid, parse_models(data))

    # --- Download model ---

    def _download_model_by_name(self, model_name: str, quant: str):
        QMessageBox.information(self, "Download", "Full HuggingFace download support coming soon.")

    # --- Model operations ---

    def _load_model(self, path: str):
        self.configure.select_model(path)
        self._go("configure")

    def _delete_model(self, path: str):
        iid = self.store.selected_instance_id
        if iid: self._run_single_setup("delete_model", iid, path=path)

    # --- Server operations ---

    def _launch_server(self, params: ServerParams):
        iid = self.store.selected_instance_id
        if not iid: return
        st = self.store.get_state(iid)
        binary = st.setup.llamacpp_path or ""
        self.store.set_instance_busy(iid, "launch", True)

        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        worker = RemoteSetupWorker(self._ssh, inst.ssh_host, inst.ssh_port,
                                    "launch_server", params=params, binary_path=binary)
        worker.finished.connect(lambda ok, out: self._on_launch_done(ok, out, iid))
        worker.start()
        self._setup_workers[iid] = worker

    def _on_launch_done(self, ok: bool, output: str, iid: int):
        self.store.set_instance_busy(iid, "launch", False)
        if ok and "LAUNCH_OK" in output:
            if iid == self.store.selected_instance_id:
                self._go("monitor")
            self._probe_instance(iid)
        else:
            self._controller.log_line.emit(f"#{iid} Launch failed.")

    def _stop_server(self):
        iid = self.store.selected_instance_id
        if iid: self._run_single_setup("stop_server", iid)

    def _restart_server(self):
        iid = self.store.selected_instance_id
        if not iid: return
        params = self.store.get_state(iid).server_params
        if params.model_path:
            self._launch_server(params)

    def _fetch_log(self):
        iid = self.store.selected_instance_id
        if not iid or not self._ssh: return
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host: return
        ok, output = self._ssh.run_script(inst.ssh_host, inst.ssh_port, script_fetch_log())
        self.monitor.set_log(output if ok else f"(SSH failed)\n{output}")
