"""Centralised reactive store for Lab V2 — remote-instance-first."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal
from app.lab.state.models import (
    DownloadJob,
    InstallJob,
    LabInstanceState,
    RemoteGGUF,
    RemoteModel,
    RemoteSystem,
    ScoredCatalogModel,
    ServerParams,
    SetupStatus,
)


class LabStore(QObject):
    # Signals
    instance_changed = Signal(int)               # instance id (the one focused by the lab)
    instance_state_updated = Signal(int, object) # iid, LabInstanceState
    busy_changed = Signal(str, bool)             # global busy (unified probe/setup)
    install_job_changed = Signal(int, object)    # iid, InstallJob
    download_job_changed = Signal(int, object)   # iid, DownloadJob

    # --- Compatibility signals (fire for current_selected_instance) ---
    remote_system_changed = Signal(object)       # RemoteSystem
    remote_models_changed = Signal(list)         # list[RemoteModel]
    scored_models_changed = Signal(list)         # list[ScoredCatalogModel]
    remote_gguf_changed = Signal(list)           # list[RemoteGGUF]
    setup_status_changed = Signal(object)        # SetupStatus
    server_params_changed = Signal(object)       # ServerParams

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_instance_id: int | None = None
        self.instance_states: dict[int, LabInstanceState] = {}
        self._global_busy: dict[str, bool] = {}

    def get_state(self, iid: int) -> LabInstanceState:
        if iid not in self.instance_states:
            self.instance_states[iid] = LabInstanceState(iid=iid)
        return self.instance_states[iid]

    def all_instance_ids(self) -> list[int]:
        """Return IDs of all managed instances."""
        return list(self.instance_states.keys())

    def set_instance(self, iid: int | None):
        """Focus Lab views on a specific instance."""
        self.selected_instance_id = iid
        self.instance_changed.emit(iid or 0)
        
        # Fire compatibility signals for the new selected instance
        st = self.get_state(iid) if iid else LabInstanceState(iid=0)
        self.remote_system_changed.emit(st.system)
        self.remote_models_changed.emit(st.models)
        self.scored_models_changed.emit(st.scored_models)
        self.remote_gguf_changed.emit(st.gguf)
        self.setup_status_changed.emit(st.setup)
        self.server_params_changed.emit(st.server_params)

    # --- Reactive helpers for the current selected instance ---
    @property
    def current_state(self) -> LabInstanceState | None:
        if self.selected_instance_id is None:
            return None
        return self.get_state(self.selected_instance_id)

    # --- Setters (all update specific iid state) ---

    def set_remote_system(self, iid: int, sys: RemoteSystem):
        st = self.get_state(iid)
        st.system = sys
        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.remote_system_changed.emit(sys)

    def set_remote_models(self, iid: int, models: list[RemoteModel]):
        st = self.get_state(iid)
        st.models = models
        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.remote_models_changed.emit(models)

    def set_scored_models(self, iid: int, scored):
        """Store scored catalog models as flat DTOs.

        Accepts list[ScoredCatalogModel] or list[fit_scorer.ScoredModel] to keep
        views independent from scorer service imports.
        """
        flat: list[ScoredCatalogModel] = []
        for item in scored:
            if isinstance(item, ScoredCatalogModel):
                flat.append(item)
                continue

            entry = item.entry
            flat.append(
                ScoredCatalogModel(
                    name=entry.name,
                    provider=entry.provider,
                    params_b=entry.params_b,
                    best_quant=entry.best_quant,
                    use_case=entry.use_case,
                    fit_level=item.fit_level,
                    fit_label=item.fit_label,
                    run_mode=item.run_mode,
                    score=item.score,
                    utilization_pct=item.utilization_pct,
                    memory_required_gb=entry.memory_required_gb,
                    memory_available_gb=item.memory_available_gb,
                    estimated_tps=item.estimated_tps,
                    gguf_sources=list(entry.gguf_sources),
                    notes=list(item.notes),
                )
            )

        st = self.get_state(iid)
        st.scored_models = flat
        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.scored_models_changed.emit(flat)

    def update_install_job(self, iid: int, job: InstallJob):
        st = self.get_state(iid)
        st.install_job = job
        self.instance_state_updated.emit(iid, st)
        self.install_job_changed.emit(iid, job)

    def update_download_job(self, iid: int, job: DownloadJob):
        st = self.get_state(iid)
        st.download_job = job
        self.instance_state_updated.emit(iid, st)
        self.download_job_changed.emit(iid, job)

    def set_remote_gguf(self, iid: int, files: list[RemoteGGUF]):
        st = self.get_state(iid)
        st.gguf = files
        st.setup.model_count = len(files)
        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.remote_gguf_changed.emit(files)

    def set_setup_status(self, iid: int, status: SetupStatus):
        st = self.get_state(iid)
        st.setup = status
        st.setup.probed = True
        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.setup_status_changed.emit(status)

    def set_server_params(self, iid: int, params: ServerParams):
        st = self.get_state(iid)
        st.server_params = params
        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.server_params_changed.emit(params)

    def save_model_config(self, iid: int, path: str, params: ServerParams):
        st = self.get_state(iid)
        st.model_configs[path] = params
        self.instance_state_updated.emit(iid, st)

    def set_instance_busy(self, iid: int, key: str, busy: bool):
        st = self.get_state(iid)
        if busy:
            st.busy_keys.add(key)
        else:
            st.busy_keys.discard(key)
        self.instance_state_updated.emit(iid, st)
        # We don't have a direct compatibility signal for busy, but views can
        # listen to instance_state_updated for per-instance busy keys.

    # Global busy (e.g. for general UI overlays)
    def set_busy(self, key: str, busy: bool):
        self._global_busy[key] = busy
        self.busy_changed.emit(key, busy)

    def update_telemetry(self, iid: int, d: dict):
        """Bridge real-time metrics from AppController into the Lab state."""
        st = self.get_state(iid)
        sys = st.system

        if "gpu_util" in d:
            sys.gpu_usage_pct = d["gpu_util"]
        if "gpu_temp" in d:
            sys.gpu_temp = d["gpu_temp"]
        if "vram_used_mb" in d:
            total = d.get("vram_total_mb") or (sys.gpu_vram_gb * 1024 if sys.gpu_vram_gb else 1)
            sys.gpu_vram_usage_pct = (d["vram_used_mb"] / total) * 100
        if "ram_used_mb" in d:
            total = d.get("ram_total_mb") or (sys.ram_total_gb * 1024 if sys.ram_total_gb else 1)
            sys.ram_usage_pct = (d["ram_used_mb"] / total) * 100
            sys.ram_available_gb = (total - d["ram_used_mb"]) / 1024
        if "load1" in d:
            # Consistent with the CPU calculation fix
            cores = sys.cpu_cores or 1
            sys.cpu_usage_pct = (d["load1"] / cores) * 100
        if "disk_used_gb" in d:
            sys.disk_used_gb = d["disk_used_gb"]
            if "disk_total_gb" in d and d["disk_total_gb"]:
                sys.disk_total_gb = d["disk_total_gb"]
                sys.disk_usage_pct = (d["disk_used_gb"] / d["disk_total_gb"]) * 100

        self.instance_state_updated.emit(iid, st)
        if iid == self.selected_instance_id:
            self.remote_system_changed.emit(sys)

    def is_busy(self, key: str) -> bool:
        return self._global_busy.get(key, False)
