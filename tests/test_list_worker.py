from app.models import Instance, InstanceState, UserInfo
from app.workers.list_worker import ListWorker


def _inst(iid, state=InstanceState.STOPPED, scheduling=False):
    return Instance(
        id=iid,
        state=state,
        gpu_name="RTX 3090",
        raw={"_is_scheduling": scheduling},
    )


def test_list_worker_emits_fast_instances_before_audit_refinement(qt_app):
    calls = []

    class FakeService:
        def get_user_info(self):
            calls.append("user")
            return UserInfo(balance=1.0)

        def list_instances(self, *, include_audit_targets=False):
            calls.append("audit" if include_audit_targets else "instances")
            if include_audit_targets:
                return [_inst(1, InstanceState.STARTING, scheduling=True)]
            return [_inst(1, InstanceState.STOPPED, scheduling=False)]

    worker = ListWorker(FakeService())
    seen = []
    worker.refreshed.connect(lambda insts, user: seen.append((insts, user)))

    worker.refresh()

    assert len(seen) == 3
    assert calls == ["instances", "user", "audit"]
    assert seen[0][0][0].state == InstanceState.STOPPED
    assert seen[0][1] is None
    assert seen[1][1].balance == 1.0
    assert seen[2][0][0].state == InstanceState.STARTING


def test_list_worker_does_not_emit_refinement_when_audit_does_not_change(qt_app):
    class FakeService:
        def get_user_info(self):
            return UserInfo(balance=1.0)

        def list_instances(self, *, include_audit_targets=False):
            return [_inst(1, InstanceState.STOPPED, scheduling=False)]

    worker = ListWorker(FakeService())
    seen = []
    worker.refreshed.connect(lambda insts, user: seen.append((insts, user)))

    worker.refresh()

    assert len(seen) == 2
    assert seen[0][1] is None
    assert seen[1][1].balance == 1.0
