from PySide6.QtCore import QEventLoop, QTimer

from app.lab.workers.streaming_worker import StreamingRemoteWorker


class _FakeSSH:
    def __init__(self, lines, ok=True):
        self._lines = lines
        self._ok = ok

    def stream_script(self, host, port, script, on_line):
        for line in self._lines:
            on_line(line)
        return self._ok, "\n".join(self._lines)


def test_streaming_worker_emits_line_then_finished(qt_app):
    ssh = _FakeSSH(["one", "two", "three"])
    worker = StreamingRemoteWorker(ssh, "h", 22, "echo stub")
    seen: list[str] = []
    done: dict = {}
    worker.line.connect(seen.append)
    worker.finished.connect(lambda ok, out: done.update(ok=ok, out=out))

    loop = QEventLoop()
    worker.finished.connect(lambda *_: loop.quit())
    QTimer.singleShot(2000, loop.quit)
    worker.start()
    loop.exec()

    assert seen == ["one", "two", "three"]
    assert done["ok"] is True
    assert "three" in done["out"]


def test_streaming_worker_propagates_failure(qt_app):
    ssh = _FakeSSH(["boom"], ok=False)
    worker = StreamingRemoteWorker(ssh, "h", 22, "exit 1")
    done: dict = {}
    worker.finished.connect(lambda ok, out: done.update(ok=ok, out=out))

    loop = QEventLoop()
    worker.finished.connect(lambda *_: loop.quit())
    QTimer.singleShot(2000, loop.quit)
    worker.start()
    loop.exec()

    assert done["ok"] is False
