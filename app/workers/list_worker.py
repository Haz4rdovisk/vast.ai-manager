from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.services.vast_service import VastService, VastAuthError, VastNetworkError


def _instance_signature(insts: list) -> tuple:
    return tuple(
        (
            getattr(inst, "id", None),
            getattr(getattr(inst, "state", None), "value", getattr(inst, "state", None)),
            getattr(inst, "status_message", None),
            bool(getattr(inst, "raw", {}).get("_is_scheduling")),
            getattr(inst, "raw", {}).get("_scheduling_source"),
        )
        for inst in insts
    )


class ListWorker(QObject):
    refreshed = Signal(list, object)  # list[Instance], UserInfo | None
    failed = Signal(str, str)         # kind, message

    def __init__(self, service: VastService):
        super().__init__()
        self.service = service

    @Slot()
    def refresh(self):
        try:
            insts = self.service.list_instances()
        except VastAuthError as e:
            self.failed.emit("auth", str(e))
            return
        except VastNetworkError as e:
            self.failed.emit("network", str(e))
            return
        except Exception as e:
            self.failed.emit("unknown", str(e))
            return

        if not isinstance(insts, list):
            insts = []
        self.refreshed.emit(insts, None)

        try:
            user = self.service.get_user_info()
        except VastAuthError as e:
            self.failed.emit("auth", str(e))
            return
        except VastNetworkError as e:
            self.failed.emit("network", str(e))
            return
        except Exception as e:
            self.failed.emit("unknown", str(e))
            return

        self.refreshed.emit(insts, user)

        try:
            refined = self.service.list_instances(include_audit_targets=True)
        except Exception:
            return
        if not isinstance(refined, list):
            return
        if _instance_signature(refined) != _instance_signature(insts):
            self.refreshed.emit(refined, user)
