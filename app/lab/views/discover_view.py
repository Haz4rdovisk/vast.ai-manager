"""Discover view: Hugging Face GGUF search, fit scoring, and side-panel install."""
from __future__ import annotations

import json
import os
import pathlib
import re
import webbrowser

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.lab.services.fit_scorer import InstanceFitScorer
from app.lab.services.huggingface import HFModel
from app.lab.services.job_registry import JobRegistry
from app.lab.services.model_catalog import CatalogEntry
from app.lab.views.install_panel_side import InstallPanelSide
from app.lab.workers.huggingface_worker import HFSearchWorker
from app.ui.components.model_card import ModelCard


_FIT_LEVEL = {"perfect": "ok", "good": "info", "marginal": "warn", "too_tight": "err", "pending": "muted"}
_FIT_LABEL = {
    "perfect": "Perfect Fit",
    "good": "Good Fit",
    "marginal": "Tight Fit",
    "too_tight": "Too Large",
    "pending": "Analyzing...",
}

CATEGORY_MAP: dict[str, dict] = {
    "All": {"pipeline": None, "heuristic": None},
    "General": {"pipeline": "text-generation", "heuristic": None},
    "Coding": {"pipeline": "text-generation", "heuristic": "coding"},
    "Reasoning": {"pipeline": "text-generation", "heuristic": "reasoning"},
    "Chat": {"pipeline": "text-generation", "heuristic": "chat"},
    "Multimodal": {"pipeline": "image-text-to-text", "heuristic": None},
    "Embedding": {"pipeline": "feature-extraction", "heuristic": None},
}

_CODING_RX = re.compile(
    r"\b(coder?|starcoder\d*|deepseek[-_]?coder|qwen[-_]?coder|wizardcoder|codellama|codegemma)\b",
    re.I,
)
_REASONING_RX = re.compile(r"\b(r1|qwq|reasoner?|o1|phi[-_]?reason|deepseek[-_]?r)\b", re.I)
_CHAT_RX = re.compile(r"\b(chat|instruct|sft|assistant|rp|roleplay)\b", re.I)
_HEURISTIC_RX = {"coding": _CODING_RX, "reasoning": _REASONING_RX, "chat": _CHAT_RX}


def apply_category_heuristic(category: str, models: list) -> list:
    """Apply client-side category filtering for tags HF cannot express cleanly."""
    cfg = CATEGORY_MAP.get(category)
    if not cfg or not cfg["heuristic"]:
        return models
    rx = _HEURISTIC_RX[cfg["heuristic"]]
    return [model for model in models if rx.search(model.name) or any(rx.search(tag) for tag in model.tags)]


class DiscoverView(QWidget):
    download_requested = Signal(int, str, str)
    setup_requested = Signal(int)
    wipe_requested = Signal(int)
    cancel_requested = Signal(str)
    resume_requested = Signal(str)
    discard_requested = Signal(str)
    back_requested = Signal()
    instances_requested = Signal()

    def __init__(self, store, job_registry: JobRegistry | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("discover-view")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"""
            QWidget#discover-view {{
                background: {t.BG_DEEP};
            }}
            QWidget#discover-topbar {{
                background: #05080d;
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }}
            QLabel#discover-brand {{
                color: {t.TEXT_HI};
                font-size: 16px;
                font-weight: 900;
            }}
            QLabel#discover-subbrand {{
                color: {t.TEXT_MID};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QWidget#discover-left-pane {{
                background: {t.BG_DEEP};
            }}
            QFrame#discover-summary {{
                background: #0d131c;
                border: 1px solid rgba(255,255,255,0.07);
                border-radius: 14px;
            }}
            QLabel#discover-summary-title {{
                color: {t.TEXT_HI};
                font-size: 18px;
                font-weight: 800;
            }}
            QLabel#discover-summary-meta {{
                color: {t.TEXT_MID};
                font-size: 12px;
            }}
            QLabel#discover-summary-chip {{
                color: {t.ACCENT_SOFT};
                background: rgba(124,92,255,0.10);
                border: 1px solid rgba(124,92,255,0.24);
                border-radius: 999px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 800;
            }}
            QLineEdit {{
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px;
                padding: 8px 14px;
                color: {t.TEXT_HI};
            }}
            QLineEdit:focus {{
                border-color: {t.ACCENT};
                background: rgba(255,255,255,0.05);
            }}
            QComboBox {{
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px;
                padding: 6px 10px;
                color: {t.TEXT_HI};
            }}
            QPushButton#discover-search-btn {{
                background: {t.ACCENT};
                border: none;
                border-radius: 10px;
                color: white;
                font-weight: 700;
                padding: 8px 18px;
            }}
            QPushButton#discover-search-btn:hover {{
                background: {t.ACCENT_HI};
            }}
            QPushButton#discover-close-btn {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px;
                color: {t.TEXT_HI};
                font-weight: 600;
            }}
            QPushButton#discover-close-btn:hover {{
                background: rgba(255,255,255,0.08);
            }}
            """
        )

        self.store = store
        self.registry = job_registry or JobRegistry.in_memory()
        self.scorer = InstanceFitScorer()
        self.worker = None
        self.current_models: list[HFModel] = []
        self._connected_instance_ids: list[int] | None = None
        self._instance_render_signatures: dict[int, tuple] = {}
        self._connection_snapshot: tuple[int, ...] = ()
        self._next_cursor: str | None = None
        self._append_mode = False
        self._pending_splitter_sizes = None

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(200)
        self._render_timer.timeout.connect(self._render)

        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.setInterval(400)
        self._splitter_save_timer.timeout.connect(self._flush_splitter_sizes)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.topbar = QWidget()
        self.topbar.setObjectName("discover-topbar")
        self.topbar.setFixedHeight(64)
        top_lay = QHBoxLayout(self.topbar)
        top_lay.setContentsMargins(16, 8, 16, 8)
        top_lay.setSpacing(t.SPACE_3)

        # 1. Left Section (Brand)
        left_sect = QWidget()
        left_sect_lay = QHBoxLayout(left_sect)
        left_sect_lay.setContentsMargins(0, 0, 0, 0)
        left_sect_lay.setSpacing(t.SPACE_3)
        brand_box = QVBoxLayout()
        brand_box.setContentsMargins(0, 0, 0, 0)
        brand_box.setSpacing(1)
        brand = QLabel("Model Store")
        brand.setObjectName("discover-brand")
        brand_box.addWidget(brand)
        subbrand = QLabel("Connected GGUF Catalog")
        subbrand.setObjectName("discover-subbrand")
        brand_box.addWidget(subbrand)
        left_sect_lay.addLayout(brand_box)
        left_sect_lay.addStretch()
        top_lay.addWidget(left_sect, 1)

        # 2. Center Section (Consolidated Search Bar)
        center_sect = QWidget()
        center_sect_lay = QHBoxLayout(center_sect)
        center_sect_lay.setContentsMargins(0, 0, 0, 0)
        center_sect_lay.setSpacing(t.SPACE_2)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Hugging Face...")
        self.search_input.setFixedWidth(280)
        self.search_input.returnPressed.connect(lambda: self._search())
        center_sect_lay.addWidget(self.search_input)

        self.filter = QComboBox()
        self.filter.addItems(list(CATEGORY_MAP.keys()))
        self.filter.setFixedWidth(100)
        self.filter.currentIndexChanged.connect(lambda _: self._search())
        center_sect_lay.addWidget(self.filter)

        self.size_filter = QComboBox()
        self.size_filter.addItems(["All Sizes", "< 7B", "7B - 14B", "14B - 35B", "35B - 80B", "> 80B"])
        self.size_filter.setFixedWidth(100)
        self.size_filter.currentIndexChanged.connect(self._render)
        center_sect_lay.addWidget(self.size_filter)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Downloads", "Best Fit"])
        self.sort_combo.setFixedWidth(110)
        self.sort_combo.currentIndexChanged.connect(self._render)
        center_sect_lay.addWidget(self.sort_combo)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("discover-search-btn")
        self.search_btn.setProperty("size", "sm")
        self.search_btn.clicked.connect(lambda: self._search())
        center_sect_lay.addWidget(self.search_btn)
        
        top_lay.addWidget(center_sect, 0, Qt.AlignCenter)

        # 3. Right Section (System Actions)
        right_sect = QWidget()
        right_sect_lay = QHBoxLayout(right_sect)
        right_sect_lay.setContentsMargins(0, 0, 0, 0)
        right_sect_lay.setSpacing(t.SPACE_2)
        right_sect_lay.addStretch()

        self.close_panel_btn = QPushButton("Close")
        self.close_panel_btn.setObjectName("discover-close-btn")
        self.close_panel_btn.setProperty("variant", "secondary")
        self.close_panel_btn.setFixedWidth(124)
        self.close_panel_btn.setVisible(True)
        self.close_panel_btn.clicked.connect(self._toggle_side_panel)
        right_sect_lay.addWidget(self.close_panel_btn)

        top_lay.addWidget(right_sect, 1)

        root.addWidget(self.topbar)

        self.layout_stack = QStackedWidget()
        root.addWidget(self.layout_stack, 1)

        self.lock_widget = self._build_lock_widget()
        self.layout_stack.addWidget(self.lock_widget)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("discover-workspace")
        self.content_widget.setStyleSheet(f"QWidget#discover-workspace {{ background: {t.BG_DEEP}; }}")
        content_lay = QVBoxLayout(self.content_widget)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        self.left_pane = QWidget()
        self.left_pane.setObjectName("discover-left-pane")
        left_lay = QVBoxLayout(self.left_pane)
        left_lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, 0)
        left_lay.setSpacing(t.SPACE_4)

        self.summary_card = QWidget()
        self.summary_card.setObjectName("discover-summary")
        summary_lay = QHBoxLayout(self.summary_card)
        summary_lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        summary_lay.setSpacing(t.SPACE_4)

        summary_text = QVBoxLayout()
        summary_text.setContentsMargins(0, 0, 0, 0)
        summary_text.setSpacing(2)
        self.summary_title = QLabel("GGUF catalog ready")
        self.summary_title.setObjectName("discover-summary-title")
        self.summary_meta = QLabel("Search. Fit. Deploy.")
        self.summary_meta.setObjectName("discover-summary-meta")
        self.summary_meta.setWordWrap(True)
        summary_text.addWidget(self.summary_title)
        summary_text.addWidget(self.summary_meta)
        summary_lay.addLayout(summary_text, 1)

        summary_chips = QVBoxLayout()
        summary_chips.setContentsMargins(0, 0, 0, 0)
        summary_chips.setSpacing(t.SPACE_2)
        self.summary_scope = QLabel("0 connected targets")
        self.summary_scope.setObjectName("discover-summary-chip")
        self.summary_ops = QLabel("0 active operations")
        self.summary_ops.setObjectName("discover-summary-chip")
        summary_chips.addWidget(self.summary_scope, 0, Qt.AlignRight)
        summary_chips.addWidget(self.summary_ops, 0, Qt.AlignRight)
        summary_lay.addLayout(summary_chips)
        left_lay.addWidget(self.summary_card)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        left_lay.addWidget(self.progress)

        self.status_lbl = QLabel("Searching starts automatically after an SSH connection is active.")
        self.status_lbl.setProperty("role", "muted")
        self.status_lbl.setWordWrap(True)
        left_lay.addWidget(self.status_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, t.SPACE_3, 0)
        self.list_lay.setSpacing(t.SPACE_3)
        self.scroll.setWidget(self.list_host)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(True)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {t.BORDER_LOW}; }}"
        )
        self._splitter.addWidget(self.left_pane)
        self.side_panel = InstallPanelSide(self.store, self.registry, self)
        self._splitter.addWidget(self.side_panel)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        saved = self._load_splitter_sizes()
        self._splitter.setSizes(saved if saved and len(saved) == 2 else [1040, 420])
        self._splitter.splitterMoved.connect(lambda *_: self._queue_splitter_save(self._splitter.sizes()))

        self.load_more_btn = QPushButton("Load more")
        self.load_more_btn.clicked.connect(lambda: self._search(append=True))
        self.load_more_btn.hide()
        left_lay.addWidget(self.scroll, 1)
        left_lay.addWidget(self.load_more_btn, 0, Qt.AlignCenter)

        content_lay.addWidget(self._splitter, 1)

        self.side_panel.close_requested.connect(self._toggle_side_panel)
        self.side_panel.install_requested.connect(self.download_requested.emit)
        self.side_panel.setup_requested.connect(self.setup_requested.emit)
        self.side_panel.wipe_requested.connect(self.wipe_requested.emit)
        self.side_panel.cancel_requested.connect(self.cancel_requested.emit)
        self.side_panel.resume_requested.connect(self.resume_requested.emit)
        self.side_panel.discard_requested.connect(self.discard_requested.emit)
        self.side_panel.show()
        self._sync_side_panel_button()

        self.layout_stack.addWidget(self.content_widget)

        self.store.instance_state_updated.connect(self._on_instance_state_updated)
        self.registry.job_updated.connect(lambda _key: self._schedule_render())
        self.registry.job_started.connect(lambda _key: self._schedule_render())
        self.registry.job_finished.connect(lambda *_: self._schedule_render())
        self._update_lock_state()

    def set_connected_instance_ids(self, ids: list[int] | None) -> None:
        self._connected_instance_ids = list(ids) if ids is not None else None
        self.side_panel.set_connected_instance_ids(self._connected_instance_ids)
        self._connection_snapshot = self._current_connection_snapshot()
        self._update_lock_state()
        self._refresh_summary()
        self._schedule_render()


    def _build_lock_widget(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(t.SPACE_8, t.SPACE_8, t.SPACE_8, t.SPACE_8)
        lay.setSpacing(t.SPACE_4)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignCenter)
        center.setSpacing(t.SPACE_4)
        lock_icon = QLabel()
        lock_icon.setAlignment(Qt.AlignCenter)
        try:
            import qtawesome as qta

            lock_icon.setPixmap(qta.icon("mdi.lock-outline", color=t.ACCENT_SOFT).pixmap(42, 42))
        except Exception:
            lock_icon.hide()
        title = QLabel("SSH Tunnel Required")
        title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 24px; font-weight: 700;")
        title.setAlignment(Qt.AlignCenter)
        msg = QLabel(
            "The Model Store requires an active SSH connection to calculate hardware fit scores "
            "and enable remote installations.\n\nPlease connect an instance via SSH to continue."
        )
        msg.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 14px;")
        msg.setAlignment(Qt.AlignCenter)
        msg.setFixedWidth(400)
        msg.setWordWrap(True)
        goto_btn = QPushButton("Go to Instances")
        goto_btn.setFixedWidth(200)
        goto_btn.clicked.connect(self.instances_requested.emit)
        center.addStretch()
        center.addWidget(lock_icon)
        center.addWidget(title)
        center.addWidget(msg)
        center.addSpacing(t.SPACE_4)
        center.addWidget(goto_btn, 0, Qt.AlignCenter)
        center.addStretch()
        lay.addLayout(center, 1)
        return widget

    def _ui_state_path(self) -> pathlib.Path:
        return pathlib.Path.home() / ".vastai-app" / "ui_state.json"

    def _load_splitter_sizes(self) -> list[int] | None:
        path = self._ui_state_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        sizes = data.get("discover_splitter")
        if isinstance(sizes, list) and all(isinstance(item, int) for item in sizes):
            return sizes
        return None

    def _save_splitter_sizes(self, sizes: list[int]) -> None:
        path = self._ui_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            data = {}
        data["discover_splitter"] = sizes
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))

    def _queue_splitter_save(self, sizes: list[int]) -> None:
        self._pending_splitter_sizes = list(sizes)
        self._splitter_save_timer.start()

    def _flush_splitter_sizes(self) -> None:
        if self._pending_splitter_sizes is None:
            return
        sizes = self._pending_splitter_sizes
        self._pending_splitter_sizes = None
        self._save_splitter_sizes(sizes)

    def _update_lock_state(self):
        connected = (
            self._connected_instance_ids
            if self._connected_instance_ids is not None
            else self.store.all_instance_ids()
        )
        has_connected = len(connected) > 0
        has_active_jobs = len(list(self.registry.active_items())) > 0
        
        # Only show lock if NO connections AND NO active jobs running
        target_idx = 1 if (has_connected or has_active_jobs) else 0
        
        if self.layout_stack.currentIndex() != target_idx:
            self.layout_stack.setCurrentIndex(target_idx)
            if target_idx == 1 and not self.current_models:
                self._search("llama")
        if target_idx == 1:
            self._refresh_summary()

    def _search(self, query: str = "", append: bool = False):
        if self.worker and self.worker.isRunning():
            return

        term = query if isinstance(query, str) and query else self.search_input.text().strip()
        category = self.filter.currentText()
        cfg = CATEGORY_MAP.get(category, CATEGORY_MAP["All"])
        cursor = self._next_cursor if append else None
        self._append_mode = append

        self.progress.setVisible(True)
        self.search_btn.setEnabled(False)
        self.search_input.setEnabled(False)
        self.load_more_btn.setEnabled(False)
        self.status_lbl.setText(
            "Loading more..." if append else f"Searching Hugging Face for '{term or 'GGUF'}'..."
        )
        self._refresh_summary(search_text=term or "GGUF", searching=True)

        self.worker = HFSearchWorker(
            query=term,
            limit=40,
            pipeline_tag=cfg["pipeline"],
            cursor=cursor,
            parent=self,
        )
        self.worker.finished.connect(lambda models, next_cursor: self._on_search_finished(models, next_cursor, category))
        self.worker.error.connect(self._on_search_error)
        self.worker.start()

    def _on_search_finished(self, models: list[HFModel], next_cursor: str | None, category: str):
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self.search_input.setEnabled(True)
        self.load_more_btn.setEnabled(True)

        filtered = apply_category_heuristic(category, models)
        if self._append_mode:
            seen = {model.id for model in self.current_models}
            self.current_models.extend([model for model in filtered if model.id not in seen])
        else:
            self.current_models = filtered
        self._next_cursor = next_cursor
        self.load_more_btn.setVisible(bool(next_cursor))
        self.status_lbl.setText(
            "No GGUF models found for that search." if not self.current_models else f"Found {len(self.current_models)} models."
        )
        self._adopt_default_selection()
        self._refresh_summary()
        self._render()

    def _on_search_error(self, error: str):
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self.search_input.setEnabled(True)
        self.load_more_btn.setEnabled(bool(self._next_cursor))
        self.status_lbl.setText(f"Search failed: {error}")
        self._refresh_summary()

    def _render(self):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.current_models:
            self.list_lay.addStretch()
            self._refresh_summary()
            return

        instance_ids = (
            list(self._connected_instance_ids)
            if self._connected_instance_ids is not None
            else self.store.all_instance_ids()
        )
        model_scores: dict[str, float] = {}
        score_labels: dict[str, list[str]] = {}
        # Quality weights for tie-breaking same scores (higher is better quality)
        QUANT_QUALITY = {
            "BF16": 100, "FP16": 100, "F16": 100,
            "Q8_0": 90, "Q6_K": 80, "Q5_K_M": 75, "Q5_K_S": 70,
            "Q4_K_M": 60, "Q4_K_S": 55, "Q3_K_M": 40, "Q2_K": 20,
        }

        for model in self.current_models:
            max_score = 0.0
            labels: list[dict] = []
            
            for iid in instance_ids:
                state = self.store.get_state(iid)
                if not (state and state.system):
                    continue

                best_file_match = None
                best_file_score = -1.0
                best_file_quality = -1
                
                # If no files found (search might not have returned siblings for some reason), 
                # use fallback Q4_K_M heuristic
                files_to_test = model.files if model.files else [None]
                
                for f in files_to_test:
                    if f:
                        size_gb = f.size_bytes / (1024 ** 3)
                        quant = f.quantization or "Unknown"
                        entry = CatalogEntry(
                            name=model.name,
                            provider=model.author,
                            params_b=model.params_b,
                            best_quant=quant,
                            memory_required_gb=size_gb + 0.5, # Small overhead
                            estimated_tps_7b=50.0,
                            gguf_sources=[model.id],
                        )
                    else:
                        # Fallback heuristic
                        entry = CatalogEntry(
                            name=model.name,
                            provider=model.author,
                            params_b=model.params_b,
                            best_quant="Q4_K_M",
                            memory_required_gb=(model.params_b * 0.7) if model.params_b > 0 else 5.0,
                            estimated_tps_7b=50.0,
                            gguf_sources=[model.id],
                        )
                    
                    scored = self.scorer.score(entry, state.system)
                    quality = QUANT_QUALITY.get(entry.best_quant, 0)
                    
                    # Tie break: keep the highest quality quantization that still yields the highest score
                    # (e.g. if both Q4 and Q8 have score 100 on a 80GB GPU, pick Q8)
                    if scored.score > best_file_score or (scored.score == best_file_score and quality > best_file_quality):
                        best_file_score = scored.score
                        best_file_match = {
                            "iid": iid,
                            "score": scored.score,
                            "fit": _FIT_LABEL.get(scored.fit_level, "Fit Available"),
                            "level": _FIT_LEVEL.get(scored.fit_level, "info"),
                            "best_quant": entry.best_quant if f else None
                        }
                        best_file_quality = quality
                
                if best_file_match:
                    labels.append(best_file_match)
                    max_score = max(max_score, best_file_score)

            model_scores[model.id] = max_score
            score_labels[model.id] = labels

        display_models = list(self.current_models)
        size_idx = self.size_filter.currentIndex()
        if size_idx > 0:
            display_models = [model for model in display_models if self._matches_size(model, size_idx)]
        if self.sort_combo.currentIndex() == 1:
            display_models.sort(key=lambda model: model_scores.get(model.id, 0), reverse=True)

        installing_by_model = {
            desc.repo_id: (desc.iid, desc.percent)
            for _key, desc in self.registry.active_items()
        }

        for model in display_models:
            card = ModelCard(model)
            card.set_selected(
                self.side_panel.current_model is not None
                and self.side_panel.current_model.id == model.id
            )
            card.set_instance_scores(score_labels.get(model.id, []))
            if model.id in installing_by_model:
                iid, percent = installing_by_model[model.id]
                card.set_installing(iid, percent)
            card.details_clicked.connect(self._show_details)
            card.open_hf_clicked.connect(self._open_hf)
            self.list_lay.addWidget(card)
        self.list_lay.addStretch()
        self._refresh_summary(model_count=len(display_models))

    def _schedule_render(self) -> None:
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _matches_size(self, model: HFModel, size_idx: int) -> bool:
        params = model.params_b
        if size_idx == 1:
            return params < 7
        if size_idx == 2:
            return 7 <= params < 14
        if size_idx == 3:
            return 14 <= params < 35
        if size_idx == 4:
            return 35 <= params < 80
        if size_idx == 5:
            return params >= 80
        return True

    def _show_details(self, model: HFModel):
        for idx in range(self.list_lay.count()):
            widget = self.list_lay.itemAt(idx).widget()
            if hasattr(widget, "set_selected"):
                widget.set_selected(getattr(widget, "model", None) is model)
        self.side_panel.set_model(model)
        self._set_side_panel_visible(True)
        self._refresh_summary()

    def _toggle_side_panel(self) -> None:
        self._set_side_panel_visible(not self.side_panel.isVisible())

    def _open_hf(self, model_id: str):
        webbrowser.open(f"https://huggingface.co/{model_id}")

    def _on_instance_state_updated(self, iid: int, state) -> None:
        snapshot = self._current_connection_snapshot()
        if snapshot != self._connection_snapshot:
            self._connection_snapshot = snapshot
            self._update_lock_state()
            self._refresh_summary()
            self._schedule_render()
            return

        sig = self._instance_signature(state)
        if self._instance_render_signatures.get(iid) == sig:
            return
        self._instance_render_signatures[iid] = sig
        if self.layout_stack.currentIndex() == 1 and self.current_models:
            self._schedule_render()

    def _current_connection_snapshot(self) -> tuple[int, ...]:
        ids = (
            list(self._connected_instance_ids)
            if self._connected_instance_ids is not None
            else self.store.all_instance_ids()
        )
        return tuple(sorted(ids))

    def _instance_signature(self, state) -> tuple:
        system = state.system
        setup = state.setup
        return (
            system.gpu_name,
            system.gpu_vram_gb,
            system.ram_total_gb,
            system.cpu_cores,
            system.has_gpu,
            setup.probed,
            setup.llamacpp_installed,
        )

    def _set_side_panel_visible(self, visible: bool) -> None:
        self.side_panel.setVisible(visible)
        if visible:
            sizes = self._splitter.sizes()
            if len(sizes) == 2 and sizes[1] == 0:
                self._splitter.setSizes([1040, 420])
        else:
            self._splitter.setSizes([1, 0])
        self._sync_side_panel_button()

    def _sync_side_panel_button(self) -> None:
        self.close_panel_btn.setText("Hide Settings" if self.side_panel.isVisible() else "Show Settings")

    def _adopt_default_selection(self) -> None:
        if not self.current_models:
            self.side_panel.clear()
            return
        current_id = self.side_panel.current_model.id if self.side_panel.current_model else None
        chosen = next((model for model in self.current_models if model.id == current_id), None)
        if chosen is None:
            chosen = self.current_models[0]
        self.side_panel.set_model(chosen)
        self._set_side_panel_visible(True)

    def _refresh_summary(
        self,
        *,
        model_count: int | None = None,
        search_text: str | None = None,
        searching: bool = False,
    ) -> None:
        connected_ids = (
            list(self._connected_instance_ids)
            if self._connected_instance_ids is not None
            else self.store.all_instance_ids()
        )
        active_ops = len(list(self.registry.active_items()))
        visible_models = model_count if model_count is not None else len(self.current_models)
        selected = self.side_panel.current_model.name if self.side_panel.current_model else "No model selected"

        if searching:
            self.summary_title.setText(f"Searching {search_text}...")
            self.summary_meta.setText("Refreshing catalog.")
        elif visible_models:
            self.summary_title.setText(f"{visible_models} models ready to inspect")
            self.summary_meta.setText(f"Focus: {selected}")
        else:
            self.summary_title.setText("GGUF catalog ready")
            self.summary_meta.setText("Search. Fit. Deploy.")

        self.summary_scope.setText(
            f"{len(connected_ids)} connected target" + ("" if len(connected_ids) == 1 else "s")
        )
        self.summary_ops.setText(
            f"{active_ops} active operation" + ("" if active_ops == 1 else "s")
        )
