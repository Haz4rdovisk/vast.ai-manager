"""Studio view for loading an installed GGUF on a selected instance."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QUrl, QTimer, QStandardPaths, QEvent
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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
import qtawesome as qta

from app import theme as t
from app.lab.state.models import ServerParams
from app.ui.components.diagnostic_banner import DiagnosticBanner
from app.ui.components.server_params_form import ServerParamsForm
from app.ui.brand_manager import BrandManager
from app.ui.components.lock_screen import LockScreen
from app.ui.components.page_header import PageHeader
from app.ui.components.primitives import GlassCard
from app.ui.views.console_drawer import ConsoleDrawer
from PySide6.QtCore import QSize




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


class StudioView(QWidget):
    launch_requested = Signal(object)
    stop_requested = Signal()
    fix_requested = Signal(str)
    instances_requested = Signal()
    navigate_requested = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("studio-view")
        self.setStyleSheet(
            f"""
            QWidget#studio-view {{
                background: {t.BG_DEEP};
            }}
            /* Shared header-action chip geometry: 38px tall, 10px radius. */
            QComboBox#studio-instance-picker,
            QComboBox#studio-model-picker,
            QLabel#studio-status-pill,
            QPushButton#studio-eject-btn {{
                min-height: 38px;
                max-height: 38px;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
            }}
            QComboBox#studio-instance-picker {{
                background: {t.SURFACE_3};
                border: 1px solid {t.BORDER_MED};
                border-left: 3px solid rgba(255,255,255,0.18);
                color: {t.TEXT_HI};
                padding-left: 14px;
                padding-right: 30px;
            }}
            QComboBox#studio-instance-picker[connected="true"] {{
                border-left: 3px solid {t.OK};
            }}
            QComboBox#studio-instance-picker:hover {{
                background: #303a4f;
                border-color: {t.BORDER_HI};
            }}
            QComboBox#studio-model-picker {{
                background: {t.SURFACE_3};
                border: 1px solid {t.BORDER_MED};
                color: {t.TEXT_HI};
                padding-left: 14px;
                padding-right: 34px;
            }}
            QComboBox#studio-model-picker:hover {{
                background: #303a4f;
                border-color: rgba(179,160,255,0.44);
            }}
            QComboBox#studio-model-picker:focus {{
                background: #303a4f;
                border-color: rgba(179,160,255,0.52);
            }}
            QComboBox#studio-model-picker:disabled {{
                background: {t.SURFACE_3};
                border: 1px solid rgba(255,255,255,0.06);
                color: {t.TEXT_MID};
                font-weight: 600;
            }}
            QComboBox#studio-instance-picker::drop-down,
            QComboBox#studio-model-picker::drop-down {{
                border: none;
                width: 22px;
                subcontrol-position: right center;
                margin-right: 6px;
            }}
            QLabel#studio-status-pill {{
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.10);
                padding: 0 14px;
                min-width: 84px;
                qproperty-alignment: AlignCenter;
            }}
            QPushButton#studio-eject-btn {{
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.10);
                color: {t.TEXT_HI};
                padding: 0 18px;
            }}
            QPushButton#studio-eject-btn:hover:enabled {{
                background: rgba(240,85,106,0.10);
                border-color: rgba(240,85,106,0.45);
                color: {t.ERR};
            }}
            QPushButton#studio-eject-btn:disabled {{
                color: {t.TEXT_MID};
                background: rgba(255,255,255,0.02);
                border-color: rgba(255,255,255,0.06);
            }}
            QWidget#studio-view QComboBox,
            QWidget#studio-view QLineEdit,
            QWidget#studio-view QSpinBox,
            QWidget#studio-view QDoubleSpinBox {{
                background: {t.SURFACE_3};
                color: {t.TEXT_HI};
                border: 1px solid {t.BORDER_MED};
                border-radius: 12px;
                padding: 7px 14px;
                min-height: 34px;
            }}
            QWidget#studio-view QComboBox:focus,
            QWidget#studio-view QLineEdit:focus,
            QWidget#studio-view QSpinBox:focus,
            QWidget#studio-view QDoubleSpinBox:focus {{
                border-color: rgba(179,160,255,0.42);
                background: #303a4f;
            }}
            QWidget#studio-view QComboBox::drop-down {{
                border: none;
                width: 24px;
                margin-right: 4px;
            }}
            QWidget#studio-view QPushButton {{
                border-radius: 12px;
                min-height: 36px;
            }}
            QWidget#studio-settings {{
                background: transparent;
            }}
            QWidget#studio-view QFrame#SolidCard QScrollArea,
            QWidget#studio-view QFrame#SolidCard QScrollArea::viewport,
            QWidget#studio-view QFrame#SolidCard QScrollArea > QWidget,
            QWidget#studio-view QFrame#SolidCard QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
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
        root.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_3)

        header = PageHeader(
            "AI Lab Studio",
            "Runtime workspace for selecting instances and launching local models.",
        )

        self.instance_combo = QComboBox()
        self.instance_combo.setObjectName("studio-instance-picker")
        self.instance_combo.setMinimumWidth(260)
        self.instance_combo.setMaximumWidth(320)
        self.instance_combo.setToolTip("Active instance")
        self.instance_combo.setPlaceholderText("No rented instances")
        self.instance_combo.currentIndexChanged.connect(self._on_instance_selected)

        self.model_picker = QComboBox()
        self.model_picker.setObjectName("studio-model-picker")
        self.model_picker.setMinimumWidth(320)
        self.model_picker.setMaximumWidth(460)
        self.model_picker.setIconSize(QSize(20, 20))
        self.model_picker.setToolTip("Loaded GGUF model")
        self.model_picker.currentIndexChanged.connect(self._on_model_combo_changed)

        self.launch_status = QLabel("Idle")
        self.launch_status.setObjectName("studio-status-pill")
        self._set_launch_status("Idle", "idle")
        header.add_action(self.launch_status)

        self.stop_btn = QPushButton("Eject")
        self.stop_btn.setObjectName("studio-eject-btn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        header.add_action(self.stop_btn)

        root.addWidget(header)
        
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
            "QSplitter::handle { background: transparent; }"
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

        # Proper stacked widget for empty / loading / live states
        self.webui_stack = QStackedWidget()
        self.webui_overlay = QWebEngineView()
        load_page = QWebEnginePage(self.profile, self.webui_overlay)
        self.webui_overlay.setPage(load_page)
        self._pages_to_cleanup.append(load_page)
        self.webui_overlay.page().setBackgroundColor(QColor("#0a0a0b"))
        self.webui_overlay.setHtml(_LOADING_WEBUI_HTML)

        self.webui_empty = self._build_empty_state()

        self.webui_stack.addWidget(self.webui)         # Index 0 — live chat
        self.webui_stack.addWidget(self.webui_overlay) # Index 1 — loading
        self.webui_stack.addWidget(self.webui_empty)   # Index 2 — empty CTA
        self.webui_stack.setCurrentWidget(self.webui_empty)
        
        workspace_lay.addWidget(self.webui_stack, 1)

        self._workspace_surface = workspace
        self._workspace_surface.installEventFilter(self)
        self.launch_log = ConsoleDrawer(self._workspace_surface)
        self.launch_log.set_placeholder_text("Waiting for llama-server output...")
        self.launch_log.expanded_changed.connect(self._position_launch_log_drawer)
        self.launch_log.set_expanded(False)
        self.launch_log.raise_()
        QTimer.singleShot(0, self._position_launch_log_drawer)
        splitter.addWidget(workspace)

        side = QWidget()
        side.setObjectName("studio-settings")
        side.setMinimumWidth(356)
        side.setMaximumWidth(456)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(t.SPACE_2, t.SPACE_3, t.SPACE_2, t.SPACE_3)
        side_lay.setSpacing(0)

        side_card = GlassCard()
        side_lay.addWidget(side_card, 1)

        card_lay = side_card.body()
        card_lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        card_lay.setSpacing(t.SPACE_4)

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
        card_lay.addLayout(settings_row)

        picker_label_style = (
            f"color: {t.TEXT_LOW}; font-size: 11px; font-weight: 700;"
            f" letter-spacing: 0.6px; text-transform: uppercase;"
        )

        instance_label = QLabel("Instance")
        instance_label.setStyleSheet(picker_label_style)
        card_lay.addWidget(instance_label)
        self.instance_combo.setMaximumWidth(16777215)
        card_lay.addWidget(self.instance_combo)

        model_label = QLabel("Model")
        model_label.setStyleSheet(picker_label_style)
        card_lay.addWidget(model_label)
        self.model_picker.setMaximumWidth(16777215)
        card_lay.addWidget(self.model_picker)

        self.launch_btn = QPushButton("Load Model")
        self.launch_btn.clicked.connect(self._on_launch)
        card_lay.addWidget(self.launch_btn)
        
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(1000) # Relaxed polling (1 second)
        self._retry_timer.timeout.connect(self._check_tunnel_and_load)
        self._target_local_port = 0
        self._retry_count = 0

        hint = QLabel("Model configuration")
        hint.setProperty("role", "section")
        card_lay.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        form_host = QWidget()
        form_lay = QVBoxLayout(form_host)
        form_lay.setContentsMargins(0, 0, t.SPACE_3, 0)
        form_lay.setSpacing(t.SPACE_2)
        self.params_form = ServerParamsForm([])
        self.params_form.set_model_field_visible(False)
        form_lay.addWidget(self.params_form)
        form_lay.addStretch()
        scroll.setWidget(form_host)
        card_lay.addWidget(scroll, 1)

        # Kept as a non-visual model registry for existing tests and signal
        # paths. The visible model picker lives in the top bar.
        self.model_list = QListWidget()
        self.model_list.currentItemChanged.connect(self._on_model_picked)
        self.model_list.hide()

        splitter.addWidget(side)
        splitter.setSizes([1100, 400])
        splitter.splitterMoved.connect(lambda *_: QTimer.singleShot(0, self._position_launch_log_drawer))
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
        if not ids:
            self.instance_combo.setCurrentIndex(-1)
        elif old_iid:
            idx = self.instance_combo.findData(old_iid)
            if idx >= 0:
                self.instance_combo.setCurrentIndex(idx)
            else:
                self._on_instance_selected(0)
        else:
            self._on_instance_selected(0)

        self.instance_combo.blockSignals(False)

    def _on_instance_selected(self, index: int):
        iid = self.instance_combo.itemData(index)
        if iid is None:
            self._refresh_instance_chip_accent(None)
            return
        self.store.set_instance(iid)
        self._refresh_instance_chip_accent(iid)

    def _refresh_instance_chip_accent(self, iid):
        state = self.store.get_state(iid) if iid else None
        connected = bool(state and getattr(state.setup, "probed", False))
        self.instance_combo.setProperty("connected", "true" if connected else "false")
        self.instance_combo.style().unpolish(self.instance_combo)
        self.instance_combo.style().polish(self.instance_combo)

    def _sync_sidebar_on_instance_change(self, iid: int):
        state = self.store.get_state(iid) if iid else None
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
        self.launch_log.clear()
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

    def _build_empty_state(self) -> QWidget:
        """Centered empty placeholder with a CTA to Model Store."""
        wrap = QWidget()
        wrap.setObjectName("studio-empty-state")
        wrap.setStyleSheet(
            f"QWidget#studio-empty-state {{ background: {t.BG_DEEP}; }}"
            f" QLabel#studio-empty-title {{ color: {t.TEXT_HI};"
            f" font-size: 22px; font-weight: 800; }}"
            f" QLabel#studio-empty-desc {{ color: {t.TEXT_MID};"
            f" font-size: 14px; }}"
            f" QLabel#studio-empty-icon {{ background: transparent; }}"
            f" QPushButton#studio-empty-cta {{"
            f" min-width: 220px; max-width: 220px;"
            f" min-height: 44px; max-height: 44px;"
            f" border-radius: 12px; font-size: 14px;"
            f" font-weight: 700; padding: 0; }}"
        )

        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.addStretch(1)

        icon = QLabel()
        icon.setObjectName("studio-empty-icon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(56, 56)
        icon.setPixmap(self._build_empty_state_icon())
        outer.addWidget(icon, 0, Qt.AlignCenter)

        outer.addSpacing(18)

        title = QLabel("No Model Loaded")
        title.setObjectName("studio-empty-title")
        title.setAlignment(Qt.AlignCenter)
        outer.addWidget(title, 0, Qt.AlignCenter)

        outer.addSpacing(10)

        desc = QLabel(
            "Browse the Model Store to download a GGUF model onto this instance,\n"
            "then come back here and load it to start a chat session."
        )
        desc.setObjectName("studio-empty-desc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setMaximumWidth(560)
        outer.addWidget(desc, 0, Qt.AlignCenter)

        outer.addSpacing(22)

        cta = QPushButton("Open Model Store")
        cta.setObjectName("studio-empty-cta")
        cta.setCursor(Qt.PointingHandCursor)
        cta.setFixedSize(220, 44)
        cta.clicked.connect(lambda: self.navigate_requested.emit("discover"))
        outer.addWidget(cta, 0, Qt.AlignCenter)

        outer.addStretch(1)
        return wrap

    def _build_empty_state_icon(self) -> QPixmap:
        try:
            return qta.icon("mdi.cube-outline", color=t.ACCENT_SOFT).pixmap(48, 48)
        except Exception:
            fallback = QPixmap(48, 48)
            fallback.fill(Qt.transparent)
            return fallback

    def clear_webui(self):
        self._set_launch_status("Idle", "idle")
        self.stop_btn.setEnabled(False)
        self.webui_stack.setCurrentWidget(self.webui_empty)
        self._set_launch_log_visible(False)

    def mark_launch_failed(self):
        self._set_launch_status("Failed", "error")
        self.stop_btn.setEnabled(False)
        self._set_launch_log_visible(True)

    def append_launch_log(self, line: str):
        if not self.launch_log.is_expanded():
            self._set_launch_log_visible(True)
        self.launch_log.log(line)
        lowered = line.lower()
        if "loading model" in lowered:
            self._set_launch_status("Loading", "busy")
        elif "server listening" in lowered or "http server listening" in lowered:
            self._set_launch_status("Ready", "ready")

    def _toggle_launch_log(self):
        self._set_launch_log_visible(not self.launch_log.is_expanded())

    def _set_launch_log_visible(self, visible: bool):
        self.launch_log.set_expanded(visible)
        self._position_launch_log_drawer()

    def _position_launch_log_drawer(self, *_args) -> None:
        if not hasattr(self, "launch_log") or not hasattr(self, "_workspace_surface"):
            return
        margin_x = t.SPACE_4
        margin_bottom = t.SPACE_2
        width = max(240, self._workspace_surface.width() - (margin_x * 2))
        height = self.launch_log.height() or self.launch_log.sizeHint().height()
        y = max(0, self._workspace_surface.height() - height - margin_bottom)
        self.launch_log.setGeometry(margin_x, y, width, height)
        self.launch_log.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_launch_log_drawer()

    def eventFilter(self, watched, event):
        if watched is getattr(self, "_workspace_surface", None) and event.type() in (
            QEvent.Resize,
            QEvent.Show,
            QEvent.Move,
        ):
            QTimer.singleShot(0, self._position_launch_log_drawer)
        return super().eventFilter(watched, event)

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
            f" border: 1px solid {border}; }}"
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
