from __future__ import annotations
from PySide6.QtWidgets import QMainWindow, QInputDialog, QLineEdit
from PySide6.QtCore import QTimer, Qt
from app.controller import AppController
from app.config import ConfigStore
from app.models import AppConfig
from app.ui.settings_dialog import SettingsDialog
from app.ui.toast import Toast
from app.ui.components.title_bar import TitleBar


class MainWindow(QMainWindow):
    def __init__(self, config_store: ConfigStore):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setWindowTitle("Vast.ai Manager")
        self.resize(1240, 820)
        self.setMouseTracking(True)
        
        self._resizing = False
        self._resize_edge = 0
        self._margin = 8

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
        
        # Add app shell (it now handles its own internal TitleBar)
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
                self.controller.set_ssh_passphrase(pwd)
                return True
            prompt = "Passphrase incorreta. Tente novamente ou cancele:"
        Toast(self.shell, "Muitas tentativas incorretas. Operação cancelada.", "error")
        return False

    def nativeEvent(self, eventType, message):
        """Native Windows event handler for robust frameless resizing."""
        # 0x84 is WM_NCHITTEST
        if eventType == b'windows_generic_MSG':
            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x84:
                # Capture mouse position
                x = wintypes.SHORT(msg.lParam & 0xFFFF).value
                y = wintypes.SHORT((msg.lParam >> 16) & 0xFFFF).value
                
                # Map to local coordinates
                local_pos = self.mapFromGlobal(self.deviceCursorPos(x, y))
                lx, ly = local_pos.x(), local_pos.y()
                w, h = self.width(), self.height()
                m = self._margin

                # Determine hit zone
                if lx < m and ly < m: return True, 13 # HTTOPLEFT
                if lx > w - m and ly < m: return True, 14 # HTTOPRIGHT
                if lx < m and ly > h - m: return True, 16 # HTBOTTOMLEFT
                if lx > w - m and ly > h - m: return True, 17 # HTBOTTOMRIGHT
                if lx < m: return True, 10 # HTLEFT
                if lx > w - m: return True, 11 # HTRIGHT
                if ly < m: return True, 12 # HTTOP
                if ly > h - m: return True, 15 # HTBOTTOM

        return super().nativeEvent(eventType, message)

    def deviceCursorPos(self, x, y):
        # Handle high-DPI scaling if needed
        from PySide6.QtCore import QPoint
        return QPoint(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for t in list(Toast._stack):
            t._reposition_stack()

    def closeEvent(self, event):
        self.controller.shutdown()
        super().closeEvent(event)
