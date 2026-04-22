import time
from unittest.mock import MagicMock

from PySide6.QtTest import QSignalSpy

from app.lab.state.models import JobDescriptor
from app.lab.workers.remote_job_probe import RemoteJobProbe


def _desc():
    return JobDescriptor(
        key="1-x-q4",
        iid=1,
        repo_id="x/y",
        filename="y-Q4_K_M.gguf",
        quant="Q4_K_M",
        size_bytes=1,
        needs_llamacpp=False,
        remote_state_path="/workspace/.vastai-app/jobs/1-x-q4.json",
        remote_log_path="/tmp/install-1-x-q4.log",
        started_at=time.time(),
    )


def test_probe_emits_running_with_state(qt_app):
    ssh = MagicMock()
    ssh.run_script.return_value = (True, 'RUNNING\n{"pid":123,"stage":"download","percent":42}\n')
    probe = RemoteJobProbe(ssh, "host", 22, _desc())
    spy = QSignalSpy(probe.result)
    probe.run()
    assert spy.count() == 1
    assert spy.at(0)[0] == "RUNNING"
    assert spy.at(0)[1]["percent"] == 42


def test_probe_emits_offline_on_ssh_failure(qt_app):
    ssh = MagicMock()
    ssh.run_script.return_value = (False, "ssh blew up")
    probe = RemoteJobProbe(ssh, "host", 22, _desc())
    spy = QSignalSpy(probe.result)
    probe.run()
    assert spy.count() == 1
    assert spy.at(0)[0] == "OFFLINE"
