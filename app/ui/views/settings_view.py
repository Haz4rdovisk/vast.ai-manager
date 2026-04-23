"""Full-page settings view for account, SSH, runtime, and local analytics."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.models import AppConfig
from app.services.vast_service import VastAuthError, VastService
from app.ui.components.page_header import PageHeader


class SettingsView(QWidget):
    saved = Signal(object)  # AppConfig
    back_requested = Signal()
    analytics_reset_requested = Signal()

    def __init__(self, config: AppConfig | None = None, parent=None):
        super().__init__(parent)
        self._config = config or AppConfig()
        self.setObjectName("settings-page")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._apply_styles()

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_4, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        root.addWidget(PageHeader(
            "Settings",
            "Account, SSH, runtime defaults, and automation.",
        ))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("settings-content")
        
        # Use QGridLayout for equal-width columns and balanced card heights
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, t.SPACE_2, 0)
        grid.setSpacing(t.SPACE_4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Row 0: Connection and SSH (Equal width and height)
        conn_card = self._build_connection_card()
        ssh_card = self._build_ssh_card()
        
        # Ensure they both expand to fill the cell height together
        # Connection's natural height will dictate the row height
        conn_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ssh_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        grid.addWidget(conn_card, 0, 0)
        grid.addWidget(ssh_card, 0, 1)

        # Row 1: Runtime and Summary/Analytics
        runtime_card = self._build_runtime_card()
        grid.addWidget(runtime_card, 1, 0)

        summary_col = QVBoxLayout()
        summary_col.setContentsMargins(0, 0, 0, 0)
        summary_col.setSpacing(t.SPACE_4)
        status_card = self._build_status_card()
        analytics_card = self._build_analytics_card()
        
        # Stack vertically and allow both to stretch
        status_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        analytics_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        summary_col.addWidget(status_card)
        summary_col.addWidget(analytics_card)
        grid.addLayout(summary_col, 1, 1)

        # Row 2: Automation and About
        automation_card = self._build_automation_card()
        about_card = self._build_about_card()
        
        # Balance heights for Automation and About
        automation_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        about_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        grid.addWidget(automation_card, 2, 0)
        grid.addWidget(about_card, 2, 1)

        # Push everything to top
        grid.setRowStretch(3, 1)

        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        root.addLayout(self._build_footer())
        self._wire_summary_updates()
        self._refresh_summary()

    # Public
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
        self._set_status("Connection not tested in this session.", t.TEXT_MID)
        self._refresh_summary()

    # Builders
    def _build_connection_card(self) -> QFrame:
        card, body = _settings_card(
            "Connection",
            "Authenticate requests against the Vast.ai API.",
        )

        body.addWidget(_field_label("Vast.ai API key"))
        api_row = QHBoxLayout()
        api_row.setSpacing(t.SPACE_2)
        self.api_key_input = QLineEdit(self._config.api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Paste your Vast.ai API key")
        self.api_key_input.setMinimumHeight(42)
        api_row.addWidget(self.api_key_input, 1)

        self.eye_btn = QPushButton("Show")
        self.eye_btn.setProperty("variant", "ghost")
        self.eye_btn.setFixedWidth(76)
        self.eye_btn.clicked.connect(self._toggle_key_visibility)
        api_row.addWidget(self.eye_btn)

        self.test_btn = QPushButton("Test")
        self.test_btn.setProperty("variant", "secondary")
        self.test_btn.setFixedWidth(82)
        self.test_btn.clicked.connect(self._on_test)
        api_row.addWidget(self.test_btn)
        body.addLayout(api_row)

        self.test_status = _inline_info("Add a key and test it before saving.")
        body.addWidget(self.test_status)
        body.addStretch(1)
        return card

    def _build_ssh_card(self) -> QFrame:
        card, body = _settings_card(
            "SSH access",
            "Choose the private key used for terminal sessions and tunnels.",
        )
        body.addWidget(_field_label("Private key path"))
        key_row = QHBoxLayout()
        key_row.setSpacing(t.SPACE_2)
        self.ssh_key_input = QLineEdit(self._config.ssh_key_path)
        self.ssh_key_input.setPlaceholderText(
            "(optional) e.g. C:\\Users\\you\\.ssh\\id_rsa"
        )
        self.ssh_key_input.setMinimumHeight(42)
        key_row.addWidget(self.ssh_key_input, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.setProperty("variant", "ghost")
        browse_btn.setFixedWidth(92)
        browse_btn.clicked.connect(self._on_browse_key)
        key_row.addWidget(browse_btn)
        body.addLayout(key_row)
        body.addWidget(_inline_info("Leave blank to auto-detect ~/.ssh/id_rsa or id_ed25519."))
        body.addStretch(1)
        return card

    def _build_runtime_card(self) -> QFrame:
        card, body = _settings_card(
            "Runtime defaults",
            "Set the operational behavior used by Instances and Studio.",
        )

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(t.SPACE_3)
        grid.setVerticalSpacing(t.SPACE_3)

        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["10", "30", "60"])
        cur = str(
            self._config.refresh_interval_seconds
            if self._config.refresh_interval_seconds in (10, 30, 60) else 30
        )
        self.interval_combo.setCurrentText(cur)
        grid.addWidget(
            _field_block("Refresh interval", "How often fleet data updates.", self.interval_combo),
            0,
            0,
        )

        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self._config.default_tunnel_port)
        grid.addWidget(
            _field_block("Default tunnel port", "Used when allocating local access.", self.port_input),
            0,
            1,
        )

        self.terminal_combo = QComboBox()
        self.terminal_combo.addItems(["auto", "wt", "cmd", "powershell"])
        self.terminal_combo.setCurrentText(self._config.terminal_preference)
        grid.addWidget(
            _field_block("Terminal", "Preferred shell launcher.", self.terminal_combo),
            1,
            0,
        )

        auto_box = QFrame()
        auto_box.setObjectName("settings-switch-box")
        auto_lay = QVBoxLayout(auto_box)
        auto_lay.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        auto_lay.setSpacing(t.SPACE_2)
        self.auto_connect_cb = QCheckBox("Auto-connect on activate")
        self.auto_connect_cb.setChecked(self._config.auto_connect_on_activate)
        auto_lay.addWidget(self.auto_connect_cb)
        auto_lay.addWidget(_hint("Automatically opens SSH after an instance becomes active."))
        grid.addWidget(auto_box, 1, 1)

        body.addLayout(grid)
        return card

    def _build_automation_card(self) -> QFrame:
        card, body = _settings_card(
            "Automation",
            "Run an optional bash snippet every time an SSH connection opens.",
        )
        self.script_input = QPlainTextEdit()
        self.script_input.setPlainText(self._config.on_connect_script)
        self.script_input.setPlaceholderText(
            "Example: pkill -f llama-server || true\n"
            "nohup /opt/llama.cpp/build/bin/llama-server ... &"
        )
        self.script_input.setMinimumHeight(132)
        self.script_input.setMaximumHeight(180)
        self.script_input.setObjectName("settings-script-input")
        body.addWidget(self.script_input)
        body.addWidget(_hint("Runs remotely via bash. Keep it idempotent so reconnects stay safe."))
        body.addStretch(1)
        return card

    def _build_status_card(self) -> QFrame:
        card, body = _settings_card("Live summary", "")
        grid = QGridLayout()
        grid.setSpacing(t.SPACE_3)

        self.summary_api = _summary_row("API", "")
        self.summary_ssh = _summary_row("SSH key", "")
        self.summary_runtime = _summary_row("Runtime", "")
        self.summary_auto = _summary_row("Automation", "")

        for row in [self.summary_api, self.summary_ssh, self.summary_runtime, self.summary_auto]:
            row.setMinimumHeight(70)

        grid.addWidget(self.summary_api, 0, 0, Qt.AlignTop)
        grid.addWidget(self.summary_ssh, 0, 1, Qt.AlignTop)
        grid.addWidget(self.summary_runtime, 1, 0, Qt.AlignTop)
        grid.addWidget(self.summary_auto, 1, 1, Qt.AlignTop)

        body.addLayout(grid)
        body.addStretch(1)
        return card

    def _build_analytics_card(self) -> QFrame:
        card, body = _settings_card(
            "Analytics",
            "Rebuild local billing history from the active Vast.ai account.",
        )
        self.reset_analytics_btn = QPushButton("Reset & Re-sync")
        self.reset_analytics_btn.setProperty("variant", "ghost")
        self.reset_analytics_btn.clicked.connect(self.analytics_reset_requested.emit)
        body.addWidget(self.reset_analytics_btn)
        body.addStretch(1)
        return card

    def _build_about_card(self) -> QFrame:
        card, body = _settings_card("About", "Build and workspace details.")
        body.addWidget(_info_line("App", "Vast.ai Manager v2.1"))
        body.addWidget(_info_line("Author", "Haz4rdovisk"))
        body.addWidget(_info_line("Mode", "Remote AI Lab"))
        body.addWidget(_info_line("Config", "~/.vastai-app/config.json"))
        body.addStretch(1)
        return card

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(t.SPACE_2)
        footer.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("variant", "ghost")
        cancel_btn.clicked.connect(self.back_requested.emit)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setMinimumWidth(170)
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)
        return footer

    # Private
    def _wire_summary_updates(self):
        self.api_key_input.textChanged.connect(self._refresh_summary)
        self.ssh_key_input.textChanged.connect(self._refresh_summary)
        self.interval_combo.currentTextChanged.connect(self._refresh_summary)
        self.port_input.valueChanged.connect(self._refresh_summary)
        self.terminal_combo.currentTextChanged.connect(self._refresh_summary)
        self.auto_connect_cb.toggled.connect(self._refresh_summary)
        self.script_input.textChanged.connect(self._refresh_summary)

    def _refresh_summary(self):
        api_key = self.api_key_input.text().strip()
        ssh_key = self.ssh_key_input.text().strip()
        script = self.script_input.toPlainText().strip()
        auto = self.auto_connect_cb.isChecked()

        self.summary_api.value.setText("Configured" if api_key else "Missing")
        self.summary_api.value.setStyleSheet(_summary_value_style(t.OK if api_key else t.WARN))
        self.summary_ssh.value.setText("Custom path" if ssh_key else "Auto-detect")
        self.summary_runtime.value.setText(
            f"{self.interval_combo.currentText()}s refresh / port {self.port_input.value()}"
        )
        self.summary_auto.value.setText("Script enabled" if script else "No script")
        self.summary_auto.value.setStyleSheet(_summary_value_style(t.OK if script else t.TEXT_MID))
        self.summary_ssh.caption.setText(ssh_key or "Using default SSH key discovery")
        self.summary_runtime.caption.setText("Fleet refresh and local tunnel defaults")
        self.summary_api.caption.setText("Required for Store, Instances, Analytics")
        self.summary_auto.caption.setText(
            f"{'Auto-connect' if auto else 'Manual connect'} via {self.terminal_combo.currentText()}"
        )

    def _toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.eye_btn.setText("Hide")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.eye_btn.setText("Show")

    def _on_browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose SSH private key",
            "",
            "All keys (id_rsa id_ed25519 *.pem);;All files (*)",
        )
        if path:
            self.ssh_key_input.setText(path)

    def _on_test(self):
        key = self.api_key_input.text().strip()
        if not key:
            self._set_status("Enter your API key first.", t.WARN)
            return
        self._set_status("Testing connection...", t.TEXT_MID)
        self.test_btn.setEnabled(False)
        try:
            svc = VastService(key)
            user = svc.test_connection()
            self._set_status(f"Connected. Balance: ${user.balance:.2f}", t.OK)
        except VastAuthError:
            self._set_status("Invalid API key.", t.ERR)
        except Exception as exc:
            self._set_status(f"Failed: {exc}", t.ERR)
        finally:
            self.test_btn.setEnabled(True)
            self._refresh_summary()

    def _on_save(self):
        key = self.api_key_input.text().strip()
        if not key:
            self._set_status("API key is required.", t.ERR)
            return
        cfg = replace(
            self._config,
            api_key=key,
            refresh_interval_seconds=int(self.interval_combo.currentText()),
            default_tunnel_port=self.port_input.value(),
            terminal_preference=self.terminal_combo.currentText(),
            auto_connect_on_activate=self.auto_connect_cb.isChecked(),
            ssh_key_path=self.ssh_key_input.text().strip(),
            on_connect_script=self.script_input.toPlainText().strip(),
            schema_version=3,
        )
        self._config = cfg
        self.saved.emit(cfg)
        self._set_status("Settings saved.", t.OK)
        self._refresh_summary()

    def _set_status(self, text: str, color: str):
        self.test_status.setText(text)
        self.test_status.setStyleSheet(
            f"color: {color}; background: rgba(255,255,255,0.03);"
            f" border: 1px solid {t.BORDER_LOW}; border-radius: 10px;"
            f" padding: 9px 11px; font-weight: 700;"
        )

    def _apply_styles(self):
        self.setStyleSheet(
            f"""
            QWidget#settings-page {{
                background: {t.BG_DEEP};
            }}
            QWidget#settings-content {{
                background: transparent;
            }}
            QFrame#settings-card {{
                background: #101722;
                border: 1px solid #243047;
                border-radius: 16px;
            }}
            QFrame#settings-card:hover {{
                background: #121b29;
                border-color: #33415d;
            }}
            QLabel#settings-card-title {{
                color: {t.TEXT_HI};
                font-size: 18px;
                font-weight: 900;
            }}
            QLabel#settings-card-subtitle,
            QLabel#settings-body,
            QLabel#settings-small {{
                color: {t.TEXT_MID};
                font-size: 12px;
            }}
            QLabel#settings-field-label {{
                color: {t.TEXT_HI};
                font-size: 12px;
                font-weight: 800;
            }}
            QLabel#settings-hint {{
                color: {t.TEXT_LOW};
                font-size: 12px;
            }}
            QFrame#settings-field-block,
            QFrame#settings-switch-box {{
                background: rgba(255,255,255,0.025);
                border: 1px solid rgba(255,255,255,0.055);
                border-radius: 14px;
            }}
            QPlainTextEdit#settings-script-input {{
                background: {t.BG_VOID};
                color: {t.TEXT_HI};
                border: 1px solid {t.BORDER_MED};
                border-radius: 12px;
                font-family: {t.FONT_MONO};
                font-size: {t.FONT_SIZE_MONO}px;
                padding: 12px;
            }}
            """
        )


def _settings_card(title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("settings-card")
    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
    lay.setSpacing(t.SPACE_3)

    header = QHBoxLayout()
    header.setContentsMargins(0, 0, 0, 0)
    header.setSpacing(0)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(2)
    title_label = QLabel(title)
    title_label.setObjectName("settings-card-title")
    title_col.addWidget(title_label)
    
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("settings-card-subtitle")
        subtitle_label.setWordWrap(True)
        title_col.addWidget(subtitle_label)
        
    header.addLayout(title_col, 1)
    lay.addLayout(header)
    return card, lay


def _field_block(title: str, caption: str, control: QWidget) -> QFrame:
    box = QFrame()
    box.setObjectName("settings-field-block")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(t.SPACE_3, t.SPACE_4, t.SPACE_3, t.SPACE_4)
    lay.setSpacing(t.SPACE_2)
    lay.addWidget(_field_label(title))
    lay.addWidget(control)
    lay.addWidget(_hint(caption))
    box.setMinimumHeight(86)
    return box


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("settings-field-label")
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("settings-hint")
    lbl.setWordWrap(True)
    return lbl


def _inline_info(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {t.TEXT_MID}; background: rgba(255,255,255,0.03);"
        f" border: 1px solid {t.BORDER_LOW}; border-radius: 10px;"
        f" padding: 9px 11px; font-weight: 700;"
    )
    lbl.setWordWrap(True)
    return lbl


def _summary_row(title: str, value: str) -> QFrame:
    row = QFrame()
    row.setObjectName("settings-field-block")
    lay = QVBoxLayout(row)
    lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
    lay.setSpacing(3)
    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    name = _field_label(title)
    val = QLabel(value)
    val.setStyleSheet(_summary_value_style(t.TEXT_HI))
    top.addWidget(name)
    top.addStretch(1)
    top.addWidget(val)
    caption = _hint("")
    lay.addLayout(top)
    lay.addWidget(caption)
    row.value = val
    row.caption = caption
    row.setMinimumHeight(72)
    return row


def _summary_value_style(color: str) -> str:
    return (
        f"color: {color}; font-family: {t.FONT_MONO};"
        " font-size: 12px; font-weight: 900;"
    )


def _info_line(key: str, value: str) -> QFrame:
    row = QFrame()
    row.setObjectName("settings-field-block")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
    lay.setSpacing(t.SPACE_2)
    k = _hint(key)
    v = QLabel(value)
    v.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 12px; font-weight: 800;")
    lay.addWidget(k)
    lay.addStretch(1)
    lay.addWidget(v)
    return row
