"""Live install panel for llama.cpp setup and GGUF download progress."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import theme as t
from app.ui.components.primitives import GlassCard, SectionHeader
from app.ui.components.progress_panel import ProgressPanel, StepState


LLAMACPP_STEPS = ["apt", "clone", "cmake", "build", "done"]
DOWNLOAD_STEPS = ["connect", "download", "verify"]

_STAGE_ORDER = {"apt": 0, "clone": 1, "cmake": 2, "build": 3, "done": 4}


class InstallPanel(QWidget):
    close_requested = Signal()
    retry_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        root.setSpacing(t.SPACE_4)

        root.addWidget(
            SectionHeader("INSTALL", "Set up llama.cpp and download the model")
        )

        self.llamacpp_section = GlassCard()
        self.llamacpp_section.body().addWidget(QLabel("1. llama.cpp on the instance"))
        self.llamacpp_progress = ProgressPanel(LLAMACPP_STEPS)
        self.llamacpp_section.body().addWidget(self.llamacpp_progress)
        root.addWidget(self.llamacpp_section)

        self.download_section = GlassCard()
        self.download_section.body().addWidget(QLabel("2. Download GGUF to /workspace"))
        self.download_progress = ProgressPanel(DOWNLOAD_STEPS)
        self.download_section.body().addWidget(self.download_progress)
        root.addWidget(self.download_section)

        buttons = QHBoxLayout()
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self.retry_requested.emit)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close_requested.emit)
        buttons.addStretch()
        buttons.addWidget(self.retry_btn)
        buttons.addWidget(self.close_btn)
        root.addLayout(buttons)

        store.install_job_changed.connect(self._on_install_job)
        store.download_job_changed.connect(self._on_download_job)

    def _on_install_job(self, iid: int, job):
        if iid != self.store.selected_instance_id or job is None:
            return

        if job.stage == "failed":
            self._mark_failed_install(job)
            return

        current_order = _STAGE_ORDER.get(job.stage, -1)
        for step in LLAMACPP_STEPS:
            order = _STAGE_ORDER[step]
            if order < current_order:
                state = StepState.DONE
            elif order == current_order:
                state = StepState.DONE if job.stage == "done" else StepState.RUNNING
            else:
                state = StepState.PENDING
            self.llamacpp_progress.set_step(step, state)

        self.llamacpp_progress.set_percent(job.percent)
        for line in job.log_tail[-10:]:
            self.llamacpp_progress.append_log(line)
        self.retry_btn.setVisible(False)

    def _on_download_job(self, iid: int, job):
        if iid != self.store.selected_instance_id or job is None:
            return

        self.download_progress.set_percent(job.percent)
        if 0 < job.percent < 100:
            self.download_progress.set_step("connect", StepState.DONE)
            self.download_progress.set_step("download", StepState.RUNNING)
        if job.done:
            self.download_progress.set_step("connect", StepState.DONE)
            self.download_progress.set_step("download", StepState.DONE)
            self.download_progress.set_step("verify", StepState.DONE)
        if job.error:
            self.download_progress.set_step("download", StepState.FAILED)
            self.retry_btn.setVisible(True)
        if job.speed:
            self.download_progress.append_log(f"{job.percent}% - {job.speed}")

    def _mark_failed_install(self, job) -> None:
        for step in LLAMACPP_STEPS:
            self.llamacpp_progress.set_step(step, StepState.PENDING)
        self.llamacpp_progress.set_step("build", StepState.FAILED)
        self.llamacpp_progress.set_percent(job.percent)
        for line in job.log_tail[-10:]:
            self.llamacpp_progress.append_log(line)
        if job.error:
            self.llamacpp_progress.append_log(job.error)
        self.retry_btn.setVisible(True)
