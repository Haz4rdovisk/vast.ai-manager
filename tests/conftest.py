import pytest
import weakref
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


# Track AppController instances created during a test so we can shut them
# down deterministically — otherwise QThreads linger and GC deadlocks at
# process exit / between tests.
_live_controllers: "weakref.WeakSet" = weakref.WeakSet()


@pytest.fixture(autouse=True)
def _track_controllers():
    try:
        from app.controller import AppController
    except ImportError:
        yield
        return

    orig_init = AppController.__init__

    def tracked_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        _live_controllers.add(self)

    AppController.__init__ = tracked_init
    try:
        yield
    finally:
        AppController.__init__ = orig_init
        for c in list(_live_controllers):
            try:
                c.shutdown()
            except Exception:
                pass
