from __future__ import annotations
import os
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QPlainTextEdit, QMessageBox, QWidget
)
from app import theme
from app.models import Instance, AppConfig
from app.services.ssh_service import SSHService
from app.config import ConfigStore

class ModelScannerWorker(QThread):
    finished = Signal(bool, list, str)

    def __init__(self, ssh: SSHService, host: str, port: int):
        super().__init__()
        self.ssh = ssh
        self.host = host
        self.port = port

    def run(self):
        script = "find /workspace /models -type f -name '*.gguf' 2>/dev/null"
        success, output = self.ssh.run_script(self.host, self.port, script)
        if success:
            models = [m.strip() for m in output.split("\n") if m.strip() and m.strip().endswith(".gguf")]
            self.finished.emit(True, models, "")
        else:
            self.finished.emit(False, [], output)


class ModelDeployWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, ssh: SSHService, host: str, port: int, script: str):
        super().__init__()
        self.ssh = ssh
        self.host = host
        self.port = port
        self.script = script

    def run(self):
        success, output = self.ssh.run_script(self.host, self.port, self.script)
        self.finished.emit(success, output)


class ModelManagerDialog(QDialog):
    # Reported up to the main window so the log/toast keeps the user
    # informed even if they close this dialog.
    deploy_status = Signal(int, str, str)  # instance_id, kind, message
    # kind ∈ {"started", "progress", "ready", "failed"}

    def __init__(self, instance: Instance, ssh: SSHService, config: AppConfig, store: ConfigStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Modelos Llama - Máquina #{instance.id}")
        self.setMinimumSize(700, 550)

        self.instance = instance
        self.ssh = ssh
        self.config = config
        self.store = store

        self._scanner: ModelScannerWorker | None = None
        self._deployer: ModelDeployWorker | None = None

        self._build_ui()
        self._scan_models()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(15)

        title = QLabel(f"🚀 Escanear e Subir Modelos")
        title.setObjectName("h2")
        lay.addWidget(title)
        
        info = QLabel(f"Instância conectada em: {self.instance.ssh_host}:{self.instance.ssh_port}")
        info.setObjectName("secondary")
        lay.addWidget(info)

        # 1. Model Selector
        hl = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.addItem("Aguarde, escaneando arquivos remotamente...")
        self.combo.setEnabled(False)
        hl.addWidget(QLabel("Modelo GGUF: "))
        hl.addWidget(self.combo, 1)
        
        self.scan_btn = QPushButton("↺ Reescanear")
        self.scan_btn.setObjectName("secondary")
        self.scan_btn.clicked.connect(self._scan_models)
        hl.addWidget(self.scan_btn)
        lay.addLayout(hl)

        # 2. Template Editor
        lay.addWidget(QLabel("Template do Runner (Use {model_path} para injetar o caminho):"))
        self.template_input = QPlainTextEdit()
        self.template_input.setPlainText(self.config.model_runner_template)
        font = self.template_input.font()
        font.setFamily("Consolas")
        font.setPointSize(10)
        self.template_input.setFont(font)
        lay.addWidget(self.template_input, 1)

        # 3. Actions
        footer = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("secondary")
        footer.addWidget(self.status_lbl)
        
        footer.addStretch()
        
        cancel = QPushButton("Fechar")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)

        self.log_btn = QPushButton("Ver log remoto")
        self.log_btn.setObjectName("secondary")
        self.log_btn.clicked.connect(self._fetch_remote_log)
        footer.addWidget(self.log_btn)

        self.deploy_btn = QPushButton("► Subir Modelo na GPU")
        self.deploy_btn.setEnabled(False)
        self.deploy_btn.clicked.connect(self._deploy_model)
        footer.addWidget(self.deploy_btn)
        
        lay.addLayout(footer)

    def _scan_models(self):
        if not self.instance.ssh_host or not self.instance.ssh_port:
            self.status_lbl.setText("Erro: Máquina sem porta SSH listada.")
            return

        self.scan_btn.setEnabled(False)
        self.deploy_btn.setEnabled(False)
        self.combo.clear()
        self.combo.addItem("Escaneando /workspace e /models via SSH...")
        self.combo.setEnabled(False)

        self._scanner = ModelScannerWorker(self.ssh, self.instance.ssh_host, self.instance.ssh_port)
        self._scanner.finished.connect(self._on_scan_done)
        self._scanner.start()

    @Slot(bool, list, str)
    def _on_scan_done(self, ok: bool, models: list, err: str):
        self.scan_btn.setEnabled(True)
        self.combo.clear()
        if ok:
            if not models:
                self.combo.addItem("Nenhum arquivo *.gguf encontrado na máquina.")
                self.deploy_btn.setEnabled(False)
            else:
                for m in models:
                    self.combo.addItem(os.path.basename(m), userData=m)
                self.combo.setEnabled(True)
                self.deploy_btn.setEnabled(True)
                self.status_lbl.setText(f"{len(models)} modelos detectados!")
        else:
            self.combo.addItem("Falha ao escanear servidor remoto.")
            self.status_lbl.setText("Falha na conexão ou comando.")

    def _deploy_model(self):
        model_path = self.combo.currentData()
        if not model_path:
            return

        # Save template config
        template = self.template_input.toPlainText()
        self.config.model_runner_template = template
        self.store.save(self.config)

        script = template.replace("{model_path}", model_path)
        
        self.deploy_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.status_lbl.setText("Roteando código. Aguarde...")

        self._deployer = ModelDeployWorker(self.ssh, self.instance.ssh_host, self.instance.ssh_port, script)  # type: ignore
        self._deployer.finished.connect(self._on_deploy_done)
        self._deployer.start()

    @Slot(bool, str)
    def _on_deploy_done(self, ok: bool, output: str):
        self.scan_btn.setEnabled(True)
        self.deploy_btn.setEnabled(True)
        if not ok:
            self._set_status("⚠ Erro ao injetar script.", theme.DANGER)
            self.deploy_status.emit(self.instance.id, "failed",
                                    f"Falha no SSH: {output[:200]}")
            QMessageBox.warning(self, "Falha", f"O Bash reportou erro:\n{output[:1000]}")
            return

        # Script dispatched. The MainWindow owns the probe (so feedback survives
        # even if the user closes this dialog mid-load) and will toast/log the
        # result. Subscribe locally only for the live visual on this dialog.
        self._set_status("Script enviado. Aguardando llama-server responder...",
                         theme.WARNING)
        self.deploy_status.emit(self.instance.id, "started",
                                "Script enviado. Aguardando modelo carregar...")

    @Slot(int, str)
    def on_external_progress(self, elapsed: int, hint: str):
        """Called by MainWindow while its probe is running, so the dialog
        mirrors the live status while open."""
        self._set_status(f"⏳ Carregando modelo... {elapsed}s — {hint}", theme.WARNING)

    @Slot(str)
    def on_external_ready(self, model_id: str):
        self._set_status(f"✓ Modelo pronto e respondendo: {model_id}", theme.SUCCESS)

    @Slot(str)
    def on_external_failed(self, reason: str):
        self._set_status(f"⚠ {reason}", theme.DANGER)

    def _fetch_remote_log(self):
        """Pull the tail of /tmp/llama-server.log so the user can see why
        deployment is failing without having to SSH manually."""
        if not self.instance.ssh_host or not self.instance.ssh_port:
            QMessageBox.warning(self, "Sem SSH", "Instância sem porta SSH listada.")
            return
        self.log_btn.setEnabled(False)
        self._set_status("Baixando log remoto...", theme.WARNING)
        try:
            ok, output = self.ssh.run_script(
                self.instance.ssh_host, self.instance.ssh_port,
                # Show what we have, plus a quick "is the process alive?" check
                "echo '=== ps llama-server ==='\n"
                "pgrep -fa llama-server || echo '(nenhum processo llama-server rodando)'\n"
                "echo\n"
                "echo '=== ss -lnt 11434 ==='\n"
                "ss -lnt 'sport = :11434' 2>/dev/null || netstat -lnt 2>/dev/null | grep 11434 || echo '(porta 11434 não está em listen)'\n"
                "echo\n"
                "echo '=== tail -200 /tmp/llama-server.log ==='\n"
                "tail -200 /tmp/llama-server.log 2>/dev/null || echo '(arquivo de log inexistente)'\n"
            )
        finally:
            self.log_btn.setEnabled(True)
            self._set_status("", "")

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Log remoto — /tmp/llama-server.log (#{self.instance.id})")
        dlg.resize(900, 600)
        v = QVBoxLayout(dlg)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        font = view.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        view.setFont(font)
        view.setPlainText(output if ok else f"(falha SSH)\n{output}")
        v.addWidget(view, 1)
        close = QPushButton("Fechar")
        close.clicked.connect(dlg.accept)
        v.addWidget(close)
        dlg.exec()

    def _set_status(self, text: str, color: str = ""):
        self.status_lbl.setText(text)
        if color:
            self.status_lbl.setStyleSheet(f"color: {color}; font-weight: 500;")
        else:
            self.status_lbl.setStyleSheet("")
