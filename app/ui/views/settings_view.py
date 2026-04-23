"""Settings view — full-page settings (replaces the dialog as primary UI).
Glassmorphism design, organized into visual sections."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QPlainTextEdit, QScrollArea,
    QFileDialog,
)
from PySide6.QtCore import Signal
from app import theme as t
from app.models import AppConfig
from app.services.vast_service import VastService, VastAuthError
from app.ui.components.page_header import PageHeader
from app.ui.components.primitives import GlassCard


class SettingsView(QWidget):
    saved = Signal(object)  # AppConfig
    back_requested = Signal()
    analytics_reset_requested = Signal()

    def __init__(self, config: AppConfig | None = None, parent=None):
        super().__init__(parent)
        self._config = config or AppConfig()

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        # Header
        root.addWidget(PageHeader(
            "Settings",
            "Configure your Vast.ai Manager experience.",
        ))

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        self.sections = QVBoxLayout(content)
        self.sections.setContentsMargins(0, 0, t.SPACE_3, 0)
        self.sections.setSpacing(t.SPACE_5)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        # ── CONNECTION ─────────────────────────────────────────────────
        conn = GlassCard()
        cl = conn.body()
        cl.addWidget(_sectionTitle("CONNECTION"))

        api_row = QHBoxLayout()
        api_row.setSpacing(t.SPACE_2)
        self.api_key_input = QLineEdit(self._config.api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Paste your Vast.ai API key")
        api_row.addWidget(self.api_key_input, 1)

        self.eye_btn = QPushButton("\U0001F441")
        self.eye_btn.setProperty("variant", "ghost")
        self.eye_btn.setFixedSize(38, 38)
        self.eye_btn.clicked.connect(self._toggle_key_visibility)
        api_row.addWidget(self.eye_btn)
        cl.addLayout(api_row)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setProperty("variant", "ghost")
        self.test_btn.clicked.connect(self._on_test)
        test_row.addWidget(self.test_btn)
        self.test_status = QLabel("")
        self.test_status.setWordWrap(True)
        test_row.addWidget(self.test_status, 1)
        cl.addLayout(test_row)
        self.sections.addWidget(conn)

        # ── SSH ────────────────────────────────────────────────────────
        ssh = GlassCard()
        sl = ssh.body()
        sl.addWidget(_sectionTitle("SSH"))

        key_row = QHBoxLayout()
        key_row.setSpacing(t.SPACE_2)
        self.ssh_key_input = QLineEdit(self._config.ssh_key_path)
        self.ssh_key_input.setPlaceholderText(
            "(optional) e.g. C:\\Users\\you\\.ssh\\id_rsa"
        )
        key_row.addWidget(self.ssh_key_input, 1)
        browse_btn = QPushButton("...")
        browse_btn.setProperty("variant", "ghost")
        browse_btn.setFixedWidth(38)
        browse_btn.clicked.connect(self._on_browse_key)
        key_row.addWidget(browse_btn)
        sl.addLayout(key_row)

        hint = QLabel("Defaults to ~/.ssh/id_rsa or id_ed25519 if empty")
        hint.setStyleSheet(f"color: {t.TEXT_LOW}; font-size: {t.FONT_SIZE_SMALL}px;")
        sl.addWidget(hint)
        self.sections.addWidget(ssh)

        # ── BEHAVIOR ───────────────────────────────────────────────────
        behav = GlassCard()
        bl = behav.body()
        bl.addWidget(_sectionTitle("BEHAVIOR"))

        r1 = QHBoxLayout()
        r1.addWidget(_label("Refresh Interval"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["10", "30", "60"])
        cur = str(
            self._config.refresh_interval_seconds
            if self._config.refresh_interval_seconds in (10, 30, 60) else 30
        )
        self.interval_combo.setCurrentText(cur)
        r1.addWidget(self.interval_combo)
        r1.addSpacing(t.SPACE_5)

        r1.addWidget(_label("Default Port"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self._config.default_tunnel_port)
        r1.addWidget(self.port_input)
        bl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(_label("Terminal"))
        self.terminal_combo = QComboBox()
        self.terminal_combo.addItems(["auto", "wt", "cmd", "powershell"])
        self.terminal_combo.setCurrentText(self._config.terminal_preference)
        r2.addWidget(self.terminal_combo)
        r2.addStretch()

        self.auto_connect_cb = QCheckBox("Auto-connect on activate")
        self.auto_connect_cb.setChecked(self._config.auto_connect_on_activate)
        r2.addWidget(self.auto_connect_cb)
        bl.addLayout(r2)
        self.sections.addWidget(behav)

        # ── AUTOMATION ─────────────────────────────────────────────────
        auto = GlassCard()
        al = auto.body()
        al.addWidget(_sectionTitle("AUTOMATION"))
        al.addWidget(QLabel("On-connect script (bash, runs on every SSH connect):"))
        self.script_input = QPlainTextEdit()
        self.script_input.setPlainText(self._config.on_connect_script)
        self.script_input.setMaximumHeight(120)
        self.script_input.setStyleSheet(
            f"font-family: {t.FONT_MONO}; font-size: {t.FONT_SIZE_MONO}px;"
            f" background: {t.BG_VOID}; color: {t.TEXT_HI};"
            f" border: 1px solid {t.BORDER_LOW};"
            f" border-radius: {t.RADIUS_MD}px;"
        )
        al.addWidget(self.script_input)
        self.sections.addWidget(auto)

        # ── ANALYTICS ──────────────────────────────────────────────────
        analytics = GlassCard()
        anl = analytics.body()
        anl.addWidget(_sectionTitle("ANALYTICS"))
        desc = QLabel(
            "Clear local analytics history and rebuild it from the current Vast.ai account."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {t.TEXT_MID};")
        anl.addWidget(desc)
        reset_row = QHBoxLayout()
        reset_row.addStretch()
        self.reset_analytics_btn = QPushButton("Reset Analytics & Re-sync")
        self.reset_analytics_btn.setProperty("variant", "ghost")
        self.reset_analytics_btn.clicked.connect(self.analytics_reset_requested.emit)
        reset_row.addWidget(self.reset_analytics_btn)
        anl.addLayout(reset_row)
        self.sections.addWidget(analytics)

        # ── ABOUT ──────────────────────────────────────────────────────
        about = GlassCard()
        abl = about.body()
        abl.addWidget(_sectionTitle("ABOUT"))
        abl.addWidget(QLabel("Vast.ai Manager v2.1"))
        abl.addWidget(QLabel("Remote AI Lab — Cloud GPU Management"))
        self.sections.addWidget(about)

        self.sections.addStretch()

        # ── Footer buttons ─────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("variant", "ghost")
        cancel_btn.clicked.connect(self.back_requested.emit)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setMinimumWidth(160)
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)
        root.addLayout(footer)

    # ── Public ─────────────────────────────────────────────────────────
    def load_config(self, config: AppConfig):
        self._config = config
        self.api_key_input.setText(config.api_key)
        self.ssh_key_input.setText(config.ssh_key_path)
        cur = str(
            config.refresh_interval_seconds
            if config.refresh_interval_seconds in (10, 30, 60) else 30
        )
        self.interval_combo.setCurrentText(cur)
        self.port_input.setValue(config.default_tunnel_port)
        self.terminal_combo.setCurrentText(config.terminal_preference)
        self.auto_connect_cb.setChecked(config.auto_connect_on_activate)
        self.script_input.setPlainText(config.on_connect_script)

    # ── Private ────────────────────────────────────────────────────────
    def _toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.eye_btn.setText("\U0001F441\u200D\U0001F5E8")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.eye_btn.setText("\U0001F441")

    def _on_browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose SSH private key", "",
            "All keys (id_rsa id_ed25519 *.pem);;All files (*)",
        )
        if path:
            self.ssh_key_input.setText(path)

    def _on_test(self):
        key = self.api_key_input.text().strip()
        if not key:
            self._set_status("Enter your API key first.", t.WARN)
            return
        self._set_status("Testing...", t.TEXT_MID)
        self.test_btn.setEnabled(False)
        try:
            svc = VastService(key)
            user = svc.test_connection()
            self._set_status(
                f"\u2713 Connected. Balance: ${user.balance:.2f}", t.OK
            )
        except VastAuthError:
            self._set_status("\u2717 Invalid API key.", t.ERR)
        except Exception as e:
            self._set_status(f"\u2717 Failed: {e}", t.ERR)
        finally:
            self.test_btn.setEnabled(True)

    def _on_save(self):
        key = self.api_key_input.text().strip()
        if not key:
            self._set_status("API key is required.", t.ERR)
            return
        cfg = AppConfig(
            api_key=key,
            refresh_interval_seconds=int(self.interval_combo.currentText()),
            default_tunnel_port=self.port_input.value(),
            terminal_preference=self.terminal_combo.currentText(),
            auto_connect_on_activate=self.auto_connect_cb.isChecked(),
            ssh_key_path=self.ssh_key_input.text().strip(),
            on_connect_script=self.script_input.toPlainText().strip(),
            model_runner_template=self._config.model_runner_template,
            include_storage_in_burn_rate=self._config.include_storage_in_burn_rate,
            burn_rate_smoothing_window=self._config.burn_rate_smoothing_window,
            estimated_network_cost_per_hour=self._config.estimated_network_cost_per_hour,
            port_map=dict(self._config.port_map),
            instance_filters=dict(self._config.instance_filters),
            start_requested_ids=list(self._config.start_requested_ids),
            start_requested_at=dict(self._config.start_requested_at),
            bulk_confirm_threshold=self._config.bulk_confirm_threshold,
            schema_version=3,
        )
        self.saved.emit(cfg)

    def _set_status(self, text: str, color: str):
        self.test_status.setText(text)
        self.test_status.setStyleSheet(
            f"color: {color}; font-weight: 500;"
        )


# ── Helpers ────────────────────────────────────────────────────────────────

def _sectionTitle(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 600;"
        f" letter-spacing: 1.5px; padding-bottom: 4px;"
    )
    return lbl


def _label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_BODY}px;"
        f" min-width: 100px;"
    )
    return lbl
