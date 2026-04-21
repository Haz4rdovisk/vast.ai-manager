"""Right-side install panel embedded in DiscoverView."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QPlainTextEdit,
)

from app import theme as t
from app.lab.services.fit_scorer import InstanceFitScorer
from app.lab.services.huggingface import HFModel, HFModelFile
from app.lab.services.model_catalog import CatalogEntry
from app.lab.workers.huggingface_worker import HFModelDetailWorker
from app.ui.components.install_progress import InstallProgress
from app.ui.components.primitives import Badge, GlassCard, StatusPill


_FIT_LEVEL = {"perfect": "ok", "good": "info", "marginal": "warn", "too_tight": "err", "pending": "muted"}
_FIT_LABEL = {
    "perfect": "Perfect Fit",
    "good": "Good Fit",
    "marginal": "Tight Fit",
    "too_tight": "Too Large",
    "pending": "Analyzing...",
}


class _InstanceCard(QFrame):
    """Integrated instance card with expanding sections (Confirm/Progress).
    Keeps hardware info always visible while stretching down for actions."""
    
    confirmed = Signal(str, int)  # mode, iid
    setup_requested = Signal(int)
    reset_requested = Signal(int)
    deploy_requested = Signal(int)
    cancel_confirm_requested = Signal()
    
    def __init__(self, iid: int, parent=None):
        super().__init__(parent)
        self.iid = iid
        self.setObjectName("deploy-target")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(120)
        
        self._root_lay = QVBoxLayout(self)
        self._root_lay.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        self._root_lay.setSpacing(t.SPACE_2)
        
        # 1. Header (Always Visible)
        # -------------------------
        header = QHBoxLayout()
        self._head_lbl = QLabel(f"Instance #{iid}")
        self._head_lbl.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
        header.addWidget(self._head_lbl)
        header.addStretch()
        self._vram_badge = Badge("0 GB VRAM")
        header.addWidget(self._vram_badge)
        self._root_lay.addLayout(header)

        self._gpu_lbl = QLabel("Unknown GPU")
        self._gpu_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 11px; font-weight: 500;")
        self._root_lay.addWidget(self._gpu_lbl)

        self._fit_pill = StatusPill("Calculating...", "muted")
        self._root_lay.addWidget(self._fit_pill)

        # 2. Progress Strip (Visible during jobs)
        # ---------------------------------------
        self._prog_widget = QWidget()
        prog_lay = QVBoxLayout(self._prog_widget)
        prog_lay.setContentsMargins(0, t.SPACE_2, 0, t.SPACE_1)
        prog_lay.setSpacing(t.SPACE_1)
        
        self._prog_status = QLabel("INITIALIZING...")
        self._prog_status.setStyleSheet(f"color: {t.ACCENT}; font-size: 9px; font-weight: 800; letter-spacing: 1px;")
        prog_lay.addWidget(self._prog_status)
        
        self._prog_bar = QProgressBar()
        self._prog_bar.setFixedHeight(4)
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setTextVisible(False)
        self._prog_bar.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255,255,255,0.05); border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t.ACCENT}, stop:1 {t.ACCENT_HI}); border-radius: 2px; }}
        """)
        prog_lay.addWidget(self._prog_bar)
        
        # Log Toggle & Content
        log_row = QHBoxLayout()
        log_row.setContentsMargins(0, 4, 0, 0)
        self._log_toggle = QPushButton("> Show Install Log")
        self._log_toggle.setCursor(Qt.PointingHandCursor)
        self._log_toggle.setStyleSheet("QPushButton { border: none; background: transparent; color: #888; text-align: left; font-size: 10px; font-weight: 600; } QPushButton:hover { color: #ccc; }")
        self._log_toggle.clicked.connect(self.toggle_log)
        log_row.addWidget(self._log_toggle)
        log_row.addStretch()
        
        self._prog_dismiss = QPushButton("Clear & Retry")
        self._prog_dismiss.setProperty("size", "sm")
        self._prog_dismiss.setStyleSheet(f"background: {t.SURFACE_3}; color: {t.TEXT}; font-size: 10px; padding: 2px 8px; border-radius: 4px; border: 1px solid {t.BORDER_LOW};")
        self._prog_dismiss.setCursor(Qt.PointingHandCursor)
        self._prog_dismiss.clicked.connect(self.show_idle)
        self._prog_dismiss.hide()
        log_row.addWidget(self._prog_dismiss)
        
        prog_lay.addLayout(log_row)
        
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setUndoRedoEnabled(False)
        self._log_view.setMaximumBlockCount(100)
        self._log_view.setFixedHeight(120)
        self._log_view.hide()
        self._log_view.setStyleSheet(f"background: {t.BG_VOID}; color: {t.TEXT_MID}; font-family: {t.FONT_MONO}; font-size: 9px; border: 1px solid {t.BORDER_LOW}; border-radius: 4px;")
        prog_lay.addWidget(self._log_view)

        self._prog_widget.hide()
        self._root_lay.addWidget(self._prog_widget)

        # 3. Confirm Section (Expands for confirmation)
        # ---------------------------------------------
        self._confirm_widget = QWidget()
        self._confirm_widget.setObjectName("confirm-section")
        self._confirm_widget.setStyleSheet(f"QWidget#confirm-section {{ border-top: 1px solid {t.BORDER_LOW}; margin-top: 4px; padding-top: 4px; }}")
        conf_lay = QVBoxLayout(self._confirm_widget)
        conf_lay.setContentsMargins(0, t.SPACE_2, 0, 0)
        conf_lay.setSpacing(t.SPACE_2)
        
        review_head = QLabel("REVIEW ACTION")
        review_head.setProperty("role", "section")
        review_head.setStyleSheet("font-size: 10px;")
        conf_lay.addWidget(review_head)
        
        self._summary_box = QWidget()
        summary_lay = QHBoxLayout(self._summary_box)
        summary_lay.setContentsMargins(0, 0, 0, 0)
        summary_lay.setSpacing(t.SPACE_3)
        
        accent_line = QFrame()
        accent_line.setFixedWidth(2)
        accent_line.setStyleSheet(f"background: {t.ACCENT}; border-radius: 1px;")
        summary_lay.addWidget(accent_line)
        
        self._summary_lbl = QLabel("")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet(f"color: {t.TEXT}; font-size: 11px; line-height: 1.25;")
        summary_lay.addWidget(self._summary_lbl, 1)
        conf_lay.addWidget(self._summary_box)
        
        conf_btns = QHBoxLayout()
        conf_btns.setSpacing(t.SPACE_2)
        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setFixedWidth(85)
        self._btn_cancel.setProperty("size", "sm")
        self._btn_cancel.clicked.connect(self.show_idle)
        
        self._btn_confirm = QPushButton("Confirm")
        self._btn_confirm.setProperty("role", "primary")
        self._btn_confirm.setProperty("size", "sm")
        self._btn_confirm.clicked.connect(lambda: self.confirmed.emit(getattr(self, "_active_mode", "deploy"), self.iid))
        
        conf_btns.addStretch()
        conf_btns.addWidget(self._btn_cancel)
        conf_btns.addWidget(self._btn_confirm)
        conf_lay.addLayout(conf_btns)
        
        self._confirm_widget.hide()
        self._root_lay.addWidget(self._confirm_widget)

        # 4. Action Buttons (Standard visible state)
        # ------------------------------------------
        self._action_widget = QWidget()
        act_lay = QHBoxLayout(self._action_widget)
        act_lay.setContentsMargins(0, t.SPACE_2, 0, 0)
        act_lay.setSpacing(t.SPACE_2)
        
        self._btn_setup = QPushButton("Setup Environment")
        self._btn_setup.setProperty("role", "primary")
        self._btn_setup.setProperty("size", "sm")
        self._btn_setup.clicked.connect(lambda: self.setup_requested.emit(self.iid))
        
        self._btn_ready = QPushButton("Ready")
        self._btn_ready.setEnabled(False)
        self._btn_ready.setProperty("size", "sm")
        
        self._btn_reset = QPushButton("Reset")
        self._btn_reset.setProperty("role", "danger")
        self._btn_reset.setProperty("size", "sm")
        self._btn_reset.setFixedWidth(60)
        self._btn_reset.clicked.connect(lambda: self.reset_requested.emit(self.iid))
        
        self._btn_deploy = QPushButton("Deploy Model")
        self._btn_deploy.setProperty("role", "primary")
        self._btn_deploy.setProperty("size", "sm")
        self._btn_deploy.clicked.connect(lambda: self.deploy_requested.emit(self.iid))
        
        act_lay.addWidget(self._btn_setup, 1)
        act_lay.addWidget(self._btn_ready, 1)
        act_lay.addWidget(self._btn_reset)
        act_lay.addWidget(self._btn_deploy, 1)
        self._root_lay.addWidget(self._action_widget)

        self._busy_lbl = QLabel("")
        self._busy_lbl.setWordWrap(True)
        self._busy_lbl.setStyleSheet(f"color: {t.WARN}; font-size: 11px; font-weight: 600; margin-top: 4px;")
        self._busy_lbl.hide()
        self._root_lay.addWidget(self._busy_lbl)

    def show_idle(self):
        self._confirm_widget.hide()
        self._prog_widget.hide()
        self._action_widget.show()
        self._prog_dismiss.hide()
        self._update_height()

    def show_confirm(self, mode: str, summary: str):
        self._summary_lbl.setText(summary)
        # Store mode in property for the connected signal
        self._active_mode = mode
        self._btn_confirm.setProperty("role", "primary" if mode != "wipe" else "danger")
        self._btn_confirm.style().unpolish(self._btn_confirm)
        self._btn_confirm.style().polish(self._btn_confirm)
        
        self._action_widget.hide()
        self._prog_widget.hide()
        self._confirm_widget.show()
        self._update_height()

    def show_progress(self, stage: str, percent: int):
        self._prog_dismiss.hide()
        self._prog_status.setText(f"{stage.upper()}... {percent}%")
        self._prog_status.setStyleSheet(f"color: {t.ACCENT}; font-size: 9px; font-weight: 800; letter-spacing: 1px;")
        self._prog_bar.setStyleSheet(f"QProgressBar {{ background: rgba(255,255,255,0.05); border: none; border-radius: 2px; }} QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t.ACCENT}, stop:1 {t.ACCENT_HI}); border-radius: 2px; }}")
        self._prog_bar.setValue(percent)
        
        if not self._prog_widget.isVisible():
            self._confirm_widget.hide()
            self._action_widget.hide()
            self._prog_widget.show()
            self._update_height()

    def show_failed(self, error_msg: str):
        self._prog_dismiss.show()
        self._prog_status.setText(f"FAILED: {error_msg}")
        self._prog_status.setStyleSheet(f"color: {t.ERR}; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        self._prog_bar.setStyleSheet(f"QProgressBar {{ background: rgba(255,255,255,0.05); border: none; border-radius: 2px; }} QProgressBar::chunk {{ background: {t.ERR}; border-radius: 2px; }}")
        self._prog_bar.setValue(100)
        
        if not self._prog_widget.isVisible():
            self._confirm_widget.hide()
            self._action_widget.hide()
            self._prog_widget.show()
            self._update_height()
        
        if not self._log_view.isVisible():
            self.toggle_log()

    def toggle_log(self):
        visible = not self._log_view.isVisible()
        self._log_view.setVisible(visible)
        self._log_toggle.setText(("> " if not visible else "v ") + "Show Install Log")
        self._update_height()

    def append_log(self, text: str):
        self._log_view.appendPlainText(text.rstrip())

    def _update_height(self):
        if self._confirm_widget.isVisible(): self.setMinimumHeight(180)
        elif self._prog_widget.isVisible():
            h = 240 if self._log_view.isVisible() else 125
            self.setMinimumHeight(h)
        else: self.setMinimumHeight(120)

    def populate_info(self, iid, state, selected_file, busy: bool, active_job, scorer):
        self._vram_badge.setText(f"{(state.system.gpu_vram_gb or 0):.0f} GB VRAM")
        self._gpu_lbl.setText(state.system.gpu_name or "Unknown GPU")

        if selected_file is not None:
            size_gb = selected_file.size_bytes / (1024 ** 3) if selected_file.size_bytes else 0
            # Simple scoring without complex CatalogEntry dependencies if possible, or just use what we have
            from app.lab.services.model_catalog import CatalogEntry
            entry = CatalogEntry(
                name="Temp",
                provider="Temp",
                params_b=0.0,
                best_quant=selected_file.quantization or "Unknown",
                memory_required_gb=size_gb + 0.5 if size_gb else 5.0,
                estimated_tps_7b=0.0,
                gguf_sources=[],
            )
            scored = scorer.score(entry, state.system)
            self._fit_pill.set_status(
                f"{scored.score:.0f} score | {_FIT_LABEL.get(scored.fit_level, 'Unknown Fit')}",
                _FIT_LEVEL.get(scored.fit_level, "info"),
            )
            self._fit_pill.show()
        else:
            self._fit_pill.hide()

        if busy and active_job:
            status_text = f"Busy with {active_job.filename or active_job.stage}"
            if self._busy_lbl.text() != status_text:
                self._busy_lbl.setText(status_text)
                self._busy_lbl.show()
                self._action_widget.hide()
                self._confirm_widget.hide()
        else:
            self._busy_lbl.hide()
            has_setup = state.setup.llamacpp_installed
            
            # Avoid redundant setVisible calls which can trigger layout flickers
            if self._btn_setup.isVisible() == has_setup:
                self._btn_setup.setVisible(not has_setup)
            if self._btn_ready.isVisible() != has_setup:
                self._btn_ready.setVisible(has_setup)
            if self._btn_reset.isVisible() != has_setup:
                self._btn_reset.setVisible(has_setup)
                
            can_deploy = has_setup and selected_file is not None
            if self._btn_deploy.isEnabled() != can_deploy:
                self._btn_deploy.setEnabled(can_deploy)
            
            if not busy and not self._confirm_widget.isVisible() and not self._prog_widget.isVisible():
                if not self._action_widget.isVisible():
                    self._action_widget.show()


class InstallPanelSide(QWidget):
    install_requested = Signal(int, str, str)
    setup_requested = Signal(int)
    wipe_requested = Signal(int)
    cancel_requested = Signal(str)
    resume_requested = Signal(str)
    discard_requested = Signal(str)
    close_requested = Signal()

    MODE_IDLE = "idle"
    MODE_READY = "ready"
    MODE_BUSY = "busy"

    def __init__(self, store, job_registry, parent=None):
        super().__init__(parent)
        self.store = store
        self.registry = job_registry
        self.scorer = InstanceFitScorer()
        self.current_model: HFModel | None = None
        self.mode = self.MODE_IDLE
        self._instance_cards: dict[int, _InstanceCard] = {}
        self._stale_desc = None

        self.setMinimumWidth(340)
        self.setMaximumWidth(440)
        self.setObjectName("studio-settings")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"""
            QWidget#studio-settings {{
                background: {t.BG_BASE};
                border-left: 1px solid {t.BORDER_LOW};
            }}
            QWidget#studio-settings QScrollArea,
            QWidget#studio-settings QScrollArea::viewport,
            QWidget#studio-settings QScrollArea > QWidget,
            QWidget#studio-settings QScrollArea > QWidget > QWidget {{
                background: {t.BG_BASE};
                border: none;
            }}
            QFrame#deploy-target {{
                background: {t.SURFACE_1};
                border: 1px solid {t.BORDER_MED};
                border-radius: 12px;
            }}
            QFrame#deploy-target:hover {{
                border-color: {t.ACCENT};
            }}
            QComboBox {{
                background: {t.SURFACE_3};
                color: {t.TEXT_HI};
                border: 1px solid {t.BORDER_MED};
                border-radius: 8px;
                padding: 6px 12px;
                min-height: 28px;
            }}
            QComboBox:focus {{ border-color: {t.ACCENT}; }}
            QLabel#deploy-model-name {{
                color: {t.TEXT_HI};
                font-size: 16px;
                font-weight: 800;
            }}
            QLabel#deploy-model-meta {{
                color: {t.TEXT_MID};
                font-size: 12px;
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        header = QHBoxLayout()
        title = QLabel("Settings")
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch()
        self._panel_meta = QLabel("0 models")
        self._panel_meta.setProperty("role", "muted")
        header.addWidget(self._panel_meta)
        root.addLayout(header)

        self._stale_banner = QFrame()
        self._stale_banner.setObjectName("stale-install-banner")
        stale_lay = QHBoxLayout(self._stale_banner)
        stale_lay.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        stale_lay.setSpacing(t.SPACE_2)
        self._stale_label = QLabel("")
        self._stale_label.setWordWrap(True)
        self._stale_label.setStyleSheet(f"color: {t.WARN}; font-size: 12px;")
        stale_lay.addWidget(self._stale_label, 1)
        resume = QPushButton("Resume")
        resume.setProperty("size", "sm")
        resume.clicked.connect(self._on_stale_resume)
        stale_lay.addWidget(resume)
        discard = QPushButton("Discard")
        discard.setProperty("variant", "ghost")
        discard.setProperty("size", "sm")
        discard.clicked.connect(self._on_stale_discard)
        stale_lay.addWidget(discard)
        self._stale_banner.hide()
        root.addWidget(self._stale_banner)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self._idle = self._build_idle()
        self._ready = self._build_ready()
        self._busy = self._build_busy()
        self.stack.addWidget(self._idle)
        self.stack.addWidget(self._ready)
        self.stack.addWidget(self._busy)

        self.registry.job_started.connect(lambda _key: self._refresh())
        self.registry.job_updated.connect(self._on_registry_update)
        self.registry.job_finished.connect(self._on_registry_finished)
        self.store.instance_state_updated.connect(lambda *_: self._refresh())
        self._set_mode(self.MODE_IDLE)

    def set_model(self, model: HFModel) -> None:
        self.current_model = model
        has_zeros = any(f.size_bytes == 0 for f in model.files) if model.files else True
        if has_zeros:
            self._fetch_model_details(model.id)
        self._refresh()

    def _fetch_model_details(self, model_id: str) -> None:
        self._detail_worker = HFModelDetailWorker(model_id, self)
        self._detail_worker.finished.connect(self._on_detail_finished)
        self._detail_worker.start()

    def _on_detail_finished(self, files: list[HFModelFile]) -> None:
        if self.current_model and files:
            self.current_model.files = files
            self._populate_quants()
            self._render_instance_cards()

    def clear(self) -> None:
        self.current_model = None
        self._set_mode(self.MODE_IDLE)

    def show_stale(self, desc, state: dict) -> None:
        pct = state.get("percent", desc.percent) or 0
        stage = state.get("stage", desc.stage) or "unknown"
        self._stale_label.setText(f"{desc.filename} on #{desc.iid} stopped at {stage} ({pct}%).")
        self._stale_desc = desc
        self._stale_banner.show()

    def _build_idle(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, t.SPACE_8, 0, 0)
        lay.setSpacing(t.SPACE_2)
        title = QLabel("No model selected")
        title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 15px; font-weight: 700;")
        msg = QLabel("Pick a GGUF from the store to choose a quantization and target instance.")
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 13px;")
        lay.addWidget(title)
        lay.addWidget(msg)
        lay.addStretch()
        return widget

    def _build_ready(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_4)

        sec_model = QLabel("Selected Model")
        sec_model.setProperty("role", "section")
        lay.addWidget(sec_model)

        self._hero_name = QLabel("")
        self._hero_name.setObjectName("deploy-model-name")
        self._hero_name.setWordWrap(True)
        self._hero_author = QLabel("")
        self._hero_author.setObjectName("deploy-model-meta")
        self._hero_stats = QLabel("")
        self._hero_stats.setObjectName("deploy-model-meta")
        lay.addWidget(self._hero_name)
        lay.addWidget(self._hero_author)
        lay.addWidget(self._hero_stats)

        sec_quant = QLabel("Target configuration")
        sec_quant.setProperty("role", "section")
        lay.addWidget(sec_quant)
        self._quant_combo = QComboBox()
        self._quant_combo.currentIndexChanged.connect(lambda _: self._render_instance_cards())
        lay.addWidget(self._quant_combo)

        sec_targets = QLabel("Deployment targets")
        sec_targets.setProperty("role", "section")
        lay.addWidget(sec_targets)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._instance_host = QWidget()
        self._instance_host.setAttribute(Qt.WA_StyledBackground, True)
        self._instance_lay = QVBoxLayout(self._instance_host)
        self._instance_lay.setContentsMargins(0, 0, 0, 0)
        self._instance_lay.setSpacing(t.SPACE_3)
        self._instance_lay.addStretch(1)
        scroll.setWidget(self._instance_host)
        lay.addWidget(scroll, 1)

        return widget

    def _build_busy(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_4)

        section = QLabel("Operations Hub")
        section.setProperty("role", "section")
        lay.addWidget(section)

        self._busy_title = QLabel("")
        self._busy_title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 15px; font-weight: 700;")
        lay.addWidget(self._busy_title)
        self._progress = InstallProgress()
        lay.addWidget(self._progress)

        self._cancel_btn = QPushButton("Abort Process")
        self._cancel_btn.setProperty("variant", "ghost")
        self._cancel_btn.clicked.connect(self._show_cancel_confirm)
        lay.addWidget(self._cancel_btn)

        self._cancel_strip = QFrame()
        self._cancel_strip.setStyleSheet(f"background: {t.SURFACE_2}; border: 1px solid {t.BORDER_LOW}; border-radius: 8px;")
        strip_lay = QHBoxLayout(self._cancel_strip)
        strip_lay.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        strip_lay.addWidget(QLabel("Terminate remote job?"))
        strip_lay.addStretch()
        no = QPushButton("No")
        no.setProperty("size", "sm")
        no.clicked.connect(self._cancel_strip.hide)
        strip_lay.addWidget(no)
        self._cancel_confirm_yes = QPushButton("Terminate")
        self._cancel_confirm_yes.setProperty("variant", "danger")
        self._cancel_confirm_yes.setProperty("size", "sm")
        self._cancel_confirm_yes.clicked.connect(self._emit_cancel)
        strip_lay.addWidget(self._cancel_confirm_yes)
        self._cancel_strip.hide()
        lay.addWidget(self._cancel_strip)
        lay.addStretch()
        return widget

    def _refresh(self) -> None:
        if self.current_model is None:
            self._set_mode(self.MODE_IDLE)
            return
        active = self._current_active_job()
        if active is not None:
            self._busy_title.setText(f"Active Job on #{active.iid}")
            self._progress.set_stage(active.stage, percent=active.percent)
            self._set_mode(self.MODE_BUSY)
            return
        self._populate_hero()
        self._populate_quants()
        self._render_instance_cards()
        self._set_mode(self.MODE_READY)

    def _populate_hero(self) -> None:
        if not self.current_model: return
        m = self.current_model
        self._hero_name.setText(m.name)
        self._hero_author.setText(f"by {m.author}")
        params = f" | {m.params_b:.1f}B" if m.params_b > 0 else ""
        self._hero_stats.setText(f"{m.likes:,} likes | {m.downloads:,} downloads{params}")

    def _populate_quants(self) -> None:
        if not self.current_model: return
        curr = self._quant_combo.currentData()
        self._quant_combo.blockSignals(True)
        self._quant_combo.clear()
        files = sorted(self.current_model.files, key=lambda i: i.size_bytes)
        default_idx = 0
        for idx, item in enumerate(files):
            size_gb = item.size_bytes / (1024 ** 3) if item.size_bytes else 0
            label = f"{item.quantization or 'Unknown'} ({size_gb:.1f} GB)"
            self._quant_combo.addItem(label, item)
            if curr and curr.filename == item.filename: default_idx = idx
            elif not curr and "Q4_K_M" in (item.quantization or "").upper(): default_idx = idx
        if files: self._quant_combo.setCurrentIndex(default_idx)
        self._quant_combo.blockSignals(False)

    def _render_instance_cards(self) -> None:
        ids = self.store.all_instance_ids()
        to_del = [iid for iid in self._instance_cards if iid not in ids]
        for iid in to_del: self._instance_cards.pop(iid).deleteLater()

        if not ids:
            while self._instance_lay.count() > 1:
                it = self._instance_lay.takeAt(0)
                if it.widget(): it.widget().deleteLater()
            empty = QLabel("No active instances. Go to Instances to add one.")
            empty.setStyleSheet(f"color: {t.TEXT_MID}; font-style: italic; padding: {t.SPACE_4}px;")
            empty.setAlignment(Qt.AlignCenter)
            self._instance_lay.insertWidget(0, empty)
            return

        sel_file = self._quant_combo.currentData()
        for iid in ids:
            state = self.store.get_state(iid)
            active = self.registry.active_for(iid)
            if iid not in self._instance_cards:
                card = _InstanceCard(iid, self)
                card.confirmed.connect(self._on_action_confirmed)
                card.setup_requested.connect(self._on_card_setup)
                card.reset_requested.connect(self._on_card_reset)
                card.deploy_requested.connect(self._on_card_deploy)
                self._instance_cards[iid] = card
                self._instance_lay.insertWidget(self._instance_lay.count() - 1, card)
            
            card = self._instance_cards[iid]
            if active: 
                card.show_progress(active.stage, active.percent)
            else:
                card.populate_info(iid, state, sel_file, False, None, self.scorer)
                # Auto-collapse if no longer busy/confirming, BUT preserve the FAILED state (dismiss button)
                if card._prog_dismiss.isVisible():
                    pass  # Keep the failed state visible so user can read log and click Clear
                elif not card._confirm_widget.isVisible() and not card._prog_widget.isVisible():
                    card.show_idle()

    def show_confirm_overlay(self, iid: int, mode: str = "deploy") -> None:
        if iid not in self._instance_cards: return
        card = self._instance_cards[iid]
        state = self.store.get_state(iid)
        gpu = f"GPU: {state.system.gpu_name or '?'} | {(state.system.gpu_vram_gb or 0):.1f} GB"
        if mode == "setup":
            summary = f"{gpu}\n\n• Installs cmake/git build tools\n• Compiles llama.cpp for CUDA backend"
        elif mode == "wipe":
            summary = f"{gpu}\n• Kills active servers\n• DELETES /opt/llama.cpp (destructive)"
        else:
            f = self._quant_combo.currentData()
            gb = f.size_bytes / (1024 ** 3) if f else 0
            needs = "• Environment setup needed\n" if not state.setup.llamacpp_installed else ""
            summary = f"{gpu}\nRepo: {self.current_model.id}\nFile: {f.filename if f else '?'}\nSize: {gb:.1f} GB\n\n{needs}• Downloads GGUF to local volume"
        card.show_confirm(mode, summary)

    def _on_action_confirmed(self, mode: str, iid: int) -> None:
        if mode == "setup": self.setup_requested.emit(iid)
        elif mode == "wipe": self.wipe_requested.emit(iid)
        else:
            f = self._quant_combo.currentData()
            if f and self.current_model:
                self.install_requested.emit(iid, self.current_model.id, f.filename)

    def _on_registry_update(self, key: str) -> None:
        active = self.registry.get(key)
        if active and active.iid in self._instance_cards:
            self._instance_cards[active.iid].show_progress(active.stage, active.percent)
        if self.mode == self.MODE_BUSY:
            m_a = self._current_active_job()
            if m_a and m_a.key == key:
                self._progress.set_stage(m_a.stage, percent=m_a.percent)
                if m_a.speed: self._progress.append_log(f"{m_a.percent}% - {m_a.speed}")

    def _on_registry_finished(self, key: str, ok: bool) -> None:
        if not ok:
            # The job is finished but failed. Find the card that was tracking it and lock it into the error state.
            for card in self._instance_cards.values():
                if card._prog_widget.isVisible() and not card._prog_dismiss.isVisible():
                    card.show_failed("Operation aborted or crashed.")
                    break
        self._refresh()

    def append_log(self, key: str, text: str):
        # 1. Update Master Log (top)
        active = self._current_active_job()
        if active and active.key == key:
            self._progress.append_log(text)
            
        # 2. Route to specific card
        job = self.registry.get(key)
        if job and job.iid in self._instance_cards:
            self._instance_cards[job.iid].append_log(text)
            
    def _on_card_setup(self, iid: int):
        self.show_confirm_overlay(iid, mode="setup")

    def _on_card_reset(self, iid: int):
        self.show_confirm_overlay(iid, mode="wipe")

    def _on_card_deploy(self, iid: int):
        self.show_confirm_overlay(iid, mode="deploy")

    def _show_cancel_confirm(self) -> None:
        self._cancel_strip.show()

    def _emit_cancel(self) -> None:
        self._cancel_strip.hide()
        a = self._current_active_job()
        if a: self.cancel_requested.emit(a.key)

    def _current_active_job(self):
        if not self.current_model: return None
        return next((d for _, d in self.registry.active_items() if d.repo_id == self.current_model.id), None)

    def _on_stale_resume(self) -> None:
        if self._stale_desc:
            self.resume_requested.emit(self._stale_desc.key)
            self._stale_banner.hide()

    def _on_stale_discard(self) -> None:
        if self._stale_desc:
            self.discard_requested.emit(self._stale_desc.key)
            self._stale_banner.hide()

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self._panel_meta.setText(f"{mode.upper()}")
        self.stack.setCurrentIndex({"idle": 0, "ready": 1, "busy": 2}.get(mode, 0))
