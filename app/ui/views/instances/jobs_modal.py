from __future__ import annotations
import time
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget, QPushButton
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor

from app import theme as t
from app.ui.components.primitives import GlassCard, IconButton
from app.ui.components import icons
from app.lab.services.job_registry import JobRegistry


class JobProgressBar(QWidget):
    """Tiny custom horizontal progress bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self._percent = 0

    def set_percent(self, p: int):
        self._percent = max(0, min(100, p))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Track
        p.setBrush(QColor(t.SURFACE_3))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 4, 4)
        
        # Fill
        if self._percent > 0:
            width = int(self.width() * (self._percent / 100))
            if width > 0:
                p.setBrush(QColor(t.ACCENT))
                p.drawRoundedRect(0, 0, width, self.height(), 4, 4)


class JobsModal(QDialog):
    """A minimal floating modal showing all background jobs."""
    def __init__(self, registry: JobRegistry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.setWindowTitle("Global Active Jobs")
        self.resize(500, 450)
        self.setStyleSheet(t.STYLESHEET)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.cards_layout = None
        self._build_ui()
        self._refresh()

        # Check for dynamic updates
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

        # Wire close shortcut
        self.close_btn.clicked.connect(self.close)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        main_card = GlassCard()
        lay = main_card.body()
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(15)

        # Header
        header = QHBoxLayout()
        title = QLabel("Global Operations")
        title.setStyleSheet(f"color: {t.TEXT_HI}; font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        self.close_btn = IconButton(icons.CLOSE, "Close")
        header.addWidget(self.close_btn)
        lay.addLayout(header)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        
        scroll.setWidget(container)
        lay.addWidget(scroll)

        root.addWidget(main_card)

    def _refresh(self):
        if not self.isVisible() or not self.cards_layout:
            return

        # Clear existing
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active = self.registry.active_values()
        recent = getattr(self.registry, "_recent", [])

        if not active and not recent:
            empty = QLabel("No active or recent jobs.")
            empty.setStyleSheet(f"color: {t.TEXT_MID}; padding: 20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, empty)
            return

        for desc in active:
            self._add_job_card(desc, is_active=True)
            
        for desc in reversed(recent):
            self._add_job_card(desc, is_active=False)

    def _add_job_card(self, desc, is_active: bool):
        card = GlassCard()
        body = card.body()
        body.setContentsMargins(15, 15, 15, 15)

        top = QHBoxLayout()
        name = QLabel(f"{desc.filename}")
        name.setStyleSheet(f"color: {t.TEXT_HI}; font-weight: 800;")
        top.addWidget(name)
        top.addStretch()
        
        iid_lbl = QLabel(f"#{desc.iid}")
        iid_lbl.setStyleSheet(f"color: {t.TEXT_MID}; font-family: {t.FONT_MONO};")
        top.addWidget(iid_lbl)
        body.addLayout(top)

        bottom = QHBoxLayout()
        stage_lbl = QLabel(desc.stage.upper())
        stage_color = t.OK if desc.stage == "done" else t.ERR if desc.stage in ("failed", "cancelled") else t.ACCENT
        stage_lbl.setStyleSheet(f"color: {stage_color}; font-size: 11px; font-weight: bold;")
        bottom.addWidget(stage_lbl)
        
        if is_active:
            bottom.addWidget(QLabel(" • "))
            pct = QLabel(f"{desc.percent or 0}%")
            pct.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 11px;")
            bottom.addWidget(pct)
            
        bottom.addStretch()
        
        if hasattr(desc, "started_at") and desc.started_at:
            mins = int((time.time() - desc.started_at) / 60)
            dur = QLabel(f"{mins}m ago")
            dur.setStyleSheet(f"color: {t.TEXT_MID}; font-size: 11px;")
            bottom.addWidget(dur)
            
        body.addLayout(bottom)

        if is_active:
            prog = JobProgressBar()
            prog.set_percent(desc.percent or 0)
            body.addWidget(prog)

        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
