"""LabShell \u2014 top-level widget for the Local AI Lab workspace.
Hosts the nav rail + a QStackedWidget of views. Owns the LabStore."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QStackedWidget, QLabel, QVBoxLayout, QMessageBox,
)
from PySide6.QtCore import Qt
from app.lab import theme as t
from app.lab.components.nav_rail import NavRail, NAV_ITEMS
from app.lab.state.store import LabStore
from app.lab.views.machine_view import MachineView
from app.lab.views.runtime_view import RuntimeView
from app.lab.views.library_view import LibraryView
from app.lab.views.discover_view import DiscoverView
from app.lab.views.benchmark_view import BenchmarkView
from app.lab.views.diagnostics_view import DiagnosticsView
from app.lab.views.overview_view import OverviewView
from app.lab.views.model_detail_view import ModelDetailView
from app.lab.workers.hw_probe import HardwareProbeWorker
from app.lab.workers.download_worker import DownloadWorker


class _Placeholder(QWidget):
    """Temporary view stub \u2014 replaced by real views in later tasks."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        lbl = QLabel(title)
        lbl.setProperty("role", "display")
        hint = QLabel("Coming online\u2026")
        hint.setProperty("role", "muted")
        lay.addWidget(lbl)
        lay.addWidget(hint)
        lay.addStretch()


class LabShell(QWidget):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("lab-shell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.store = LabStore(self)
        self._config = config
        self._downloads: dict[str, DownloadWorker] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavRail(self)
        self.nav.selected.connect(self._switch)
        root.addWidget(self.nav)

        self.stack = QStackedWidget(self)
        self._views: dict[str, QWidget] = {}
        for key, label, _ in NAV_ITEMS:
            v = _Placeholder(label, self)
            self.stack.addWidget(v)
            self._views[key] = v
        root.addWidget(self.stack, 1)

        self._switch("overview")

        # --- Machine view + hardware probe ---
        self.replace_view("machine", MachineView(self.store, self))
        self._hw_worker = HardwareProbeWorker(self)
        self._hw_worker.detected.connect(self.store.set_hardware)
        self._hw_worker.start()

        # --- Runtime view + probe ---
        self.runtime_view = RuntimeView(self.store, self)
        self.replace_view("runtime", self.runtime_view)
        self.runtime_view.kick_probe()

        # --- Library view ---
        models_dir = getattr(self._config, "models_dir", "") if self._config else ""
        self.library_view = LibraryView(self.store, models_dir, self)
        self.replace_view("library", self.library_view)
        self.library_view.rescan()

        # --- Discover view ---
        self.discover_view = DiscoverView(self.store, self)
        self.replace_view("discover", self.discover_view)
        self.discover_view.install_requested.connect(self._on_install_requested)

        # --- Benchmark view ---
        self.benchmark_view = BenchmarkView(self.store, self)
        self.replace_view("benchmark", self.benchmark_view)

        # Library \u2192 Benchmark cross-link
        def _bench_from_library(path: str):
            self.benchmark_view.select_model(path)
            self.nav.set_active("benchmark")
            self._switch("benchmark")
        self.library_view.benchmark_requested.connect(_bench_from_library)

        # Library navigation
        self.library_view.navigate_requested.connect(
            lambda k: (self.nav.set_active(k), self._switch(k)))

        # --- Diagnostics view ---
        self.diag_view = DiagnosticsView(self.store, self)
        self.replace_view("diagnostics", self.diag_view)
        self.diag_view.navigate_requested.connect(
            lambda k: (self.nav.set_active(k), self._switch(k)))
        self.diag_view.rescan_library_requested.connect(
            lambda: self.library_view.rescan())

        # --- Model detail view (not in nav rail) ---
        self.detail_view = ModelDetailView(self.store, self)
        self.stack.addWidget(self.detail_view)
        self.detail_view.back_requested.connect(lambda: self._switch("library"))
        self.detail_view.removed.connect(lambda _p: self.library_view.rescan())
        self.detail_view.benchmark_requested.connect(
            lambda p: (self.benchmark_view.select_model(p),
                       self.nav.set_active("benchmark"),
                       self._switch("benchmark")))
        self.library_view.model_detail_requested.connect(self._open_detail)

        # --- Overview view ---
        self.overview_view = OverviewView(self.store, self)
        self.replace_view("overview", self.overview_view)
        self.overview_view.navigate_requested.connect(
            lambda k: (self.nav.set_active(k), self._switch(k)))
        self.overview_view.install_requested.connect(self._on_install_requested)

    # --- Navigation ---

    def _switch(self, key: str):
        v = self._views.get(key)
        if v is not None:
            self.stack.setCurrentWidget(v)

    def replace_view(self, key: str, widget: QWidget):
        """Called by later tasks to swap a placeholder for the real view."""
        old = self._views.get(key)
        idx = None
        if old is not None:
            idx = self.stack.indexOf(old)
            self.stack.removeWidget(old)
            old.deleteLater()
        self._views[key] = widget
        if idx is not None and idx >= 0:
            self.stack.insertWidget(idx, widget)
        else:
            self.stack.addWidget(widget)

    def _open_detail(self, path: str):
        self.detail_view.show_model_by_path(path)
        self.stack.setCurrentWidget(self.detail_view)

    # --- Download manager ---

    def _on_install_requested(self, entry_id: str):
        entry = next((e for e in self.store.catalog if e.id == entry_id), None)
        if entry is None:
            return
        models_dir = getattr(self._config, "models_dir", "") if self._config else ""
        if not models_dir:
            QMessageBox.warning(
                self, "Models folder not configured",
                "Pick a models folder in the Library tab before installing.")
            self._switch("library")
            self.nav.set_active("library")
            return
        if self.store.is_busy(f"download:{entry_id}"):
            return
        self.store.set_busy(f"download:{entry_id}", True)
        worker = DownloadWorker(entry_id, entry.repo_id, entry.filename,
                                models_dir, parent=self)
        worker.progress.connect(
            lambda d, total, spd, e=entry_id:
                self.discover_view.on_progress(e, d, total, spd))
        worker.finished_ok.connect(
            lambda _p, e=entry_id: self._on_download_done(e, ok=True))
        worker.failed.connect(
            lambda msg, e=entry_id: self._on_download_done(e, ok=False, msg=msg))
        worker.start()
        self._downloads[entry_id] = worker

    def _on_download_done(self, entry_id: str, ok: bool, msg: str = ""):
        self.store.set_busy(f"download:{entry_id}", False)
        self.discover_view.on_install_result(entry_id, ok)
        if ok:
            self.library_view.rescan()
        elif not ok:
            QMessageBox.critical(self, "Download failed", msg or "Unknown error")
