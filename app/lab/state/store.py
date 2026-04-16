"""Single source of truth for the Lab. Qt signals notify views of changes.
Views subscribe; services/workers push."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal
from app.lab.state.models import (
    HardwareSpec, RuntimeStatus, ModelFile, CatalogEntry,
    Recommendation, BenchmarkResult, DiagnosticsItem,
)


class LabStore(QObject):
    hardware_changed = Signal(object)          # HardwareSpec
    runtime_changed = Signal(object)           # RuntimeStatus
    library_changed = Signal(list)             # list[ModelFile]
    catalog_changed = Signal(list)             # list[CatalogEntry]
    recommendations_changed = Signal(list)     # list[Recommendation]
    benchmarks_changed = Signal(list)          # list[BenchmarkResult]
    diagnostics_changed = Signal(list)         # list[DiagnosticsItem]
    busy_changed = Signal(str, bool)           # (key, is_busy)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hardware = HardwareSpec()
        self.runtime = RuntimeStatus()
        self.library: list[ModelFile] = []
        self.catalog: list[CatalogEntry] = []
        self.recommendations: list[Recommendation] = []
        self.benchmarks: list[BenchmarkResult] = []
        self.diagnostics: list[DiagnosticsItem] = []
        self._busy: dict[str, bool] = {}

    def set_hardware(self, spec: HardwareSpec):
        self.hardware = spec
        self.hardware_changed.emit(spec)

    def set_runtime(self, rs: RuntimeStatus):
        self.runtime = rs
        self.runtime_changed.emit(rs)

    def set_library(self, items: list[ModelFile]):
        self.library = items
        self.library_changed.emit(items)

    def set_catalog(self, items: list[CatalogEntry]):
        self.catalog = items
        self.catalog_changed.emit(items)

    def set_recommendations(self, items: list[Recommendation]):
        self.recommendations = items
        self.recommendations_changed.emit(items)

    def add_benchmark(self, item: BenchmarkResult):
        self.benchmarks.append(item)
        self.benchmarks_changed.emit(list(self.benchmarks))

    def set_diagnostics(self, items: list[DiagnosticsItem]):
        self.diagnostics = items
        self.diagnostics_changed.emit(items)

    def set_busy(self, key: str, busy: bool):
        self._busy[key] = busy
        self.busy_changed.emit(key, busy)

    def is_busy(self, key: str) -> bool:
        return self._busy.get(key, False)
