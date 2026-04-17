"""LabShell V2 \u2014 remote instance-first AI Lab workspace.
Manages views, workers, and wiring against a selected Vast.ai instance."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QStackedWidget, QLabel, QVBoxLayout, QMessageBox,
)
from PySide6.QtCore import Qt, Slot
from app.lab import theme as t
from app.ui.components.nav_rail import NavRail, NAV_ITEMS
from app.lab.state.store import LabStore
from app.lab.state.models import RemoteGGUF, ServerParams
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
        self._probe_worker: RemoteProbeWorker | None = None
        self._setup_worker: RemoteSetupWorker | None = None

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
        self.dashboard.probe_requested.connect(self._probe_instance)
        self.dashboard.setup_requested.connect(self._run_setup)
        self.dashboard.navigate_requested.connect(self._go)

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
        self.models_view.rescan_requested.connect(self._probe_instance)
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

        self._controller: AppController | None = None
        self._switch("dashboard")

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
        """Wire the app controller into the shell. Builds and registers the
        Instances view. Idempotent."""
        if self._controller is not None:
            return
        self._controller = controller
        self.instances = InstancesView(controller, self)
        self._add_view("instances", self.instances)
        self.instances.open_lab_requested.connect(self._on_open_lab_from_card)
        self.instances.open_settings_requested.connect(
            lambda: self.parent() and self.parent().open_settings())
        # Make Instances the landing view
        self._switch("instances")
        self.nav.set_active("instances")

    def _on_open_lab_from_card(self, iid: int):
        """User clicked "Abrir no Lab" on an instance card. Select the instance
        and jump to Dashboard."""
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst:
            return
        self.select_instance(iid, inst.gpu_name or "",
                              inst.ssh_host or "", inst.ssh_port or 0)
        self._go("dashboard")

    # --- Instance selection (called from MainWindow) ---

    def select_instance(self, iid: int, gpu_name: str,
                        ssh_host: str, ssh_port: int):
        """Called when user opens Lab for a specific instance."""
        self._host = ssh_host
        self._port = ssh_port
        self.store.set_instance(iid)
        self.dashboard.set_instance_info(iid, gpu_name, ssh_host)
        self._probe_instance()

    # --- Remote probe ---

    def _probe_instance(self):
        if not self._ssh or not self._host or not self._port:
            QMessageBox.warning(self, "No Instance",
                                "Select an instance with SSH access first.")
            return
        if self._probe_worker and self._probe_worker.isRunning():
            return
        self.store.set_busy("probe", True)
        self._probe_worker = RemoteProbeWorker(
            self._ssh, self._host, self._port, self)
        self._probe_worker.setup_ready.connect(self.store.set_setup_status)
        self._probe_worker.system_ready.connect(self.store.set_remote_system)
        self._probe_worker.models_ready.connect(self.store.set_remote_models)
        self._probe_worker.gguf_ready.connect(self.store.set_remote_gguf)
        self._probe_worker.failed.connect(
            lambda msg: QMessageBox.warning(self, "Probe Failed", msg))
        self._probe_worker.finished.connect(
            lambda: self.store.set_busy("probe", False))
        self._probe_worker.start()

    # --- Remote setup ---

    def _run_setup(self, what: str):
        if not self._ssh or not self._host:
            return
        if self._setup_worker and self._setup_worker.isRunning():
            QMessageBox.information(self, "Busy",
                                    "A setup operation is already running.")
            return

        if what == "all":
            # Chain: install llmfit → start serve → install llamacpp
            self._chain_setup(["install_llmfit", "start_llmfit", "install_llamacpp"])
            return

        self._run_single_setup(what if what != "llamacpp" else "install_llamacpp")

    def _chain_setup(self, actions: list[str]):
        if not actions:
            self._probe_instance()
            return
        action = actions.pop(0)
        self.store.set_busy("setup", True)
        self._setup_worker = RemoteSetupWorker(
            self._ssh, self._host, self._port, action)
        self._setup_worker.progress.connect(
            lambda msg: self.dashboard.setup_status_lbl.setText(msg))
        self._setup_worker.finished.connect(
            lambda ok, out: self._on_chain_step_done(ok, out, actions))
        self._setup_worker.start()

    def _on_chain_step_done(self, ok: bool, output: str, remaining: list[str]):
        self.store.set_busy("setup", False)
        if not ok:
            self.dashboard.setup_status_lbl.setText(f"Setup step failed: {output[:200]}")
            self._probe_instance()
            return
        if remaining:
            self._chain_setup(remaining)
        else:
            self.dashboard.setup_status_lbl.setText("Setup complete! Probing...")
            self._probe_instance()

    def _run_single_setup(self, action: str, **kwargs):
        self.store.set_busy("setup", True)
        self._setup_worker = RemoteSetupWorker(
            self._ssh, self._host, self._port, action, **kwargs)
        self._setup_worker.progress.connect(
            lambda msg: self.dashboard.setup_status_lbl.setText(msg))
        self._setup_worker.finished.connect(self._on_setup_done)
        self._setup_worker.start()

    def _on_setup_done(self, ok: bool, output: str):
        self.store.set_busy("setup", False)
        if ok:
            self.dashboard.setup_status_lbl.setText("Done! Refreshing...")
            self._probe_instance()
        else:
            self.dashboard.setup_status_lbl.setText(f"Failed: {output[:200]}")

    # --- LLMfit model refresh ---

    def _refresh_llmfit_models(self, use_case: str, search: str):
        if not self._ssh or not self._host:
            return
        from app.lab.services.remote_llmfit import build_models_query
        script = build_models_query(use_case=use_case, search=search)
        self.store.set_busy("discover", True)

        worker = RemoteSetupWorker(
            self._ssh, self._host, self._port, "_raw_script")
        # Patch the script builder for this one-off
        worker._build_script = lambda: script
        worker.finished.connect(self._on_llmfit_models_done)
        worker.start()
        self._setup_worker = worker  # keep reference

    def _on_llmfit_models_done(self, ok: bool, output: str):
        self.store.set_busy("discover", False)
        if ok:
            data = parse_json_output(output)
            if data:
                self.store.set_remote_models(parse_models(data))

    # --- Download model ---

    def _download_model_by_name(self, model_name: str, quant: str):
        """User clicked Download in Discover. We need a repo_id and filename.
        For now, use the model name as search hint — TODO: map properly."""
        QMessageBox.information(
            self, "Download",
            f"To download a model, go to Models \u2192 check if it's already there,\n"
            f"or use SSH to manually download:\n\n"
            f"Model: {model_name}\nQuant: {quant}\n\n"
            f"Full HuggingFace download support coming in the next update.")

    # --- Model operations ---

    def _load_model(self, path: str):
        self.configure.select_model(path)
        self._go("configure")

    def _delete_model(self, path: str):
        if not self._ssh or not self._host:
            return
        self._run_single_setup("delete_model", path=path)

    # --- Server operations ---

    def _launch_server(self, params: ServerParams):
        if not self._ssh or not self._host:
            return
        binary = self.store.setup_status.llamacpp_path or ""
        self.store.set_busy("launch", True)

        worker = RemoteSetupWorker(
            self._ssh, self._host, self._port,
            "launch_server", params=params, binary_path=binary)
        worker.finished.connect(self._on_launch_done)
        worker.start()
        self._setup_worker = worker

    def _on_launch_done(self, ok: bool, output: str):
        self.store.set_busy("launch", False)
        if ok and "LAUNCH_OK" in output:
            self._go("monitor")
            self._probe_instance()  # refresh status
        else:
            QMessageBox.warning(self, "Launch Failed",
                                f"llama-server failed to start:\n{output[:500]}")

    def _stop_server(self):
        if not self._ssh or not self._host:
            return
        self._run_single_setup("stop_server")

    def _restart_server(self):
        params = self.store.server_params
        if params.model_path:
            self._launch_server(params)
        else:
            QMessageBox.information(self, "No Config",
                                    "No previous config. Go to Configure first.")

    def _fetch_log(self):
        if not self._ssh or not self._host:
            return
        ok, output = self._ssh.run_script(
            self._host, self._port, script_fetch_log())
        self.monitor.set_log(output if ok else f"(SSH failed)\n{output}")
