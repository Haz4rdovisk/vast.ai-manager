from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QFormLayout, QFileDialog, QWidget,
    QPlainTextEdit,
)
from PySide6.QtCore import Signal
from app.models import AppConfig
from app.services.vast_service import VastService, VastAuthError
from app import theme


class SettingsDialog(QDialog):
    saved = Signal(object)  # AppConfig

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.setMinimumWidth(500)
        self.config = config

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        title = QLabel("Configurações")
        title.setObjectName("h1")
        lay.addWidget(title)

        subtitle = QLabel("A API key é salva em %USERPROFILE%\\.vastai-app\\config.json")
        subtitle.setObjectName("secondary")
        lay.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(12)

        self.api_key_input = QLineEdit(config.api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("cole sua Vast.ai API key")
        form.addRow("API Key", self.api_key_input)

        self.interval_input = QComboBox()
        self.interval_input.addItems(["10", "30", "60"])
        cur = str(config.refresh_interval_seconds if config.refresh_interval_seconds in (10, 30, 60) else 30)
        self.interval_input.setCurrentText(cur)
        form.addRow("Intervalo de atualização (s)", self.interval_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(config.default_tunnel_port)
        form.addRow("Porta local padrão", self.port_input)

        self.terminal_input = QComboBox()
        self.terminal_input.addItems(["auto", "wt", "cmd", "powershell"])
        self.terminal_input.setCurrentText(config.terminal_preference)
        form.addRow("Terminal preferido", self.terminal_input)

        self.auto_connect_input = QCheckBox("Conectar automaticamente ao ativar uma instância")
        self.auto_connect_input.setChecked(config.auto_connect_on_activate)
        form.addRow("", self.auto_connect_input)

        # SSH key path (optional — defaults to ~/.ssh/id_rsa or id_ed25519)
        key_row = QWidget()
        key_h = QHBoxLayout(key_row)
        key_h.setContentsMargins(0, 0, 0, 0)
        self.ssh_key_input = QLineEdit(config.ssh_key_path)
        self.ssh_key_input.setPlaceholderText("(opcional) ex: C:\\Users\\voce\\.ssh\\id_rsa")
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(32)
        browse_btn.setObjectName("secondary")
        browse_btn.clicked.connect(self._on_browse_key)
        key_h.addWidget(self.ssh_key_input)
        key_h.addWidget(browse_btn)
        form.addRow("Chave SSH privada", key_row)

        self.on_connect_script_input = QPlainTextEdit()
        self.on_connect_script_input.setPlainText(config.on_connect_script)
        self.on_connect_script_input.setPlaceholderText("Script bash opcional para rodar ao conectar na Vast (ex: pkill llama; nohup ...)")
        self.on_connect_script_input.setFixedHeight(120)
        self.on_connect_script_input.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        form.addRow("Script Incial\n(Opcional)", self.on_connect_script_input)

        lay.addLayout(form)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        lay.addWidget(self.status_lbl)

        btns = QHBoxLayout()
        self.test_btn = QPushButton("Testar conexão")
        self.test_btn.setObjectName("secondary")
        self.test_btn.clicked.connect(self._on_test)
        self.save_btn = QPushButton("Salvar")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.test_btn)
        btns.addStretch()
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)
        lay.addLayout(btns)

    def _current_config(self) -> AppConfig:
        return AppConfig(
            api_key=self.api_key_input.text().strip(),
            refresh_interval_seconds=int(self.interval_input.currentText()),
            default_tunnel_port=self.port_input.value(),
            terminal_preference=self.terminal_input.currentText(),
            auto_connect_on_activate=self.auto_connect_input.isChecked(),
            ssh_key_path=self.ssh_key_input.text().strip(),
            on_connect_script=self.on_connect_script_input.toPlainText().strip(),
            # Preserve non-UI-exposed fields so saving doesn't reset them.
            model_runner_template=self.config.model_runner_template,
            include_storage_in_burn_rate=self.config.include_storage_in_burn_rate,
            burn_rate_smoothing_window=self.config.burn_rate_smoothing_window,
            estimated_network_cost_per_hour=self.config.estimated_network_cost_per_hour,
            schema_version=2,
        )

    def _on_browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolha sua chave SSH privada", "",
            "Todas as chaves (id_rsa id_ed25519 id_ecdsa *.pem);;Todos os arquivos (*)",
        )
        if path:
            self.ssh_key_input.setText(path)

    def _on_test(self):
        cfg = self._current_config()
        if not cfg.api_key:
            self._set_status("Cole sua API key primeiro.", theme.WARNING)
            return
        self._set_status("Testando...", theme.TEXT_SECONDARY)
        self.test_btn.setEnabled(False)
        try:
            svc = VastService(cfg.api_key)
            user = svc.test_connection()
            self._set_status(f"✓ Conectado. Saldo atual: ${user.balance:.2f}", theme.SUCCESS)
        except VastAuthError:
            self._set_status("✗ API key inválida.", theme.DANGER)
        except Exception as e:
            self._set_status(f"✗ Falha: {e}", theme.DANGER)
        finally:
            self.test_btn.setEnabled(True)

    def _on_save(self):
        cfg = self._current_config()
        if not cfg.api_key:
            self._set_status("API key é obrigatória.", theme.DANGER)
            return
        self.saved.emit(cfg)
        self.accept()

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {color}; font-weight: 500;")
