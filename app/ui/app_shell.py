"""LabShell V2 — remote instance-first AI Lab workspace.
Manages views, workers, and wiring against a selected Vast.ai instance."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QStackedWidget, QLabel, QVBoxLayout,
)
from PySide6.QtCore import Qt, Slot, QTimer
from app import theme as t
from app.ui.components.nav_rail import NavRail
from app.lab.state.store import LabStore
from app.lab.state.models import ServerParams
from app.models import TunnelStatus
from app.lab.views.discover_view import DiscoverView
from app.lab.views.models_view import ModelsView
from app.lab.views.studio_view import StudioView
from app.controller import AppController
from app.ui.views.instances.instances_view import InstancesView
from app.ui.views.analytics_view import AnalyticsView
from app.ui.views.store_view import StoreView
from app.ui.views.settings_view import SettingsView
from app.lab.views.hardware_view import HardwareView
from app.lab.workers.remote_probe import RemoteProbeWorker
from app.lab.workers.remote_setup_worker import RemoteSetupWorker
from app.lab.workers.streaming_worker import StreamingRemoteWorker
from app.lab.services.job_registry import JobRegistry
from app.lab.services.progress_parsers import parse_cmake_build_stage, parse_wget_progress
from app.lab.services.remote_setup import (
    script_download_model,
    script_fetch_log,
    script_install_llamacpp,
    script_wipe_llamacpp,
)
from app.ui.dialogs import UpdateSelectionDialog
from app.ui.components.title_bar import TitleBar


# View key → readable label for the title bar
_VIEW_LABELS = {
    "instances": "Instances",
    "store": "Store",
    "analytics": "Analytics",
    "studio": "Studio",
    "hardware": "Hardware",
    "discover": "Discover Models",
    "install": "Install",
    "models": "Models",
    "settings": "Settings",
}


class AppShell(QWidget):
    def __init__(self, config=None, config_store=None,
                 ssh_service=None, analytics_store=None, parent=None):
        super().__init__(parent)
        self.setObjectName("app-shell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.store = LabStore(self)
        import pathlib
        jobs_path = pathlib.Path.home() / ".vastai-app" / "jobs.json"
        self.job_registry = JobRegistry(persist_path=str(jobs_path), parent=self)
        self.job_registry.load_from_disk()
        self._config = config
        self._config_store = config_store
        self._ssh = ssh_service
        from app.services.port_allocator import PortAllocator
        self.studio_port_allocator = PortAllocator(
            default_port=12000,
            initial_map=self._config.studio_port_map if self._config else {},
            persist=self._persist_studio_port_map
        )
        self.analytics_store = analytics_store
        self._controller = None
        self._current_view = ""
        self._analytics_api_sync_pending = False
        
        self._host: str = ""
        self._port: int = 0
        
        self._probe_workers: dict[int, RemoteProbeWorker] = {}
        self._probe_callbacks: dict[int, callable] = {}
        self._setup_workers: dict[int, RemoteSetupWorker] = {}
        self._setup_cooldowns: dict[int, float] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Left Sidebar (Full Height)
        self.nav = NavRail(self)
        self.nav.selected.connect(self._switch)
        root.addWidget(self.nav)

        # 2. Right Side Content (Header + Views)
        self.right_container = QWidget()
        self.right_lay = QVBoxLayout(self.right_container)
        self.right_lay.setContentsMargins(0, 0, 0, 0)
        self.right_lay.setSpacing(0)
        
        # Add TitleBar to the right header
        self.title_bar = TitleBar(self.window())
        self.right_lay.addWidget(self.title_bar)
        
        # Stacked Widget for views
        self.stack = QStackedWidget(self)
        self._views: dict[str, QWidget] = {}
        self.right_lay.addWidget(self.stack, 1)
        
        root.addWidget(self.right_container, 1)

        # --- Studio ---
        self.studio = StudioView(self.store, self)
        self._add_view("studio", self.studio)
        self.studio.launch_requested.connect(self._launch_server)
        self.studio.stop_requested.connect(self._stop_server)
        self.studio.fix_requested.connect(self._apply_diagnostic_fix)

        # --- Discover ---
        self.discover = DiscoverView(self.store, self.job_registry, self)
        self._add_view("discover", self.discover)
        self.discover.download_requested.connect(self._download_model_by_name)
        self.discover.setup_requested.connect(self._setup_environment_job)
        self.discover.wipe_requested.connect(self._wipe_environment)
        self.discover.cancel_requested.connect(self._cancel_job)
        self.discover.resume_requested.connect(self._resume_job)
        self.discover.discard_requested.connect(self._discard_job)
        self.discover.back_requested.connect(lambda: self._go("studio"))
        self.discover.instances_requested.connect(lambda: self._go("instances"))

        # --- Models ---
        self.models = ModelsView(self.store, self)
        self._add_view("models", self.models)
        self.models.delete_requested.connect(self._delete_model)
        self.models.rescan_requested.connect(self._manual_probe)
        self.models.navigate_requested.connect(self._go)
        self.models.launch_requested.connect(self._launch_server)

        # --- Hardware ---
        self.hardware = HardwareView(self.store, self)
        self._add_view("hardware", self.hardware)

        # --- Analytics (NEW) ---
        self.analytics = AnalyticsView(self._config, analytics_store=self.analytics_store, parent=self)
        self._add_view("analytics", self.analytics)

        # --- Settings (NEW) ---
        self.settings_view = SettingsView(self._config, self)
        self._add_view("settings", self.settings_view)
        self.settings_view.back_requested.connect(
            lambda: self._go("instances")
        )

        self._switch("studio")

        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+R"), self,
                  activated=lambda: self._controller and self._controller.request_refresh())
        QShortcut(QKeySequence("Ctrl+,"), self,
                  activated=lambda: self._go("settings"))

    # --- View management ---

    def _add_view(self, key: str, widget: QWidget):
        self.stack.addWidget(widget)
        self._views[key] = widget

    def _switch(self, key: str):
        v = self._views.get(key)
        if v is not None:
            entering_analytics = key == "analytics" and self._current_view != "analytics"
            self.stack.setCurrentWidget(v)
            self.title_bar.setPageTitle(_VIEW_LABELS.get(key, key.title()))
            self._current_view = key
            if entering_analytics:
                self._request_analytics_api_sync()
            if key == "store" and hasattr(v, "enter_view"):
                v.enter_view()

    def _go(self, key: str):
        self.nav.set_active(key)
        self._switch(key)

    def attach_controller(self, controller: AppController):
        if self._controller is not None:
            return
        self._controller = controller
        self.instances = InstancesView(controller, self, store=self.store)
        self._add_view("instances", self.instances)
        self.store_view = StoreView(controller, self)
        self._add_view("store", self.store_view)
        self.instances.activate_requested.connect(controller.activate)
        self.instances.deactivate_requested.connect(controller.deactivate)
        self.instances.connect_requested.connect(controller.connect_tunnel)
        self.instances.disconnect_requested.connect(controller.disconnect_tunnel)
        self.instances.fix_ssh_requested.connect(controller.fix_instance_ssh)
        self.instances.set_label_requested.connect(self._on_set_label)
        self.instances.bulk_requested.connect(controller.bulk_action)
        self.instances.open_lab_requested.connect(self._on_open_lab_from_card)
        self.instances.open_settings_requested.connect(
            lambda: self._go("settings")
        )
        self.instances.open_logs_requested.connect(
            lambda: controller.toast_requested.emit(
                "Use o ícone de log em cada card para logs filtrados.", "info", 2500
            )
        )
        self.instances.open_analytics_requested.connect(
            lambda: self._go("analytics")
        )
        
        # Proactive: listen to tunnel status
        controller.tunnel_status_changed.connect(self._on_tunnel_status_changed)
        controller.instances_refreshed.connect(self.instances.handle_refresh)
        # Sync Studio and hardware with current active instances
        controller.instances_refreshed.connect(
            lambda instances, *_: self.studio.refresh_instances(
                [i.id for i in instances if i.ssh_host]
            )
        )
        controller.instances_refreshed.connect(self.hardware.sync_instances)
        controller.instances_refreshed.connect(self._try_reattach_jobs_once)
        # Bridge real-time metrics back to the Lab store
        controller.live_metrics.connect(self._on_live_metrics_bridge)
        # Sync analytics
        controller.instances_refreshed.connect(self._sync_analytics)
        controller.refresh_failed.connect(lambda *_: setattr(self, "_analytics_api_sync_pending", False))

        # Settings wiring
        self.settings_view.load_config(controller.config)
        self.settings_view.saved.connect(self._on_settings_saved)

        # Wire persistent analytics store from controller
        self.analytics.set_store(controller.analytics_store)
        
        # Models connections
        self.models.back_requested.connect(lambda: self._go("studio"))
        
        # Landing view
        self._switch("instances")
        self.nav.set_active("instances")

    def _sync_analytics(self, instances, user_info):
        self._analytics_api_sync_pending = False
        ctrl = self._controller
        self.analytics.sync(
            instances, user_info,
            ctrl.today_spend() if ctrl else 0.0,
            week_spend=ctrl.week_spend() if ctrl else None,
            month_spend=ctrl.month_spend() if ctrl else None,
        )

    def _request_analytics_api_sync(self):
        if self._controller is None or self._controller.vast is None:
            return
        if self._analytics_api_sync_pending:
            return
        self._analytics_api_sync_pending = True
        self._controller.log_line.emit("Sincronizando Analytics com a API da Vast.ai...")
        self._controller.request_deep_sync()

    def _on_settings_saved(self, cfg):
        """Handle settings save from the inline view."""
        if self._controller:
            self._controller.apply_config(cfg)
            self._controller.config_store.save(cfg)
            if hasattr(self.instances, "billing"):
                self.instances.billing.apply_config(cfg)
            self.analytics.apply_config(cfg)

    def _on_tunnel_status_changed(self, iid: int, status: str, msg: str):
        if status == TunnelStatus.CONNECTED.value:
            # Automatic probe!
            self._probe_instance(iid)

    def _on_live_metrics_bridge(self, iid: int, data: dict):
        """Bridge metrics from AppController into the Lab store."""
        if self.store:
            self.store.update_telemetry(iid, data)

    def _on_open_lab_from_card(self, iid: int):
        """User clicked "Open Lab" on an instance card."""
        self.select_instance(iid)
        self._go("studio")

    def _on_set_label(self, iid: int, label: str) -> None:
        if self._controller is None or self._controller.vast is None:
            return
        try:
            self._controller.vast.set_label(iid, label)
            self._controller.toast_requested.emit(
                f"Label aplicado em #{iid}", "success", 2000
            )
            self._controller.request_refresh()
        except Exception as exc:
            self._controller.toast_requested.emit(
                f"Falha ao definir label: {exc}", "error", 4000
            )

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

    def _probe_instance(self, iid: int, callback: callable | None = None):
        if callback:
            self._probe_callbacks[iid] = callback
            
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host or not inst.ssh_port:
            return
        
        if iid in self._probe_workers and self._probe_workers[iid].isRunning():
            return
            
        self.store.set_instance_busy(iid, "probe", True)
        worker = RemoteProbeWorker(self._ssh, inst.ssh_host, inst.ssh_port, self)
        self._probe_workers[iid] = worker
        
        worker.setup_ready.connect(lambda s: self._on_probe_status_ready(iid, s))
        worker.system_ready.connect(lambda s: self.store.set_remote_system(iid, s))
        worker.models_ready.connect(lambda m: self.store.set_remote_models(iid, m))
        worker.gguf_ready.connect(lambda g: self.store.set_remote_gguf(iid, g))
        
        worker.finished.connect(lambda: self._on_probe_done(iid))
        worker.failed.connect(lambda msg: self._controller.log_line.emit(f"#{iid} Probe error: {msg}"))
        worker.start()

    def _on_probe_status_ready(self, iid: int, status):
        import time
        now = time.time()
        
        # Guard: if we just installed it, don't let a "no" from probe revert it for 15s
        if not status.llamacpp_installed and iid in self._setup_cooldowns:
            if now - self._setup_cooldowns[iid] < 15.0:
                status.llamacpp_installed = True
            else:
                self._setup_cooldowns.pop(iid)
                
        self.store.set_setup_status(iid, status)
        
        # Proactive Reattachment Logic
        if status.llama_server_running and iid == self.store.selected_instance_id:
            # Check if we need to open the WebUI
            if self.studio.launch_status.text().strip().endswith("Idle") or "error" in self.studio.launch_status.text().lower():
                inst = next((i for i in self._controller.last_instances if i.id == iid), None)
                if inst and inst.ssh_host:
                    remote_port = status.llama_server_port or 11434
                    local_port = self.studio_port_allocator.get(iid)
                    self._ssh.start_tunnel(iid, inst.ssh_host, inst.ssh_port, remote_port, local_port)
                    self.studio.open_webui(local_port)
                    self._controller.log_line.emit(f"#{iid}: Reattached to running server on port {remote_port}")

    def _on_probe_done(self, iid: int):
        self.store.set_instance_busy(iid, "probe", False)
        
        # Execute pending callback if any
        callback = self._probe_callbacks.pop(iid, None)
        if callback:
            QTimer.singleShot(100, callback)
            
        # Cleanup worker ref after small delay to be safe
        QTimer.singleShot(100, lambda: self._probe_workers.pop(iid, None))

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

        st = self.store.get_state(iid)
        is_installed = st.setup.llmfit_installed and st.setup.llamacpp_installed
        
        if what == "all":
            if is_installed:
                self._show_update_dialog(iid)
                return
            else:
                self._chain_setup(["install_llmfit", "start_llmfit", "install_llamacpp"], iid)
                return

        self._run_single_setup(what if what != "llamacpp" else "install_llamacpp", iid=iid)

    def _show_update_dialog(self, iid: int):
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst: return
        
        dlg = UpdateSelectionDialog(iid, self._ssh, inst.ssh_host, inst.ssh_port, self)
        if dlg.exec():
            actions = dlg.get_selection()
            if actions:
                # User confirmed components - start real setup
                self._chain_setup(actions, iid)

    def _chain_setup(self, actions: list[str], iid: int):
        if not actions:
            self._probe_instance(iid)
            return
        action = actions.pop(0)
        self.store.set_instance_busy(iid, "setup", True)
        
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        worker = RemoteSetupWorker(self._ssh, inst.ssh_host, inst.ssh_port, action)
        self._setup_workers[iid] = worker
        
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

    def _setup_environment_job(self, iid: int):
        """Standardized environment setup using the Job System for visibility."""
        if not iid or not self._controller or not self._ssh:
            return

        state = self.store.get_state(iid)
        if state.setup.llamacpp_installed:
            return

        if not self.job_registry.can_start(iid):
            self._controller.toast_requested.emit(
                f"A job is already running on #{iid}.", "warning", 2500
            )
            return

        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host:
            return

        from app.lab.state.models import JobDescriptor, build_job_key
        import time

        key = build_job_key(iid, "SYSTEM", "SETUP")
        desc = JobDescriptor(
            key=key,
            iid=iid,
            repo_id="Environment",
            filename="llama.cpp (CUDA Build)",
            quant="SETUP",
            size_bytes=0,
            needs_llamacpp=True,
            remote_state_path=f"/workspace/.vastai-app/jobs/{key}.json",
            remote_log_path=f"/tmp/install-{key}.log",
            started_at=time.time(),
        )
        self.job_registry.start_job(desc)

        script = script_install_llamacpp(job_key=key)
        worker = StreamingRemoteWorker(self._ssh, inst.ssh_host, inst.ssh_port, script, self)
        self._setup_workers[iid] = worker

        def on_line(line: str):
            event = parse_cmake_build_stage(line)
            if event.stage == "done":
                # Instant success! Don't wait for SSH closure
                self._on_install_done_registry(True, "Success confirmed via log", key, iid)
            elif event.stage != "unknown":
                self.job_registry.update(key, stage=event.stage, percent=event.percent or 100 if event.stage == "done" else 0)

        worker.line.connect(on_line)
        worker.line.connect(lambda l: self.discover.side_panel.append_log(key, l))
        worker.finished.connect(lambda ok, out: self._on_install_done_registry(ok, out, key, iid))
        self.job_registry.update(key, stage="apt", percent=0)
        worker.start()

    def _wipe_environment(self, iid: int):
        """Recursive deletion of llama.cpp to test fresh setup."""
        if not iid or not self._controller or not self._ssh:
            return
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host:
            return

        self.store.set_instance_busy(iid, "setup", True)
        
        def on_done(ok, out):
            self.store.set_instance_busy(iid, "setup", False)
            if ok:
                st = self.store.get_state(iid)
                st.setup.llamacpp_installed = False
                self.store.set_setup_status(iid, st.setup)
                self._controller.log_line.emit(f"#{iid}: Environment wiped.")
                self._probe_instance(iid)
            else:
                self._controller.log_line.emit(f"#{iid}: Wipe failed: {out[:100]}")

        worker = RemoteSetupWorker(self._ssh, inst.ssh_host, inst.ssh_port, "wipe_llamacpp")
        self._setup_workers[iid] = worker
        worker.finished.connect(on_done)
        worker.start()

    def _run_single_setup(self, action: str, iid: int, callback: callable | None = None, **kwargs):
        self.store.set_instance_busy(iid, "setup", True)
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        worker = RemoteSetupWorker(self._ssh, inst.ssh_host, inst.ssh_port, action, **kwargs)
        self._setup_workers[iid] = worker
        worker.finished.connect(lambda ok, out: self._on_setup_done(ok, out, iid, callback))
        worker.start()

    def _on_setup_done(self, ok: bool, output: str, iid: int, callback: callable | None = None):
        self.store.set_instance_busy(iid, "setup", False)
        if ok:
            # Chain the callback through the probe to ensure store sync
            self._probe_instance(iid, callback=callback)
        else:
            self._controller.log_line.emit(f"#{iid} Setup failed: {output[:100]}")

    # --- LLMfit model refresh ---

    def _refresh_llmfit_models(self, use_case: str, search: str):
        """Score the bundled catalog locally against every known instance."""
        from app.lab.services.fit_scorer import InstanceFitScorer
        from app.lab.services.model_catalog import ModelCatalog

        catalog = ModelCatalog.bundled()
        entries = catalog.filter(use_case=use_case or "all", search=search or "")
        scorer = InstanceFitScorer()

        ids = list(self.store.all_instance_ids()) or (
            [self.store.selected_instance_id] if self.store.selected_instance_id else []
        )
        for iid in ids:
            system = self.store.get_state(iid).system
            scored = [scorer.score(entry, system) for entry in entries]
            self.store.set_scored_models(iid, scored)

    # --- Download model ---

    def _download_model_by_name(self, iid: int, model_name: str, quant: str):
        """Start a remote install/download job.

        ``quant`` is the full GGUF filename in the current Discover flow.
        """
        if not iid or not self._controller or not self._ssh:
            return

        if not self.job_registry.can_start(iid):
            self._controller.toast_requested.emit(
                f"Install already running on #{iid}.", "warning", 2500
            )
            return

        self.store.set_instance(iid) # Ensure the store is focused on the target instance
        self._install_retry_iid = iid
        self._install_retry_model = model_name
        self._install_retry_quant = quant

        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host:
            return

        state = self.store.get_state(iid)
        
        # We no longer rely on scored_models for the repo, as we search HF directly
        # The model_name passed from DiscoverView is the HF repo ID (e.g., "bartowski/Meta-Llama-3-8B-Instruct-GGUF")
        repo = model_name
        
        # The filename is passed directly from the selected HFModelFile
        filename = quant # In the new flow, 'quant' parameter is actually the full filename
        import re
        import time

        match = re.search(r'-(Q\d_[A-Z0-9_]+)\.gguf$', filename, re.I)
        quant_token = match.group(1).upper() if match else "UNKNOWN"

        needs_install = not state.setup.llamacpp_installed
        from app.lab.state.models import JobDescriptor, build_job_key

        key = build_job_key(iid, repo, quant_token)
        desc = JobDescriptor(
            key=key,
            iid=iid,
            repo_id=repo,
            filename=filename,
            quant=quant_token,
            size_bytes=0,
            needs_llamacpp=needs_install,
            remote_state_path=f"/workspace/.vastai-app/jobs/{key}.json",
            remote_log_path=f"/tmp/install-{key}.log",
            started_at=time.time(),
        )
        self.job_registry.start_job(desc)

        script_parts: list[str] = []
        if needs_install:
            script_parts.append(script_install_llamacpp(job_key=key))
        script_parts.append(script_download_model(repo, filename, job_key=key))
        full_script = "\n".join(script_parts)

        worker = StreamingRemoteWorker(
            self._ssh,
            inst.ssh_host,
            inst.ssh_port,
            full_script,
            self,
        )
        self._setup_workers[iid] = worker
        log_tail: list[str] = []
        progress_state = {
            "phase": "install" if needs_install else "download",
            "percent": 0,
        }

        def on_line(line: str):
            log_tail.append(line)
            if len(log_tail) > 200:
                del log_tail[:100]

            if progress_state["phase"] == "install":
                event = parse_cmake_build_stage(line)
                if event.stage == "done":
                    # Proactive phase skip
                    self.job_registry.update(key, stage="download", percent=0)
                    progress_state["phase"] = "download"
                    return

                if event.stage != "unknown":
                    percent = (
                        event.percent
                        if event.percent is not None
                        else progress_state["percent"]
                    )
                    progress_state["percent"] = percent
                    self.job_registry.update(key, stage=event.stage, percent=percent)
                return

            event = parse_wget_progress(line)
            if event is not None:
                self.job_registry.update(key, stage="download", percent=event.percent, speed=event.speed)
            elif "DOWNLOAD_DONE" in line:
                self.job_registry.update(key, stage="done", percent=100)

        worker.line.connect(on_line)
        worker.line.connect(lambda l: self.discover.side_panel.append_log(key, l))
        worker.finished.connect(lambda ok, out: self._on_install_done_registry(ok, out, key, iid))
        self.job_registry.update(key, stage="apt" if needs_install else "download", percent=0)
        worker.start()

    def _on_install_done_registry(self, ok: bool, output: str, key: str, iid: int):
        desc = self.job_registry.get(key)
        if not desc:
            return  # Already handled by proactive trigger
        self.job_registry.finish(key, ok=ok, error=(output[-200:] if not ok else None))
        
        # Proactive sync: if we just installed llamacpp, update store immediately
        if ok and desc and desc.needs_llamacpp:
            import time
            self._setup_cooldowns[iid] = time.time()
            st = self.store.get_state(iid)
            st.setup.llamacpp_installed = True
            self.store.set_setup_status(iid, st.setup)
            
        self._probe_instance(iid)

    def _cancel_job(self, key: str) -> None:
        desc = self.job_registry.get(key)
        if desc is None or self._ssh is None or self._controller is None:
            return
        inst = next((i for i in self._controller.last_instances if i.id == desc.iid), None)
        if not inst or not inst.ssh_host:
            return
        from app.lab.services.remote_setup import script_cancel_job

        self._ssh.run_script(inst.ssh_host, inst.ssh_port, script_cancel_job(key))
        self.job_registry.update(key, stage="cancelled")
        self.job_registry.finish(key, ok=False, error="cancelled")

    def _resume_job(self, key: str) -> None:
        desc = self.job_registry.get(key)
        if desc is None:
            return
        self.job_registry.drop(key)
        self._download_model_by_name(desc.iid, desc.repo_id, desc.filename)

    def _discard_job(self, key: str) -> None:
        desc = self.job_registry.get(key)
        if desc is None:
            return
        if self._ssh is not None and self._controller is not None:
            inst = next((i for i in self._controller.last_instances if i.id == desc.iid), None)
            if inst and inst.ssh_host:
                from app.lab.services.remote_setup import script_cancel_job

                self._ssh.run_script(inst.ssh_host, inst.ssh_port, script_cancel_job(key))
        self.job_registry.drop(key)

    def _try_reattach_jobs_once(self, instances, _user=None):
        if getattr(self, "_reattach_done", False):
            return
        self._reattach_done = True
        if self._ssh is None:
            return

        from app.lab.workers.remote_job_probe import RemoteJobProbe

        self._job_probes: dict[str, RemoteJobProbe] = {}
        for key, desc in self.job_registry.active_items():
            inst = next((i for i in instances if i.id == desc.iid), None)
            if not inst or not inst.ssh_host:
                continue
            probe = RemoteJobProbe(self._ssh, inst.ssh_host, inst.ssh_port, desc, self)
            self._job_probes[key] = probe
            probe.result.connect(
                lambda status, state, d=desc: self._on_job_probe(d, status, state)
            )
            probe.finished.connect(lambda k=key: self._job_probes.pop(k, None))
            probe.start()

    def _on_job_probe(self, desc, status: str, state: dict):
        if status == "DONE":
            self.job_registry.finish(desc.key, ok=True)
            if self._controller:
                self._controller.toast_requested.emit(
                    f"Install of {desc.filename} completed on #{desc.iid}.", "success", 3000
                )
            self._probe_instance(desc.iid)
            return
        if status == "MISSING":
            self.job_registry.drop(desc.key)
            return
        if status == "STALE":
            self.discover.side_panel.show_stale(desc, state)
            return
        if status != "RUNNING":
            return

        self.job_registry.update(
            desc.key,
            stage=state.get("stage", desc.stage),
            percent=state.get("percent", desc.percent),
            bytes_downloaded=state.get("bytes_downloaded", desc.bytes_downloaded),
        )
        self._reattach_stream(desc)
        self.job_registry.mark_reattached(desc.key)
        if self._controller:
            self._controller.toast_requested.emit(
                f"Reattached to install on #{desc.iid}.", "info", 3000
            )

    def _reattach_stream(self, desc) -> None:
        if self._controller is None or self._ssh is None:
            return
        inst = next((i for i in self._controller.last_instances if i.id == desc.iid), None)
        if not inst or not inst.ssh_host:
            return
        tail_script = f'tail -n +1 -f "{desc.remote_log_path}"'
        worker = StreamingRemoteWorker(self._ssh, inst.ssh_host, inst.ssh_port, tail_script, self)
        self._setup_workers[desc.iid] = worker
        key = desc.key

        def on_line(line: str):
            event = parse_wget_progress(line)
            if event is not None:
                self.job_registry.update(key, stage="download", percent=event.percent, speed=event.speed)
                return
            build_event = parse_cmake_build_stage(line)
            if build_event.stage != "unknown":
                current = self.job_registry.get(key)
                self.job_registry.update(
                    key,
                    stage=build_event.stage,
                    percent=build_event.percent or (current.percent if current else 0),
                )
                return
            if "DOWNLOAD_DONE" in line:
                self.job_registry.update(key, stage="done", percent=100)
                self.job_registry.finish(key, ok=True)
                worker.requestInterruption()

        worker.line.connect(on_line)
        worker.start()

    # --- Model operations ---

    def _load_model(self, path: str):
        # We don't switch to a separate view anymore, just make sure we are on models view
        self._go("models")
        # The models view should probably auto-expand this path
        self.models._expanded_path = path
        self.models._render(self.store.get_state(self.store.selected_instance_id).gguf if self.store.selected_instance_id else [])

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
        self.store.set_server_params(iid, params)

        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst:
            return
        from app.lab.services.model_params import build_launch_script

        script = build_launch_script(params, binary) + "\n" + (
            "timeout 20 tail -n 40 -f /tmp/llama-server.log 2>/dev/null || true\n"
        )
        worker = StreamingRemoteWorker(
            self._ssh,
            inst.ssh_host,
            inst.ssh_port,
            script,
            self,
        )
        def handle_line(line):
            self.studio.append_launch_log(line)
            # Instant launch trigger - wait for slots to be idle for absolute stability
            lowered = line.lower()
            if "all slots are idle" in lowered:
                self._establish_studio_tunnel(iid)
            elif "listening" in lowered and not "all slots are idle" in lowered:
                # Log a subtle hint that we are waiting for the idle signal
                pass 

        worker.line.connect(handle_line)
        worker.finished.connect(lambda ok, out: self._on_launch_done(ok, out, iid))
        worker.start()
        self._setup_workers[iid] = worker

    def _establish_studio_tunnel(self, iid: int):
        """Immediately establish the SSH tunnel and open the WebUI for a running server."""
        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        st = self.store.get_state(iid)
        
        # Guard: don't re-trigger if already ready or different instance
        if not inst or iid != self.store.selected_instance_id:
            return
            
        # If we already have a tunnel and WebUI is open, don't flicker
        if not self.studio.launch_status.text().strip().endswith("Ready"):
            remote_port = st.server_params.port or 11434
            local_port = self.studio_port_allocator.get(iid)
            self._ssh.start_tunnel(iid, inst.ssh_host, inst.ssh_port, remote_port, local_port)
            self.studio.open_webui(local_port)
            self._controller.log_line.emit(f"#{iid}: WebUI ready at http://127.0.0.1:{local_port}")

    def _on_launch_done(self, ok: bool, output: str, iid: int):
        self.store.set_instance_busy(iid, "launch", False)
        if ok:
            self._establish_studio_tunnel(iid)
        else:
            from app.lab.services.diagnostics import classify_server_log
            diag = classify_server_log(output)
            if diag and iid == self.store.selected_instance_id:
                self.studio.banner.set_diagnostic(diag)
                self.studio.mark_launch_failed()
            self._controller.log_line.emit(f"#{iid} Launch failed.")

    def _stop_server(self):
        iid = self.store.selected_instance_id
        if iid:
            self.studio.clear_webui()
            self._run_single_setup("stop_server", iid)
        else:
            self._run_single_setup("stop_server", iid)
            self.studio.clear_webui()

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
        if self._controller:
            self._controller.log_line.emit(output if ok else f"(SSH failed)\n{output}")

    def _apply_diagnostic_fix(self, action: str):
        iid = self.store.selected_instance_id
        if not iid:
            return
        if action == "lower_ngl":
            params = self.store.get_state(iid).server_params
            params.gpu_layers = max(0, params.gpu_layers // 2)
            self.store.set_server_params(iid, params)
            self._launch_server(params)
        elif action == "free_port":
            self._stop_server()
        elif action == "reinstall_llamacpp":
            self._run_setup("install_llamacpp", iid=iid)
        elif action == "pick_model":
            self._go("models")

    def _persist_studio_port_map(self, m):
        if self._config:
            self._config.studio_port_map = m
            if self._config_store:
                self._config_store.save(self._config)
