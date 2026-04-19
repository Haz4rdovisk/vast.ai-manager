"""Centralised reactive store for Lab V2 — remote-instance-first."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal
from app.lab.state.models import (
    RemoteSystem, RemoteModel, RemoteGGUF, SetupStatus, ServerParams,
    LabInstanceState,
)


class LabStore(QObject):
    # Signals
    instance_changed = Signal(int)               # instance id (the one focused by the lab)
    instance_state_updated = Signal(int, object) # iid, LabInstanceState
    busy_changed = Signal(str, bool)             # global busy (unified probe/setup)

    # --- Compatibility signals (fire for current_selected_instance) ---
    remote_system_changed = Signal(object)       # RemoteSystem
    remote_models_changed = Signal(list)         # list[RemoteModel]
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
        """Focus the UI (other than Dashboard) on a specific instance."""
        self.selected_instance_id = iid
        self.instance_changed.emit(iid or 0)
        
        # Fire compatibility signals for the new selected instance
        st = self.get_state(iid) if iid else LabInstanceState(iid=0)
        self.remote_system_changed.emit(st.system)
        self.remote_models_changed.emit(st.models)
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
        # We don't have a direct compatibility signal for busy, 
        # but views might need it. For now Dashboard handles it.

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
