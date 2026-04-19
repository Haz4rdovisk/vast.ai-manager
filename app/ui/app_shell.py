"""LabShell V2 — remote instance-first AI Lab workspace.
Manages views, workers, and wiring against a selected Vast.ai instance."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QStackedWidget, QLabel, QVBoxLayout,
)
from PySide6.QtCore import Qt, Slot, QTimer
from app import theme as t
from app.ui.components.nav_rail import NavRail, NAV_ITEMS
from app.lab.state.store import LabStore
from app.lab.state.models import DownloadJob, InstallJob, RemoteGGUF, ServerParams
from app.models import TunnelStatus
from app.lab.views.discover_view import DiscoverView
from app.lab.views.install_panel import InstallPanel
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
from app.lab.services.progress_parsers import parse_cmake_build_stage, parse_wget_progress
from app.lab.services.remote_setup import (
    script_download_model,
    script_fetch_log,
    script_install_llamacpp,
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
        self._config = config
        self._config_store = config_store
        self._ssh = ssh_service
        self.analytics_store = analytics_store
        self._controller = None
        self._current_view = ""
        self._analytics_api_sync_pending = False
        
        self._host: str = ""
        self._port: int = 0
        
        self._probe_workers: dict[int, RemoteProbeWorker] = {}
        self._probe_callbacks: dict[int, callable] = {}
        self._setup_workers: dict[int, RemoteSetupWorker] = {}

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
        self.discover = DiscoverView(self.store, self)
        self._add_view("discover", self.discover)
        self.discover.refresh_requested.connect(self._refresh_llmfit_models)
        self.discover.download_requested.connect(self._download_model_by_name)
        self.discover.back_requested.connect(lambda: self._go("studio"))

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
        self.instances = InstancesView(controller, self)
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
        
        worker.setup_ready.connect(lambda s: self.store.set_setup_status(iid, s))
        worker.system_ready.connect(lambda s: self.store.set_remote_system(iid, s))
        worker.models_ready.connect(lambda m: self.store.set_remote_models(iid, m))
        worker.gguf_ready.connect(lambda g: self.store.set_remote_gguf(iid, g))
        
        worker.finished.connect(lambda: self._on_probe_done(iid))
        worker.start()

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

    def _download_model_by_name(self, model_name: str, quant: str):
        iid = self.store.selected_instance_id
        if not iid or not self._controller or not self._ssh:
            return

        self._install_retry_model = model_name
        self._install_retry_quant = quant

        inst = next((i for i in self._controller.last_instances if i.id == iid), None)
        if not inst or not inst.ssh_host:
            return

        if "install" not in self._views:
            panel = InstallPanel(self.store, self)
            self._add_view("install", panel)
            panel.close_requested.connect(lambda: self._go("discover"))
            panel.retry_requested.connect(
                lambda: self._download_model_by_name(
                    self._install_retry_model,
                    self._install_retry_quant,
                )
            )
        self._go("install")

        state = self.store.get_state(iid)
        scored = next((s for s in state.scored_models if s.name == model_name), None)
        repo = scored.gguf_sources[0] if scored and scored.gguf_sources else model_name
        filename = (
            f"{model_name.lower().replace(' ', '-')}-"
            f"{(quant or 'Q4_K_M').lower()}.gguf"
        )
        needs_install = not state.setup.llamacpp_installed

        script_parts: list[str] = []
        if needs_install:
            script_parts.append(script_install_llamacpp())
        script_parts.append(script_download_model(repo, filename))
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
                    self.store.update_install_job(
                        iid,
                        InstallJob(
                            kind="llamacpp",
                            stage="done",
                            percent=100,
                            log_tail=log_tail[-10:],
                        ),
                    )
                    progress_state["phase"] = "download"
                    return

                if event.stage != "unknown":
                    percent = (
                        event.percent
                        if event.percent is not None
                        else progress_state["percent"]
                    )
                    progress_state["percent"] = percent
                    self.store.update_install_job(
                        iid,
                        InstallJob(
                            kind="llamacpp",
                            stage=event.stage,
                            percent=percent,
                            log_tail=log_tail[-10:],
                        ),
                    )
                return

            event = parse_wget_progress(line)
            if event is not None:
                self.store.update_download_job(
                    iid,
                    DownloadJob(
                        repo_id=repo,
                        filename=filename,
                        percent=event.percent,
                        bytes_downloaded=0,
                        bytes_total=0,
                        speed=event.speed,
                    ),
                )
            elif "DOWNLOAD_DONE" in line:
                self.store.update_download_job(
                    iid,
                    DownloadJob(
                        repo_id=repo,
                        filename=filename,
                        percent=100,
                        bytes_downloaded=0,
                        bytes_total=0,
                        speed="",
                        done=True,
                    ),
                )

        worker.line.connect(on_line)
        worker.finished.connect(lambda ok, out: self._on_install_done(ok, out, iid))
        self.store.update_install_job(
            iid,
            InstallJob(
                kind="llamacpp",
                stage="apt" if needs_install else "done",
                percent=0 if needs_install else 100,
            ),
        )
        worker.start()

    def _on_install_done(self, ok: bool, output: str, iid: int):
        if not ok:
            self.store.update_install_job(
                iid,
                InstallJob(
                    kind="llamacpp",
                    stage="failed",
                    percent=0,
                    log_tail=output.splitlines()[-20:],
                    error=output[-200:],
                ),
            )
        self._probe_instance(iid)

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
        worker.line.connect(lambda line: self.studio.append_launch_log(line))
        worker.finished.connect(lambda ok, out: self._on_launch_done(ok, out, iid))
        worker.start()
        self._setup_workers[iid] = worker

    def _on_launch_done(self, ok: bool, output: str, iid: int):
        from app.lab.services.diagnostics import classify_server_log

        self.store.set_instance_busy(iid, "launch", False)
        if ok and "LAUNCH_OK" in output:
            tunnel = self._ssh.get(iid) if self._ssh else None
            port = (
                tunnel.local_port
                if tunnel
                else self.store.get_state(iid).server_params.port
            )
            if iid == self.store.selected_instance_id:
                self._go("studio")
                self.studio.open_webui(port)
            self._probe_instance(iid)
        else:
            diag = classify_server_log(output)
            if diag and iid == self.store.selected_instance_id:
                self.studio.banner.set_diagnostic(diag)
                self.studio.mark_launch_failed()
            self._controller.log_line.emit(f"#{iid} Launch failed.")

    def _stop_server(self):
        iid = self.store.selected_instance_id
        if iid:
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
