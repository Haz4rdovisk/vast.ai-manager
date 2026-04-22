"""Studio view for loading an installed GGUF on a selected instance."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QUrl, QTimer, QStandardPaths
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript

from app import theme as t
from app.lab.state.models import ServerParams
from app.ui.components.diagnostic_banner import DiagnosticBanner
from app.ui.components.server_params_form import ServerParamsForm
from app.ui.brand_manager import BrandManager
from app.ui.components.lock_screen import LockScreen
from PySide6.QtCore import QSize


_EMPTY_WEBUI_HTML = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      height: 100vh;
      overflow: hidden;
      background: {t.BG_DEEP};
      color: {t.TEXT};
      font-family: Inter, Segoe UI, sans-serif;
    }}
    .stage {{
      height: 100vh;
      display: grid;
      place-items: center;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.018), rgba(0,0,0,0)),
        {t.BG_DEEP};
    }}
    .empty {{
      max-width: 480px;
      text-align: center;
      color: {t.TEXT_LOW};
      font-size: 14px;
      letter-spacing: 0;
      padding: 28px 32px;
      background: rgba(12, 16, 22, 0.72);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 20px;
      box-shadow: 0 24px 80px rgba(0,0,0,0.28);
    }}
    .eyebrow {{
      color: {t.ACCENT_SOFT};
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1.6px;
      text-transform: uppercase;
      margin-bottom: 14px;
    }}
    strong {{
      display: block;
      color: {t.TEXT};
      font-size: 24px;
      font-weight: 800;
      margin-bottom: 10px;
    }}
    p {{
      margin: 0;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <main class="stage">
    <section class="empty">
      <div class="eyebrow">AI Lab Studio</div>
      <strong>No model loaded</strong>
      <p>Pick a model in the top selector, adjust Settings, then press Load Model. The chat input appears here inside the llama.cpp webui after launch.</p>
    </section>
  </main>
</body>
</html>
"""


_LOADING_WEBUI_HTML = f"""
<!doctype html>
<html>
<head>
  <style>
    body {{
      margin: 0;
      height: 100vh;
      display: grid;
      place-items: center;
      background: {t.BG_DEEP};
      color: {t.TEXT_MID};
      font-family: Inter, sans-serif;
    }}
    .loader {{
      width: 48px;
      height: 48px;
      border: 3px solid rgba(255,255,255,0.05);
      border-radius: 50%;
      display: inline-block;
      position: relative;
      box-sizing: border-box;
      animation: rotation 1s linear infinite;
    }}
    .loader::after {{
      content: '';  
      box-sizing: border-box;
      position: absolute;
      left: 0;
      top: 0;
      width: 48px;
      height: 48px;
      border-radius: 50%;
      border-bottom: 3px solid {t.ACCENT};
      animation: rotation 1s linear infinite;
    }}
    @keyframes rotation {{
      0% {{ transform: rotate(0deg); }}
      100% {{ transform: rotate(360deg); }}
    }} 
    .status {{
      margin-top: 20px;
      font-size: 13px;
      font-weight: 500;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
  </style>
</head>
<body>
  <div style="text-align: center;">
    <span class="loader"></span>
    <div class="status">Establishing Secure Tunnel...</div>
  </div>
</body>
</html>
"""


class LaunchLogPanel(QFrame):
    """Compact launch drawer for llama-server startup output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("launch-log-panel")
        self.setFixedHeight(220)
        self.setStyleSheet(
            f"""
            QFrame#launch-log-panel {{
                background: #090d15;
                border-top: 1px solid rgba(255,255,255,0.08);
            }}
            QLabel#launch-log-title {{
                color: {t.TEXT_HI};
                font-size: 13px;
                font-weight: 800;
            }}
            QLabel#launch-log-subtitle {{
                color: {t.TEXT_LOW};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel[stage="true"] {{
                border-radius: 8px;
                padding: 4px 9px;
                font-size: 11px;
                font-weight: 800;
                font-family: {t.FONT_MONO};
            }}
            QPlainTextEdit#launch-log-text {{
                background: #030508;
                color: {t.TEXT};
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                padding: 10px;
                font-family: {t.FONT_MONO};
                font-size: 12px;
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_4)
        root.setSpacing(t.SPACE_3)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(t.SPACE_3)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(1)
        title = QLabel("Launch Log")
        title.setObjectName("launch-log-title")
        subtitle = QLabel("llama-server startup output")
        subtitle.setObjectName("launch-log-subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self._stage_labels: dict[str, QLabel] = {}
        for key, label in [
            ("start", "start"),
            ("load", "load"),
            ("ready", "ready"),
        ]:
            chip = QLabel(label)
            chip.setProperty("stage", "true")
            self._stage_labels[key] = chip
            header.addWidget(chip)
        root.addLayout(header)

        self._log = QPlainTextEdit()
        self._log.setObjectName("launch-log-text")
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(800)
        self._log.setPlaceholderText("Waiting for llama-server output...")
        root.addWidget(self._log, 1)

        self.set_stage("start", "pending")
        self.set_stage("load", "pending")
        self.set_stage("ready", "pending")

    def append_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    def log_text(self) -> str:
        return self._log.toPlainText()

    def set_stage(self, stage: str, state: str) -> None:
        label = self._stage_labels.get(stage)
        if label is None:
            return
        palette = {
            "pending": (t.TEXT_LOW, "rgba(255,255,255,0.04)", "rgba(255,255,255,0.08)"),
            "running": (t.INFO, "rgba(78,168,255,0.10)", "rgba(78,168,255,0.28)"),
            "done": (t.OK, "rgba(59,212,136,0.10)", "rgba(59,212,136,0.28)"),
            "failed": (t.ERR, "rgba(240,85,106,0.10)", "rgba(240,85,106,0.28)"),
        }
        fg, bg, border = palette.get(state, palette["pending"])
        label.setStyleSheet(
            f"QLabel {{ color: {fg}; background: {bg};"
            f" border: 1px solid {border}; }}"
        )

    def reset(self) -> None:
        self._log.clear()
        self.set_stage("start", "pending")
        self.set_stage("load", "pending")
        self.set_stage("ready", "pending")


class StudioView(QWidget):
    launch_requested = Signal(object)
    stop_requested = Signal()
    fix_requested = Signal(str)
    instances_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("studio-view")
        self.setStyleSheet(
            f"""
            QWidget#studio-view {{
                background: {t.BG_DEEP};
            }}
            QWidget#studio-topbar {{
                background: #05080d;
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }}
            QLabel#studio-brand {{
                color: {t.TEXT_HI};
                font-size: 15px;
                font-weight: 900;
            }}
            QLabel#studio-subbrand {{
                color: {t.TEXT_MID};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QLabel#studio-status-pill {{
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 8px 12px;
                min-width: 76px;
                font-weight: 800;
            }}
            QComboBox#studio-instance-picker {{
                background: transparent;
                border: 1px solid rgba(255,255,255,0.08);
                color: {t.TEXT};
                min-height: 30px;
                padding: 6px 10px;
                border-radius: 10px;
            }}
            QComboBox#studio-model-picker {{
                background: #281f68;
                border: 1px solid rgba(179,160,255,0.44);
                color: white;
                min-height: 38px;
                padding: 7px 16px;
                font-weight: 700;
                border-radius: 12px;
            }}
            QComboBox#studio-model-picker:disabled {{
                background: #101722;
                border-color: rgba(255,255,255,0.10);
                color: {t.TEXT_MID};
            }}
            QWidget#studio-view QComboBox,
            QWidget#studio-view QLineEdit,
            QWidget#studio-view QSpinBox,
            QWidget#studio-view QDoubleSpinBox {{
                background: #111820;
                color: {t.TEXT_HI};
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                padding: 5px 10px;
                min-height: 24px;
            }}
            QWidget#studio-view QComboBox:focus,
            QWidget#studio-view QLineEdit:focus,
            QWidget#studio-view QSpinBox:focus,
            QWidget#studio-view QDoubleSpinBox:focus {{
                border-color: {t.ACCENT};
            }}
            QWidget#studio-view QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QWidget#studio-view QPushButton {{
                border-radius: 8px;
            }}
            QWidget#studio-view QScrollArea,
            QWidget#studio-view QScrollArea > QWidget,
            QWidget#studio-view QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            QWidget#studio-view QCheckBox {{
                color: {t.TEXT};
                spacing: 8px;
            }}
            QWidget#studio-view QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 5px;
                background: #111820;
            }}
            QWidget#studio-view QCheckBox::indicator:checked {{
                background: {t.ACCENT};
                border-color: {t.ACCENT};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        topbar = QWidget()
        topbar.setObjectName("studio-topbar")
        topbar.setFixedHeight(64)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(16, 8, 16, 8)
        top.setSpacing(t.SPACE_3)

        left_panel = QWidget()
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_lay = QHBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(t.SPACE_3)
        brand_box = QVBoxLayout()
        brand_box.setContentsMargins(0, 0, 0, 0)
        brand_box.setSpacing(1)
        brand = QLabel("AI Lab Studio")
        brand.setObjectName("studio-brand")
        subbrand = QLabel("Runtime Workspace")
        subbrand.setObjectName("studio-subbrand")
        brand_box.addWidget(brand)
        brand_box.addWidget(subbrand)
        left_lay.addLayout(brand_box)
        self.instance_combo = QComboBox()
        self.instance_combo.setObjectName("studio-instance-picker")
        self.instance_combo.setMinimumWidth(230)
        self.instance_combo.setMaximumWidth(320)
        self.instance_combo.currentIndexChanged.connect(self._on_instance_selected)
        left_lay.addWidget(self.instance_combo)
        left_lay.addStretch()
        top.addWidget(left_panel, 1)

        self.model_picker = QComboBox()
        self.model_picker.setObjectName("studio-model-picker")
        self.model_picker.setMinimumWidth(420)
        self.model_picker.setMaximumWidth(620)
        self.model_picker.setIconSize(QSize(24, 24))
        self.model_picker.currentIndexChanged.connect(self._on_model_combo_changed)
        top.addWidget(self.model_picker, 0, Qt.AlignCenter)

        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_lay = QHBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(t.SPACE_2)
        right_lay.addStretch()

        self.launch_status = QLabel("Idle")
        self.launch_status.setObjectName("studio-status-pill")
        self._set_launch_status("Idle", "idle")
        right_lay.addWidget(self.launch_status)

        self.stop_btn = QPushButton("Eject")
        self.stop_btn.setProperty("variant", "secondary")
        self.stop_btn.setFixedWidth(92)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        right_lay.addWidget(self.stop_btn)
        top.addWidget(right_panel, 1)
        root.addWidget(topbar)
        
        self.layout_stack = QStackedWidget()
        root.addWidget(self.layout_stack, 1)

        # 1. Lock Screen
        self.lock_screen = LockScreen(
            title="Studio Workspace Locked",
            message="Selecting and connecting an instance via SSH is required to access the AI Lab Studio and interactive runtime."
        )
        self.lock_screen.instances_requested.connect(self.instances_requested.emit)
        self.layout_stack.addWidget(self.lock_screen)

        # 2. Main Workspace
        self.workspace_host = QWidget()
        self.workspace_lay = QVBoxLayout(self.workspace_host)
        self.workspace_lay.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {t.BORDER_LOW}; }}"
        )

        workspace = QWidget()
        workspace.setObjectName("studio-workspace")
        workspace.setStyleSheet(
            f"QWidget#studio-workspace {{ background: {t.BG_DEEP}; }}"
        )
        workspace_lay = QVBoxLayout(workspace)
        workspace_lay.setContentsMargins(0, 0, 0, 0)
        workspace_lay.setSpacing(0)

        self.banner = DiagnosticBanner()
        self.banner.fix_requested.connect(self.fix_requested.emit)
        workspace_lay.setSpacing(0)
        
        # Setup persistent profile for caching heavy assets (bundle.js, etc.)
        cache_path = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) + "/studio_cache"
        self.profile = QWebEngineProfile("studio_profile", self)
        self.profile.setPersistentStoragePath(cache_path)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)
        self.profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
        self.profile.setHttpCacheMaximumSize(100 * 1024 * 1024) 
        
        # Force dark background via script injection (runs before any CSS)
        dark_script = QWebEngineScript()
        dark_script.setSourceCode("""
            (function() {
                var css = 'html, body { background: #0a0a0b !important; color: #c7cedc !important; }';
                var style = document.createElement('style');
                style.type = 'text/css';
                style.id = 'force-dark-style';
                style.appendChild(document.createTextNode(css));
                
                function inject() {
                    var target = document.documentElement || document.head;
                    if (target && !document.getElementById('force-dark-style')) {
                        target.appendChild(style);
                        return true;
                    }
                    return false;
                }
                
                if (!inject()) {
                    var observer = new MutationObserver(function() {
                        if (inject()) observer.disconnect();
                    });
                    observer.observe(document, { childList: true, subtree: true });
                }
            })();
        """)
        dark_script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        dark_script.setWorldId(QWebEngineScript.MainWorld)
        dark_script.setRunsOnSubFrames(True)
        self.profile.scripts().insert(dark_script)
        
        self._ui_probe_timer = QTimer(self)
        self._ui_probe_timer.setInterval(600)
        self._ui_probe_timer.timeout.connect(self._run_ui_probe)
        
        # Track objects for explicit cleanup to avoid QtWebEngine profile warnings
        self._pages_to_cleanup = []
        
        self.webui = QWebEngineView()
        chat_page = QWebEnginePage(self.profile, self.webui)
        self.webui.setPage(chat_page) 
        self._pages_to_cleanup.append(chat_page)
        self.webui.page().setBackgroundColor(QColor("#0a0a0b"))
        self.webui.loadFinished.connect(self._on_webui_load_finished)
        self.webui.setHtml(_EMPTY_WEBUI_HTML)
        
        # Proper stacked widget for loading state
        self.webui_stack = QStackedWidget()
        self.webui_overlay = QWebEngineView()
        load_page = QWebEnginePage(self.profile, self.webui_overlay)
        self.webui_overlay.setPage(load_page)
        self._pages_to_cleanup.append(load_page)
        self.webui_overlay.page().setBackgroundColor(QColor("#0a0a0b"))
        self.webui_overlay.setHtml(_LOADING_WEBUI_HTML)
        
        self.webui_stack.addWidget(self.webui)         # Index 0
        self.webui_stack.addWidget(self.webui_overlay) # Index 1
        self.webui_stack.setCurrentIndex(0)
        
        workspace_lay.addWidget(self.webui_stack, 1)

        self.launch_log = LaunchLogPanel()
        self.launch_log.setVisible(False)
        workspace_lay.addWidget(self.launch_log)
        splitter.addWidget(workspace)

        side = QWidget()
        side.setObjectName("studio-settings")
        side.setMinimumWidth(340)
        side.setMaximumWidth(440)
        side.setStyleSheet(
            f"QWidget#studio-settings {{ background: {t.BG_BASE};"
            f" border-left: 1px solid {t.BORDER_LOW}; }}"
        )
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        side_lay.setSpacing(t.SPACE_3)

        settings_row = QHBoxLayout()
        title = QLabel("Settings")
        title.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 16px; font-weight: 700;"
        )
        settings_row.addWidget(title)
        settings_row.addStretch()
        self.models_count_label = QLabel("0 models")
        self.models_count_label.setProperty("role", "muted")
        settings_row.addWidget(self.models_count_label)
        side_lay.addLayout(settings_row)

        self.runtime_scope_label = QLabel("Pick an instance and a model to configure the runtime.")
        self.runtime_scope_label.setWordWrap(True)
        self.runtime_scope_label.setStyleSheet(
            f"color: {t.TEXT}; background: {t.SURFACE_1}; border: 1px solid {t.BORDER_LOW}; border-radius: 12px; padding: 12px; font-size: 12px;"
        )
        side_lay.addWidget(self.runtime_scope_label)

        self.launch_btn = QPushButton("Load Model")
        self.launch_btn.clicked.connect(self._on_launch)
        side_lay.addWidget(self.launch_btn)

        self.log_toggle_btn = QPushButton("Show Launch Log")
        self.log_toggle_btn.setProperty("variant", "ghost")
        self.log_toggle_btn.clicked.connect(self._toggle_launch_log)
        self._set_launch_log_visible(False)
        
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(1000) # Relaxed polling (1 second)
        self._retry_timer.timeout.connect(self._check_tunnel_and_load)
        self._target_local_port = 0
        self._retry_count = 0
        side_lay.addWidget(self.log_toggle_btn)

        hint = QLabel("Model configuration")
        hint.setProperty("role", "section")
        side_lay.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        form_host = QWidget()
        form_lay = QVBoxLayout(form_host)
        form_lay.setContentsMargins(0, 0, 0, 0)
        form_lay.setSpacing(0)
        self.params_form = ServerParamsForm([])
        self.params_form.set_model_field_visible(False)
        form_lay.addWidget(self.params_form)
        form_lay.addStretch()
        scroll.setWidget(form_host)
        side_lay.addWidget(scroll, 1)

        # Kept as a non-visual model registry for existing tests and signal
        # paths. The visible model picker lives in the top bar.
        self.model_list = QListWidget()
        self.model_list.currentItemChanged.connect(self._on_model_picked)
        self.model_list.hide()

        splitter.addWidget(side)
        splitter.setSizes([1120, 360])
        self.workspace_lay.addWidget(splitter)
        self.layout_stack.addWidget(self.workspace_host)

        self.store.instance_changed.connect(self._on_instance_changed)
        self.store.instance_state_updated.connect(lambda *_: self._update_lock_state())
        self._update_lock_state()

        store.instance_changed.connect(self._sync_sidebar_on_instance_change)
        store.remote_gguf_changed.connect(self._sync_models)

    def _update_lock_state(self):
        iid = self.store.selected_instance_id
        state = self.store.get_state(iid) if iid else None
        has_connection = state and state.setup.probed
        
        target_idx = 1 if has_connection else 0
        if self.layout_stack.currentIndex() != target_idx:
            self.layout_stack.setCurrentIndex(target_idx)

    def _on_instance_changed(self, iid: int):
        self._sync_sidebar_on_instance_change(iid)
        self._update_lock_state()

    def refresh_instances(self, ids: list[int]):
        # 1. Save current selection
        old_iid = self.instance_combo.currentData()

        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        for iid in ids:
            state = self.store.get_state(iid)
            tag = "" if state.gguf else " - no models"
            self.instance_combo.addItem(f"Instance #{iid}{tag}", iid)
        
        # 2. Restore selection
        if old_iid:
            idx = self.instance_combo.findData(old_iid)
            if idx >= 0:
                self.instance_combo.setCurrentIndex(idx)
            elif ids:
                self._on_instance_selected(0)
        elif ids:
            self._on_instance_selected(0)

        self.instance_combo.blockSignals(False)

    def _on_instance_selected(self, index: int):
        iid = self.instance_combo.itemData(index)
        if iid is None:
            return
        self.store.set_instance(iid)

    def _sync_sidebar_on_instance_change(self, iid: int):
        state = self.store.get_state(iid) if iid else None
        if state is None:
            self.runtime_scope_label.setText("Pick an instance and a model to configure the runtime.")
        else:
            self.runtime_scope_label.setText(
                f"Instance #{iid} selected. {len(state.gguf)} local model"
                + ("" if len(state.gguf) == 1 else "s")
                + " available for launch."
            )
        self._sync_models(state.gguf if state else [])

    def _sync_models(self, gguf):
        # 1. Save current selection
        old_path = self.model_picker.currentData()

        self.model_list.clear()
        self.model_picker.blockSignals(True)
        self.model_picker.clear()
        
        if not gguf:
            self.model_picker.addItem("Install a GGUF model first", None)
        else:
            for model in gguf:
                item = QListWidgetItem(model.filename)
                item.setData(Qt.UserRole, model.path)
                
                # Get brand icon
                icon = BrandManager.get_icon(model.filename)
                item.setIcon(icon)
                
                self.model_list.addItem(item)
                self.model_picker.addItem(icon, model.filename, model.path)
        
        self.model_picker.setEnabled(bool(gguf))
        self.launch_btn.setEnabled(bool(gguf))
        self.models_count_label.setText(
            f"{len(gguf)} model" if len(gguf) == 1 else f"{len(gguf)} models"
        )
        if not gguf:
            self.runtime_scope_label.setText(
                "No GGUF models are installed on this instance yet. Use the Model Store to download one, then come back here to launch it."
            )
        self.params_form.set_model_paths([model.path for model in gguf])
        
        # 2. Restore selection if possible, otherwise fallback to 0
        idx = self.model_picker.findData(old_path) if old_path else -1
        if idx >= 0:
            self.model_picker.setCurrentIndex(idx)
        elif gguf:
            self.model_picker.setCurrentIndex(0)
            self._set_selected_model(gguf[0].path)
        
        self.model_picker.blockSignals(False)

    def _on_model_picked(self, item, _previous):
        if item is None:
            return
        self._set_selected_model(item.data(Qt.UserRole))

    def _on_model_combo_changed(self, index: int):
        path = self.model_picker.itemData(index)
        if path:
            self._set_selected_model(path)

    def _set_selected_model(self, path: str):
        params = self.params_form.current_params()
        params.model_path = path
        self.params_form.set_params(params)
        name = path.rsplit("/", 1)[-1] if path else "No model selected"
        self.runtime_scope_label.setText(
            f"Runtime target: {name}. Review Settings below, then launch the local llama.cpp session."
        )
        model_index = self.model_picker.findData(path)
        if model_index >= 0 and self.model_picker.currentIndex() != model_index:
            self.model_picker.blockSignals(True)
            self.model_picker.setCurrentIndex(model_index)
            self.model_picker.blockSignals(False)

    def _on_launch(self):
        params: ServerParams = self.params_form.current_params()
        if not params.model_path:
            return
        self.banner.clear()
        self.launch_log.reset()
        self.launch_log.set_stage("start", "running")
        self._set_launch_status("Launching", "busy")
        self.stop_btn.setEnabled(True)
        self._set_launch_log_visible(True)
        self.launch_requested.emit(params)

    def open_webui(self, local_port: int):
        self._set_launch_status("Ready", "ready")
        self.stop_btn.setEnabled(True)
        self.webui_stack.setCurrentIndex(1) # Switch to loading layer
        self._target_local_port = local_port
        self._retry_count = 0
        self._retry_timer.start()
        # Don't setUrl yet, wait for timer to confirm port is open

    def _check_tunnel_and_load(self):
        from app.services.ssh_service import is_port_open
        self._retry_count += 1
        
        if is_port_open("127.0.0.1", self._target_local_port):
            self._retry_timer.stop()
            self.webui.setUrl(QUrl(f"http://127.0.0.1:{self._target_local_port}/"))
            # We don't hide the log yet, we wait for loadFinished signal!
        elif self._retry_count > 30: # 15 seconds timeout
            self._retry_timer.stop()
            self.mark_launch_failed()
            self.banner.error(f"Tunnel timed out on port {self._target_local_port}. Try manual reload.")

    def _on_webui_load_finished(self, ok: bool):
        if ok and not self._retry_timer.isActive() and self._target_local_port > 0:
            # Main HTML is here, start probing for the real UI elements (textarea)
            self._ui_probe_timer.start()

    def _run_ui_probe(self):
        # We look for a textarea or a specifically common llama.cpp ID
        js = "!!(document.querySelector('textarea') || document.querySelector('#input-chat'))"
        self.webui.page().runJavaScript(js, self._handle_probe_result)

    def _handle_probe_result(self, found: bool):
        if found:
            self._ui_probe_timer.stop()
            
            # Helper JS to "wake up" the textarea sizing (multi-pulse retry + force focus/click)
            js_fix = """
                (function() {
                    var count = 0;
                    var itv = setInterval(function() {
                        var ta = document.querySelector('textarea') || document.querySelector('#input-chat');
                        if (ta) {
                            ta.focus();
                            ta.click();
                            var val = ta.value || '';
                            ta.value = val + ' ';
                            ta.dispatchEvent(new Event('input', { bubbles: true }));
                            ta.value = val;
                            ta.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        if (++count > 4) clearInterval(itv);
                    }, 150);
                })();
            """
            self.webui.page().runJavaScript(js_fix)
            
            # Reveal only after the pulsations have likely finished
            def reveal():
                self.webui_stack.setCurrentIndex(0)
                self._set_launch_status("Ready", "ready")
                QTimer.singleShot(1000, lambda: self._set_launch_log_visible(False))
            
            QTimer.singleShot(800, reveal)

    def clear_webui(self):
        self._set_launch_status("Idle", "idle")
        self.stop_btn.setEnabled(False)
        self.webui.setHtml(_EMPTY_WEBUI_HTML)
        self._set_launch_log_visible(False)

    def mark_launch_failed(self):
        self._set_launch_status("Failed", "error")
        self.stop_btn.setEnabled(False)
        self.launch_log.set_stage("start", "failed")
        self.launch_log.set_stage("load", "failed")
        self._set_launch_log_visible(True)

    def append_launch_log(self, line: str):
        if not self.launch_log.isVisible():
            self._set_launch_log_visible(True)
        self.launch_log.append_log(line)
        lowered = line.lower()
        if "loading model" in lowered:
            self._set_launch_status("Loading", "busy")
            self.launch_log.set_stage("start", "done")
            self.launch_log.set_stage("load", "running")
        elif "server listening" in lowered or "http server listening" in lowered:
            self._set_launch_status("Ready", "ready")
            self.launch_log.set_stage("load", "done")
            self.launch_log.set_stage("ready", "done")

    def _toggle_launch_log(self):
        self._set_launch_log_visible(not self.launch_log.isVisible())

    def _set_launch_log_visible(self, visible: bool):
        self.launch_log.setVisible(visible)
        self.log_toggle_btn.setText("Hide Launch Log" if visible else "Show Launch Log")

    def _set_launch_status(self, text: str, level: str):
        if hasattr(self, "_last_status_level") and self._last_status_level == level and self.launch_status.text() == f"\u25CF  {text}":
            return
        self._last_status_level = level
        colors = {
            "idle": (t.TEXT_MID, "rgba(255,255,255,0.03)", "rgba(255,255,255,0.10)"),
            "busy": (t.WARN, "rgba(244,183,64,0.10)", "rgba(244,183,64,0.26)"),
            "ready": (t.OK, "rgba(59,212,136,0.10)", "rgba(59,212,136,0.26)"),
            "error": (t.ERR, "rgba(240,85,106,0.10)", "rgba(240,85,106,0.26)"),
        }
        fg, bg, border = colors.get(level, colors["idle"])
        self.launch_status.setText(f"\u25CF  {text}")
        self.launch_status.setStyleSheet(
            f"QLabel#studio-status-pill {{ color: {fg}; background: {bg};"
            f" border: 1px solid {border}; border-radius: 8px;"
            f" padding: 6px 10px; min-width: 76px; font-weight: 800; }}"
        )

    def closeEvent(self, event):
        """Explicit cleanup to prevent QtWebEngine profile release warnings."""
        if hasattr(self, "_ui_probe_timer"):
            self._ui_probe_timer.stop()
        
        # The order is critical: Pages must be destroyed before the Profile
        for page in self._pages_to_cleanup:
            # Setting page to None on the view or deleting the page
            try:
                page.setParent(None)
                page.deleteLater()
            except:
                pass
        
        self._pages_to_cleanup.clear()
        super().closeEvent(event)
