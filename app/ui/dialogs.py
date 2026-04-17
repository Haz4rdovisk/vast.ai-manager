"""Interactive dialogs for the AI Lab."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCheckBox, QFrame
)
from PySide6.QtCore import Qt
from app import theme as t

from app.lab.workers.remote_update_worker import RemoteUpdateWorker

class UpdateSelectionDialog(QDialog):
    """Allows user to select which components to update/refresh."""
    def __init__(self, iid: int, ssh_service, host: str, port: int, parent=None):
        super().__init__(parent)
        self.iid = iid
        self.ssh = ssh_service
        self.host = host
        self.port = port
        self.worker = None
        self.mode = "check" # check | apply | none
        
        self.setWindowTitle(f"Update Instance #{iid}")
        self.setFixedWidth(400)
        
        lay = QVBoxLayout(self)
        lay.setSpacing(t.SPACE_4)
        
        header = QLabel("Components Update")
        header.setProperty("role", "title")
        lay.addWidget(header)
        
        self.msg = QLabel("Select which components you want to check for updates:")
        self.msg.setWordWrap(True)
        self.msg.setProperty("role", "muted")
        lay.addWidget(self.msg)
        
        group = QFrame()
        group.setStyleSheet(f"background: {t.SURFACE_2}; border-radius: 8px; padding: 10px;")
        glay = QVBoxLayout(group)
        
        self.cb_llmfit = QCheckBox("Model Advisor (LLMfit)")
        self.cb_llmfit.setChecked(True)
        self.cb_llmfit_hint = QLabel("Select to check for updates.")
        self.cb_llmfit_hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID}; margin-left: 24px;")
        
        self.cb_llama = QCheckBox("Inference Engine (llama.cpp)")
        self.cb_llama.setChecked(True)
        self.cb_llama_hint = QLabel("Select to check for updates.")
        self.cb_llama_hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID}; margin-left: 24px;")
        
        # Reset mode when selection changes
        self.cb_llmfit.stateChanged.connect(self._reset_mode)
        self.cb_llama.stateChanged.connect(self._reset_mode)

        glay.addWidget(self.cb_llmfit)
        glay.addWidget(self.cb_llmfit_hint)
        glay.addSpacing(10)
        glay.addWidget(self.cb_llama)
        glay.addWidget(self.cb_llama_hint)
        lay.addWidget(group)
        
        btns = QHBoxLayout()
        btns.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("variant", "ghost")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.action_btn = QPushButton("Run Update Check")
        self.action_btn.clicked.connect(self._handle_action)
        
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.action_btn)
        lay.addLayout(btns)

    def _reset_mode(self, *args):
        """Reset the UI to initial 'check' state when selection changes."""
        if self.mode == "probing": return
        self.mode = "check"
        self.action_btn.setText("Run Update Check")
        self.action_btn.setEnabled(True)
        self.msg.setText("Select which components you want to check for updates:")
        # Reset hints slightly to avoid confusion
        if self.cb_llmfit.isEnabled():
            self.cb_llmfit_hint.setText("Select to check for updates.")
            self.cb_llmfit_hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID}; margin-left: 24px;")
        if self.cb_llama.isEnabled():
            self.cb_llama_hint.setText("Select to check for updates.")
            self.cb_llama_hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID}; margin-left: 24px;")

    def _handle_action(self):
        if self.mode == "check":
            self._start_probe()
        elif self.mode == "apply":
            self.accept()

    def _start_probe(self):
        self.mode = "probing"
        self.action_btn.setEnabled(False)
        self.action_btn.setText("\u21BB Checking...")
        self.cb_llmfit.setEnabled(False)
        self.cb_llama.setEnabled(False)
        
        if self.cb_llmfit.isChecked(): self.cb_llmfit_hint.setText("Checking LLMfit...")
        if self.cb_llama.isChecked(): self.cb_llama_hint.setText("Checking Llama.cpp...")

        self.worker = RemoteUpdateWorker(self.ssh, self.host, self.port, self)
        self.worker.finished.connect(self._on_probe_finished)
        self.worker.failed.connect(self._on_probe_failed)
        self.worker.start()

    def _on_probe_finished(self, results: dict):
        has_updates = False
        
        # Process LLMfit
        if self.cb_llmfit.isChecked():
            val = results.get("llmfit", 0)
            if val == 999:
                 self.cb_llmfit_hint.setText("MISSING - Setup needed")
                 self.cb_llmfit_hint.setStyleSheet(f"font-size: 9pt; color: {t.ACCENT}; font-weight: bold; margin-left: 24px;")
                 has_updates = True
            elif val > 0:
                 self.cb_llmfit_hint.setText(f"UPDATE AVAILABLE ({val} commits behind)")
                 self.cb_llmfit_hint.setStyleSheet(f"font-size: 9pt; color: {t.ACCENT}; font-weight: bold; margin-left: 24px;")
                 has_updates = True
            else:
                 self.cb_llmfit_hint.setText("Up to date")
                 self.cb_llmfit_hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID}; margin-left: 24px;")
                 self.cb_llmfit.setChecked(False) # Auto uncheck if no update

        # Process Llama
        if self.cb_llama.isChecked():
            val = results.get("llamacpp", 0)
            if val == 999:
                 self.cb_llama_hint.setText("MISSING - Setup needed")
                 self.cb_llama_hint.setStyleSheet(f"font-size: 9pt; color: {t.ACCENT}; font-weight: bold; margin-left: 24px;")
                 has_updates = True
            elif val > 0:
                 self.cb_llama_hint.setText(f"UPDATE AVAILABLE ({val} commits behind)")
                 self.cb_llama_hint.setStyleSheet(f"font-size: 9pt; color: {t.ACCENT}; font-weight: bold; margin-left: 24px;")
                 has_updates = True
            else:
                 self.cb_llama_hint.setText("Up to date")
                 self.cb_llama_hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID}; margin-left: 24px;")
                 self.cb_llama.setChecked(False) # Auto uncheck if no update

        self.cb_llmfit.setEnabled(True)
        self.cb_llama.setEnabled(True)

        if has_updates:
            self.mode = "apply"
            self.action_btn.setText("Apply Updates")
            self.action_btn.setEnabled(True)
            self.msg.setText("Updates found! Select which ones to apply and click below:")
        else:
            self.mode = "none"
            self.action_btn.setText("No updates found")
            self.action_btn.setEnabled(False)
            self.msg.setText("Everything is current. No changes needed.")

    def _on_probe_failed(self, err: str):
        self.mode = "check"
        self.action_btn.setEnabled(True)
        self.action_btn.setText("Retry Check")
        self.cb_llmfit.setEnabled(True)
        self.cb_llama.setEnabled(True)
        self.msg.setText(f"Check failed: {err[:50]}")

    def get_selection(self) -> list[str]:
        res = []
        if self.cb_llmfit.isChecked():
            res.extend(["install_llmfit", "start_llmfit"])
        if self.cb_llama.isChecked():
            res.append("install_llamacpp")
        return res
