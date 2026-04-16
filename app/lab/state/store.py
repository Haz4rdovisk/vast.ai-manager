"""Centralised reactive store for Lab V2 — remote-instance-first."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal
from app.lab.state.models import (
    RemoteSystem, RemoteModel, RemoteGGUF, SetupStatus, ServerParams,
)


class LabStore(QObject):
    # Signals
    instance_changed = Signal(int)               # instance id
    remote_system_changed = Signal(object)       # RemoteSystem
    remote_models_changed = Signal(list)         # list[RemoteModel]
    remote_gguf_changed = Signal(list)           # list[RemoteGGUF]
    setup_status_changed = Signal(object)        # SetupStatus
    server_params_changed = Signal(object)       # ServerParams
    busy_changed = Signal(str, bool)             # key, busy

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_instance_id: int | None = None
        self.remote_system = RemoteSystem()
        self.remote_models: list[RemoteModel] = []
        self.remote_gguf: list[RemoteGGUF] = []
        self.setup_status = SetupStatus()
        self.server_params = ServerParams()
        self._busy: dict[str, bool] = {}

    def set_instance(self, iid: int | None):
        self.selected_instance_id = iid
        # Reset state when switching instances
        self.remote_system = RemoteSystem()
        self.remote_models = []
        self.remote_gguf = []
        self.setup_status = SetupStatus()
        self.server_params = ServerParams()
        self.instance_changed.emit(iid or 0)

    def set_remote_system(self, sys: RemoteSystem):
        self.remote_system = sys
        self.remote_system_changed.emit(sys)

    def set_remote_models(self, models: list[RemoteModel]):
        self.remote_models = models
        self.remote_models_changed.emit(models)

    def set_remote_gguf(self, files: list[RemoteGGUF]):
        self.remote_gguf = files
        self.remote_gguf_changed.emit(files)

    def set_setup_status(self, status: SetupStatus):
        self.setup_status = status
        self.setup_status_changed.emit(status)

    def set_server_params(self, params: ServerParams):
        self.server_params = params
        self.server_params_changed.emit(params)

    def is_busy(self, key: str) -> bool:
        return self._busy.get(key, False)

    def set_busy(self, key: str, busy: bool):
        self._busy[key] = busy
        self.busy_changed.emit(key, busy)
