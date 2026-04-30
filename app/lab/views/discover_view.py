"""Discover view: Hugging Face GGUF search, fit scoring, and side-panel install."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import pathlib
import re
import webbrowser

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import theme as t
from app.lab.services.fit_scorer import InstanceFitScorer
from app.lab.services.huggingface import (
    HFModel,
    HFModelFile,
    estimate_gguf_size_gb,
    has_complete_file_metadata,
    model_requires_detail_fetch,
)
from app.lab.services.job_registry import JobRegistry
from app.lab.services.model_catalog import CatalogEntry
from app.lab.views.install_panel_side import InstallPanelSide
from app.lab.workers.huggingface_worker import HFSearchWorker, HFModelDetailWorker
from app.ui.brand_manager import BrandManager
from app.ui.components import icons
from app.ui.components.model_card import ModelCard
from app.ui.components.lock_screen import LockScreen
from app.ui.components.page_header import PageHeader
from app.ui.components.primitives import IconButton


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

_SEARCH_PAGE_SIZE = 40
_DEFAULT_DISCOVER_QUERY = ""


@dataclass(frozen=True)
class _SearchRequest:
    term: str
    category: str
    sort_mode: str = "trending"
    cursor: str | None = None
    append: bool = False


@dataclass(frozen=True)
class _ModelScoreCacheEntry:
    model_signature: tuple
    scoring_context: tuple
    sort_rank: float
    display_score: float
    labels: tuple[tuple[tuple[str, object], ...], ...]


def apply_category_heuristic(category: str, models: list) -> list:
    """Apply client-side category filtering for tags HF cannot express cleanly."""
    cfg = CATEGORY_MAP.get(category)
    if not cfg or not cfg["heuristic"]:
        return models
    rx = _HEURISTIC_RX[cfg["heuristic"]]
    return [model for model in models if rx.search(model.name) or any(rx.search(tag) for tag in model.tags)]


def category_uses_client_heuristic(category: str) -> bool:
    cfg = CATEGORY_MAP.get(category, CATEGORY_MAP["All"])
    return bool(cfg.get("heuristic"))


class _SearchSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(18, 18)
        self.hide()

    def start(self) -> None:
        self.show()
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        size = min(self.width(), self.height())
        rect = QRectF(2, 2, size - 4, size - 4)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track_pen = QPen(QColor(255, 255, 255, 36), 2.2)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        accent_pen = QPen(QColor(t.ACCENT_HI), 2.4)
        accent_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(accent_pen)
        painter.drawArc(rect, (-self._angle) * 16, 110 * 16)


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
            QWidget#discover-controls {{
                background: transparent;
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
                background: #1C2535;
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 14px;
                padding: 6px 14px;
                min-height: 32px;
                color: {t.TEXT_HI};
            }}
            QLineEdit:focus {{
                border-color: rgba(255,255,255,0.08);
                background: #202B3E;
            }}
            QComboBox {{
                background: #253044;
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 14px;
                padding: 6px 14px;
                min-height: 32px;
                color: {t.TEXT_HI};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QPushButton#discover-search-btn {{
                background: {t.ACCENT};
                border: none;
                border-radius: 14px;
                color: white;
                font-weight: 700;
                padding: 8px 18px;
                min-height: 32px;
            }}
            QPushButton#discover-search-btn:hover {{
                background: {t.ACCENT_HI};
            }}
            QToolButton#discover-close-btn {{
                background: transparent;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                color: {t.TEXT_MID};
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}
            QToolButton#discover-close-btn:hover {{
                background: rgba(255,255,255,0.06);
                color: {t.TEXT_HI};
            }}
            """
        )

        self.store = store
        self.registry = job_registry or JobRegistry.in_memory()
        self.scorer = InstanceFitScorer()
        self.worker = None
        self.current_models: list[HFModel] = []
        self._active_request: _SearchRequest | None = None
        self._queued_request: _SearchRequest | None = None
        self._search_generation = 0
        self._page_buffer: list[HFModel] = []
        self._page_seen_ids: set[str] = set()
        self._connected_instance_ids: list[int] | None = None
        self._instance_render_signatures: dict[int, tuple] = {}
        self._score_cache: dict[str, _ModelScoreCacheEntry] = {}
        self._displayed_model_ids: tuple[str, ...] = ()
        self._visible_model_count = 0
        self._detail_session_id = 0
        self._connection_snapshot: tuple[int, ...] = ()
        self._next_cursor: str | None = None
        self._append_mode = False
        self._pending_splitter_sizes = None

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(200)
        self._render_timer.timeout.connect(self._render)
        
        self._detail_queue: list[str] = [] # Model IDs to fetch
        self._is_fetching_details = False
        self._detail_worker = None
        self._cards: dict[str, ModelCard] = {}

        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.setInterval(400)
        self._splitter_save_timer.timeout.connect(self._flush_splitter_sizes)

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_5, t.SPACE_3, t.SPACE_5, t.SPACE_4)
        root.setSpacing(t.SPACE_3)

        header = PageHeader(
            "Model Store",
            "Browse the connected GGUF catalog and install models on your instances.",
        )

        self.summary_scope = QLabel("0 connected targets")
        self.summary_scope.setObjectName("discover-summary-chip")
        header.add_action(self.summary_scope)

        self.summary_ops = QLabel("0 active operations")
        self.summary_ops.setObjectName("discover-summary-chip")
        header.add_action(self.summary_ops)

        self.close_panel_btn = IconButton(icons.CLOSE, "Hide settings")
        self.close_panel_btn.setObjectName("discover-close-btn")
        self.close_panel_btn.setVisible(True)
        self.close_panel_btn.clicked.connect(self._toggle_side_panel)
        header.add_action(self.close_panel_btn)

        root.addWidget(header)

        self.topbar = QWidget()
        self.topbar.setObjectName("discover-controls")
        top_lay = QHBoxLayout(self.topbar)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(t.SPACE_3)

        # Consolidated Search Bar
        center_sect = QWidget()
        center_sect_lay = QHBoxLayout(center_sect)
        center_sect_lay.setContentsMargins(0, 0, 0, 0)
        center_sect_lay.setSpacing(t.SPACE_2)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Hugging Face...")
        self.search_input.setFixedWidth(220)
        self.search_input.returnPressed.connect(lambda: self._search())
        center_sect_lay.addWidget(self.search_input)

        self.filter = QComboBox()
        self.filter.addItems(list(CATEGORY_MAP.keys()))
        self.filter.setFixedWidth(110)
        self.filter.currentIndexChanged.connect(lambda _: self._search())
        center_sect_lay.addWidget(self.filter)

        self.size_filter = QComboBox()
        self.size_filter.addItems(["All Sizes", "< 7B", "7B - 14B", "14B - 35B", "35B - 80B", "> 80B", "Unknown Size"])
        self.size_filter.setFixedWidth(110)
        self.size_filter.currentIndexChanged.connect(self._render)
        center_sect_lay.addWidget(self.size_filter)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Trending", "Downloads", "Best Fit"])
        self.sort_combo.setFixedWidth(110)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        center_sect_lay.addWidget(self.sort_combo)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("discover-search-btn")
        self.search_btn.setProperty("size", "sm")
        self.search_btn.clicked.connect(lambda: self._search())
        center_sect_lay.addWidget(self.search_btn)

        self.search_spinner = _SearchSpinner()
        center_sect_lay.addWidget(self.search_spinner, 0, Qt.AlignVCenter)
        
        top_lay.addWidget(center_sect, 0, Qt.AlignLeft)
        top_lay.addStretch(1)

        self.layout_stack = QStackedWidget()
        root.addWidget(self.layout_stack, 1)

        self.lock_widget = LockScreen(
            title="SSH Tunnel Required",
            message="The Model Store requires an active SSH connection to calculate hardware fit scores and enable remote installations.\n\nPlease connect an instance via SSH to continue."
        )
        self.lock_widget.instances_requested.connect(self.instances_requested.emit)
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
        left_lay.setContentsMargins(t.SPACE_4, 0, t.SPACE_4, 0)
        left_lay.setSpacing(t.SPACE_4)
        left_lay.addWidget(self.topbar)

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
        self.list_host.setMinimumWidth(0)
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, t.SPACE_3, 0)
        self.list_lay.setSpacing(t.SPACE_3)
        self.scroll.setWidget(self.list_host)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(True)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(
            "QSplitter::handle { background: transparent; }"
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
        self.side_panel.details_fetched.connect(lambda _: self._schedule_render())
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
                self._search(_DEFAULT_DISCOVER_QUERY)
        if target_idx == 1:
            self._refresh_summary()

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

    def _search(self, query: str = "", append: bool = False):
        request = self._build_search_request(query=query, append=append)
        if self._active_request == request and self.worker and self.worker.isRunning():
            return

        if self.worker and self.worker.isRunning():
            self._queued_request = request
            self._set_search_loading(True)
            self.load_more_btn.setEnabled(False)
            self.status_lbl.setText("Updating search...")
            self._refresh_summary(search_text=request.term or "Top GGUF", searching=True)
            return

        self._launch_search(request, reset_buffer=True)

    def _build_search_request(self, query: str = "", append: bool = False) -> _SearchRequest:
        if append and self._active_request is not None:
            term = self._active_request.term
            category = self._active_request.category
            sort_mode = self._active_request.sort_mode
        else:
            term = query if isinstance(query, str) and query else self.search_input.text().strip()
            category = self.filter.currentText()
            sort_mode = self._current_sort_mode()
        return _SearchRequest(
            term=term,
            category=category,
            sort_mode=sort_mode,
            cursor=self._next_cursor if append else None,
            append=append,
        )

    def _current_sort_mode(self) -> str:
        return {
            0: "trending",
            1: "downloads",
            2: "best_fit",
        }.get(self.sort_combo.currentIndex(), "trending")

    def _hf_sort_key(self, sort_mode: str) -> str:
        return "trendingScore" if sort_mode == "trending" else "downloads"

    def _on_sort_changed(self, _index: int) -> None:
        if self._current_sort_mode() == "best_fit":
            self._render()
            return
        self._search()

    def _launch_search(self, request: _SearchRequest, *, reset_buffer: bool) -> None:
        cfg = CATEGORY_MAP.get(request.category, CATEGORY_MAP["All"])
        self._active_request = request
        self._queued_request = None
        self._append_mode = request.append
        if reset_buffer:
            self._page_buffer = []
            self._page_seen_ids = {model.id for model in self.current_models} if request.append else set()
            if not request.append:
                for model in self.current_models:
                    model.details_loading = False
                self._detail_session_id += 1
                self._detail_queue = []
                self._is_fetching_details = False
                self._detail_worker = None
        self._search_generation += 1
        generation = self._search_generation

        self._set_search_loading(True)
        self.load_more_btn.setEnabled(False)
        self.status_lbl.setText(
            "Loading more..." if request.append else self._search_status_text(request.term)
        )
        self._refresh_summary(search_text=request.term or "Top GGUF", searching=True)

        self.worker = HFSearchWorker(
            query=request.term,
            limit=_SEARCH_PAGE_SIZE,
            pipeline_tag=cfg["pipeline"],
            cursor=request.cursor,
            sort_by=self._hf_sort_key(request.sort_mode),
            parent=self,
        )
        self.worker.finished.connect(
            lambda models, next_cursor, generation=generation, request=request: self._on_search_finished(
                generation, request, models, next_cursor
            )
        )
        self.worker.error.connect(
            lambda error, generation=generation, request=request: self._on_search_error(generation, request, error)
        )
        self.worker.start()

    def _publish_search_results(
        self,
        request: _SearchRequest,
        filtered_batch: list[HFModel],
        next_cursor: str | None,
        *,
        partial: bool = False,
    ) -> None:
        if request.append:
            seen = {model.id for model in self.current_models}
            self.current_models.extend([model for model in filtered_batch if model.id not in seen])
        else:
            self.current_models = list(filtered_batch)

        self._next_cursor = next_cursor
        self.load_more_btn.setVisible(bool(next_cursor) and not partial)
        visible_count = self._current_visible_model_count()
        if partial:
            self.status_lbl.setText(
                self._format_result_status(
                    total_count=len(self.current_models),
                    visible_count=visible_count,
                    partial=True,
                )
            )
        else:
            self.status_lbl.setText(
                self._format_result_status(
                    total_count=len(self.current_models),
                    visible_count=visible_count,
                    partial=False,
                )
            )
        self._refresh_summary()

        new_ids = [m.id for m in filtered_batch if model_requires_detail_fetch(m)]
        if request.append:
            seen_queue = set(self._detail_queue)
            self._detail_queue.extend([mid for mid in new_ids if mid not in seen_queue])
        else:
            self._detail_queue = new_ids

        self._render()
        self._start_detail_fetch()

    def _on_search_finished(
        self,
        generation,
        request=None,
        models: list[HFModel] | str | None = None,
        next_cursor: str | None = None,
    ):
        if isinstance(generation, list):
            legacy_models = generation
            legacy_next_cursor = request if isinstance(request, str | type(None)) else None
            legacy_category = models if isinstance(models, str) else self.filter.currentText()
            self._search_generation += 1
            generation = self._search_generation
            request = _SearchRequest(
                term=self.search_input.text().strip(),
                category=legacy_category,
                sort_mode=self._current_sort_mode(),
                cursor=None,
                append=self._append_mode,
            )
            self._active_request = request
            self._page_buffer = []
            self._page_seen_ids = {model.id for model in self.current_models} if self._append_mode else set()
            models = legacy_models
            next_cursor = legacy_next_cursor

        self._handle_search_finished(generation, request, models or [], next_cursor)

    def _handle_search_finished(
        self,
        generation: int,
        request: _SearchRequest,
        models: list[HFModel],
        next_cursor: str | None,
    ) -> None:
        if generation != self._search_generation or self._active_request != request:
            return

        self.worker = None
        for model in models:
            if model.id in self._page_seen_ids:
                continue
            self._page_buffer.append(model)
            self._page_seen_ids.add(model.id)

        filtered_batch = apply_category_heuristic(request.category, self._page_buffer)
        if (
            not request.append
            and category_uses_client_heuristic(request.category)
            and filtered_batch
        ):
            self._publish_search_results(request, filtered_batch, next_cursor, partial=bool(next_cursor))

        if self._queued_request is not None and self._queued_request != request:
            self._set_search_loading(False)
            self.load_more_btn.setEnabled(True)
            self._run_queued_search_if_any()
            return

        if self._should_prefetch_more(request, filtered_batch, next_cursor):
            next_request = _SearchRequest(
                term=request.term,
                category=request.category,
                sort_mode=request.sort_mode,
                cursor=next_cursor,
                append=request.append,
            )
            self.status_lbl.setText(
                f"Refining {request.category.lower()} results..." if request.category != "All" else "Loading more..."
            )
            self._launch_search(next_request, reset_buffer=False)
            return

        self._set_search_loading(False)
        self.load_more_btn.setEnabled(True)
        self._publish_search_results(request, filtered_batch, next_cursor, partial=False)
        self._run_queued_search_if_any()

    def _on_search_error(self, generation: int, request: _SearchRequest, error: str):
        if generation != self._search_generation or self._active_request != request:
            return

        self.worker = None
        self._set_search_loading(False)
        self.load_more_btn.setEnabled(bool(self._next_cursor))
        self.status_lbl.setText(f"Search failed: {error}")
        self._refresh_summary()
        self._run_queued_search_if_any()

    def _should_prefetch_more(
        self,
        request: _SearchRequest,
        filtered_batch: list[HFModel],
        next_cursor: str | None,
    ) -> bool:
        if not next_cursor:
            return False
        if not category_uses_client_heuristic(request.category):
            return False
        return len(filtered_batch) < _SEARCH_PAGE_SIZE

    def _run_queued_search_if_any(self) -> None:
        queued = self._queued_request
        if queued is None:
            self._active_request = None
            return
        self._queued_request = None
        self._launch_search(queued, reset_buffer=True)

    def _search_status_text(self, term: str) -> str:
        if term:
            return f"Searching Hugging Face for '{term}'..."
        return "Searching Hugging Face for top GGUF models..."

    def _current_visible_model_count(self) -> int:
        size_idx = self.size_filter.currentIndex()
        if size_idx <= 0:
            return len(self.current_models)
        return sum(1 for model in self.current_models if self._matches_size(model, size_idx))

    def _format_result_status(self, *, total_count: int, visible_count: int, partial: bool) -> str:
        if total_count <= 0:
            return "No GGUF models found for that search."
        if partial:
            base = f"Showing {visible_count} visible result" + ("" if visible_count == 1 else "s")
            if visible_count != total_count:
                base += f" from {total_count} fetched"
            return base + ". Refining matches..."
        if visible_count != total_count:
            return f"Found {total_count} models ({visible_count} visible with current filters)."
        return f"Found {visible_count} models."

    def _render(self):
        if not self.current_models:
            self._rebuild_card_layout([])
            self._visible_model_count = 0
            self._refresh_summary()
            for card in self._cards.values():
                card.deleteLater()
            self._cards.clear()
            self._score_cache.clear()
            self._displayed_model_ids = ()
            return

        instance_ids = (
            list(self._connected_instance_ids)
            if self._connected_instance_ids is not None
            else self.store.all_instance_ids()
        )
        scoring_context = tuple(
            (iid, *self._instance_signature(self.store.get_state(iid)))
            for iid in instance_ids
        )
        model_scores: dict[str, float] = {}
        model_sort_ranks: dict[str, float] = {}
        score_labels: dict[str, list[dict] | None] = {}
        detail_messages: dict[str, str] = {}
        # Quality weights for ranking (higher is better intelligence/quality)
        QUANT_QUALITY = {
            "BF16": 100, "FP16": 100, "F16": 100,
            "Q8_0": 90, "Q6_K": 82, "Q5_K_M": 78, "Q5_K_S": 74, "Q5_0": 72,
            "Q4_K_M": 65, "Q4_K_S": 60, "Q4_0": 55,
            "IQ4_XS": 62, "IQ4_NL": 61,
            "Q3_K_L": 48, "Q3_K_M": 44, "Q3_K_S": 40,
            "IQ3_M": 46, "IQ3_S": 42, "IQ3_XXS": 38,
            "Q2_K": 25, "IQ2_M": 22, "IQ2_S": 20, "IQ2_XS": 18, "IQ2_XXS": 15,
        }

        for model in self.current_models:
            if getattr(model, "details_error", ""):
                model_scores[model.id] = 0.0
                score_labels[model.id] = []
                detail_messages[model.id] = model.details_error
                continue
            if model_requires_detail_fetch(model) or getattr(model, "details_loading", False):
                model_scores[model.id] = 0.0
                score_labels[model.id] = None
                continue

            model_signature = self._model_signature(model)
            cached = self._score_cache.get(model.id)
            if cached and cached.model_signature == model_signature and cached.scoring_context == scoring_context:
                model_scores[model.id] = cached.display_score
                model_sort_ranks[model.id] = cached.sort_rank
                score_labels[model.id] = self._thaw_cached_labels(cached.labels)
                continue

            max_score = 0.0
            max_rank = 0.0
            labels: list[dict] = []
            
            for iid in instance_ids:
                state = self.store.get_state(iid)
                if not (state and state.system):
                    continue

                best_file_match = None
                best_file_rank = -1.0
                
                files_to_test = model.files if model.files else [None]
                
                for f in files_to_test:
                    if f:
                        if not f.quantization:
                            continue

                        size_gb = f.size_bytes / (1024 ** 3)
                        if size_gb < 0.1 and model.params_b > 0:
                            size_gb = estimate_gguf_size_gb(model.params_b, f.quantization)
                        
                        if model.params_b > 0 and size_gb > 0.1:
                            expected = estimate_gguf_size_gb(model.params_b, f.quantization)
                            if size_gb < (expected * 0.7):
                                continue

                        quant = f.quantization
                        entry = CatalogEntry(
                            name=model.name,
                            provider=model.author,
                            params_b=model.params_b,
                            best_quant=quant,
                            memory_required_gb=size_gb + 0.3,
                            estimated_tps_7b=50.0,
                            gguf_sources=[model.id],
                        )
                    else:
                        continue
                    
                    scored = self.scorer.score(entry, state.system)
                    quality = QUANT_QUALITY.get(entry.best_quant, 0)
                    if not quality and "Q" in entry.best_quant: quality = 30
                    
                    if scored.score >= 40:
                        rank = scored.score + (quality * 2.0)
                    else:
                        rank = scored.score
                    
                    if rank > best_file_rank:
                        best_file_rank = rank
                        best_file_match = {
                            "iid": iid,
                            "score": scored.score,
                            "rank": rank,
                            "fit": _FIT_LABEL.get(scored.fit_level, "Fit Available"),
                            "level": _FIT_LEVEL.get(scored.fit_level, "info"),
                            "best_quant": entry.best_quant if f else None
                        }
                
                if best_file_match:
                    labels.append(best_file_match)
                    max_score = max(max_score, best_file_match["score"])
                    max_rank = max(max_rank, best_file_match["rank"])

            model_scores[model.id] = max_score
            model_sort_ranks[model.id] = max_rank
            score_labels[model.id] = labels
            self._score_cache[model.id] = _ModelScoreCacheEntry(
                model_signature=model_signature,
                scoring_context=scoring_context,
                sort_rank=max_rank,
                display_score=max_score,
                labels=self._freeze_cached_labels(labels),
            )

        display_models = list(self.current_models)
        size_idx = self.size_filter.currentIndex()
        if size_idx > 0:
            display_models = [model for model in display_models if self._matches_size(model, size_idx)]
        if self._current_sort_mode() == "best_fit":
            display_models.sort(
                key=lambda model: (
                    -model_sort_ranks.get(model.id, 0.0),
                    -model_scores.get(model.id, 0.0),
                    -model.downloads,
                    -model.likes,
                    model.name.lower(),
                )
            )
        elif self._current_sort_mode() == "downloads":
            display_models.sort(
                key=lambda model: (
                    -model.downloads,
                    -model.likes,
                    model.name.lower(),
                )
            )

        self._visible_model_count = len(display_models)
        self._adopt_default_selection(display_models)

        installing_by_model = {
            desc.repo_id: (desc.iid, desc.percent)
            for _key, desc in self.registry.active_items()
        }

        new_cards = {}
        for model in display_models:
            if model.id in self._cards:
                card = self._cards[model.id]
            else:
                card = ModelCard(model)
                card.details_clicked.connect(self._show_details)
                card.open_hf_clicked.connect(self._open_hf)
            
            card.set_selected(
                self.side_panel.current_model is not None
                and self.side_panel.current_model.id == model.id
            )
            score_state = score_labels.get(model.id)
            if score_state is None:
                card.set_scoring_pending()
            else:
                if detail_messages.get(model.id):
                    card.set_detail_error(detail_messages[model.id])
                elif score_state:
                    card.set_instance_scores(score_state)
                else:
                    card.set_score_unavailable("No compatible GGUF fit available.")
            if model.id in installing_by_model:
                iid, percent = installing_by_model[model.id]
                card.set_installing(iid, percent)
            else:
                card.clear_installing()

            new_cards[model.id] = card

        self._cards = {**self._cards, **new_cards}
        self._rebuild_card_layout(display_models)

        current_ids = {m.id for m in self.current_models}
        for mid, card in self._cards.items():
            if mid not in current_ids:
                card.deleteLater()
                self._score_cache.pop(mid, None)
        
        self._cards = new_cards
        self._refresh_summary(model_count=len(display_models))

    def _rebuild_card_layout(self, display_models: list[HFModel]) -> None:
        display_ids = tuple(model.id for model in display_models)
        if display_ids == self._displayed_model_ids:
            return

        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if not item:
                continue
            widget = item.widget()
            if widget:
                widget.setParent(None)

        for model in display_models:
            card = self._cards.get(model.id)
            if card is not None:
                self.list_lay.addWidget(card)
        self.list_lay.addStretch()
        self._displayed_model_ids = display_ids

    def _start_detail_fetch(self) -> None:
        if self._is_fetching_details or not self._detail_queue:
            return
        
        self._is_fetching_details = True
        self._fetch_next_detail()

    def _fetch_next_detail(self) -> None:
        if not self._detail_queue:
            self._is_fetching_details = False
            return
            
        mid = self._detail_queue.pop(0)
        # Check if model still exists in current search
        model = next((m for m in self.current_models if m.id == mid), None)
        if not model or not model_requires_detail_fetch(model) or getattr(model, "details_loading", False):
            self._fetch_next_detail()
            return
            
        worker = HFModelDetailWorker(mid, self)
        self._detail_worker = worker
        session_id = self._detail_session_id
        model.details_loading = True
        model.details_error = ""
        worker.finished.connect(lambda files, m=model, sid=session_id, mid=mid: self._on_bg_detail_finished(sid, mid, m, files))
        worker.error.connect(lambda message, m=model, sid=session_id, mid=mid: self._on_bg_detail_error(sid, mid, m, message))
        worker.start()

    def _on_bg_detail_finished(self, session_id: int, model_id: str, model: HFModel, files: list[HFModelFile]) -> None:
        self._detail_worker = None
        if session_id != self._detail_session_id:
            model.details_loading = False
            self._is_fetching_details = False
            self._start_detail_fetch()
            return
        model.files = files
        model.details_loading = False
        model.details_loaded = has_complete_file_metadata(files)
        model.details_error = "" if files else "Could not load GGUF file metadata."
        self._score_cache.pop(model.id, None)
        # Schedule a render to update the specific card
        self._schedule_render()
        # Continue queue
        self._fetch_next_detail()

    def _on_bg_detail_error(self, session_id: int, model_id: str, model: HFModel, message: str) -> None:
        self._detail_worker = None
        if session_id != self._detail_session_id:
            model.details_loading = False
            self._is_fetching_details = False
            self._start_detail_fetch()
            return
        model.details_loading = False
        model.details_error = message or "Could not load GGUF file metadata."
        self._score_cache.pop(model.id, None)
        self._schedule_render()
        self._fetch_next_detail()

    def _schedule_render(self) -> None:
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _set_search_loading(self, loading: bool) -> None:
        if loading:
            self.search_spinner.start()
        else:
            self.search_spinner.stop()

    @staticmethod
    def _freeze_cached_labels(labels: list[dict]) -> tuple[tuple[tuple[str, object], ...], ...]:
        return tuple(
            tuple(sorted(item.items()))
            for item in labels
        )

    @staticmethod
    def _thaw_cached_labels(labels: tuple[tuple[tuple[str, object], ...], ...]) -> list[dict]:
        return [dict(item) for item in labels]

    @staticmethod
    def _model_signature(model: HFModel) -> tuple:
        return (
            round(model.params_b, 3),
            tuple(
                sorted(
                    (item.filename, item.size_bytes, item.quantization)
                    for item in model.files
                )
            ),
        )

    def _get_best_fallback_quant(self, system, params_b: float) -> str:
        """Pick the best likely quantization that fits the given hardware as a fallback."""
        if params_b <= 0:
            return "Q4_K_M"
        
        # Available memory (VRAM or RAM)
        avail = (system.gpu_vram_gb or 0) if system.has_gpu else (system.ram_total_gb or 0)
        if avail <= 0:
            return "Q4_K_M"

        # Check from best to worst
        for q in ["BF16", "Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K"]:
            if avail >= estimate_gguf_size_gb(params_b, q):
                return q
        return "Q2_K"

    def _matches_size(self, model: HFModel, size_idx: int) -> bool:
        params = model.params_b
        if size_idx == 6:
            return params <= 0
        if params <= 0:
            return False
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
        self.close_panel_btn.setToolTip("Hide settings" if self.side_panel.isVisible() else "Show settings")

    def _adopt_default_selection(self, candidate_models: list[HFModel] | None = None) -> None:
        candidates = candidate_models if candidate_models is not None else self.current_models
        if not candidates:
            self.side_panel.clear()
            return
        current_id = self.side_panel.current_model.id if self.side_panel.current_model else None
        chosen = next((model for model in candidates if model.id == current_id), None)
        if chosen is None:
            chosen = candidates[0]
        if self.side_panel.current_model is None or self.side_panel.current_model.id != chosen.id:
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
        visible_models = model_count if model_count is not None else self._current_visible_model_count()

        if searching:
            self.status_lbl.setText(f"Searching {search_text}...")
        elif visible_models:
            noun = "model" if visible_models == 1 else "models"
            self.status_lbl.setText(f"{visible_models} {noun} loaded")
        else:
            self.status_lbl.setText("Search. Fit. Deploy.")

        self.summary_scope.setText(
            f"{len(connected_ids)} connected target" + ("" if len(connected_ids) == 1 else "s")
        )
        self.summary_ops.setText(
            f"{active_ops} active operation" + ("" if active_ops == 1 else "s")
        )
