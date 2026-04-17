from __future__ import annotations
from PySide6.QtWidgets import QMainWindow, QInputDialog, QLineEdit
from PySide6.QtCore import QTimer
from app.controller import AppController
from app.config import ConfigStore
from app.models import AppConfig
from app.ui.settings_dialog import SettingsDialog
from app.ui.toast import Toast


class MainWindow(QMainWindow):
    def __init__(self, config_store: ConfigStore):
        super().__init__()
        self.setWindowTitle("Vast.ai Manager")
        self.resize(1240, 820)

        self.config_store = config_store
        self.config = config_store.load()

        self.controller = AppController(config_store, self)

        self._build_ui()

        # Route toasts from controller
        self.controller.toast_requested.connect(
            lambda m, k, d: Toast(self.shell, m, k, d)
        )
        self.controller.passphrase_needed.connect(self._prompt_passphrase)

        if not self.config.api_key:
            QTimer.singleShot(150, self._open_settings)
        else:
            self.controller.bootstrap()

    def _build_ui(self):
        from app.ui.app_shell import AppShell
        self.shell = AppShell(self.config, self.config_store, self.controller.ssh, self)
        self.shell.attach_controller(self.controller)
        self.setCentralWidget(self.shell)

    def open_settings(self):
        self._open_settings()

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, cfg: AppConfig):
        self.config = cfg
        self.controller.apply_config(cfg)

    def _prompt_passphrase(self):
        if not self.controller.ssh.is_passphrase_required() or self.controller.ssh.passphrase_cache:
            return True
        prompt = "Digite a passphrase da sua chave SSH para continuar:"
        for _ in range(5):
            pwd, ok = QInputDialog.getText(
                self, "Chave SSH Protegida", prompt, QLineEdit.Password,
            )
            if not ok:
                return False
            if not pwd:
                prompt = "Passphrase vazia. Tente novamente ou cancele:"
                continue
            if self.controller.ssh.verify_passphrase(pwd):
                self.controller.ssh.set_passphrase(pwd)
                return True
            prompt = "Passphrase incorreta. Tente novamente ou cancele:"
        Toast(self.shell, "Muitas tentativas incorretas. Operação cancelada.", "error")
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for t in list(Toast._stack):
            t._reposition_stack()

    def closeEvent(self, event):
        self.controller.shutdown()
        super().closeEvent(event)
