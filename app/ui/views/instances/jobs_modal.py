from __future__ import annotations
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton
)

from app import theme as t
from app.ui.components.primitives import GlassCard, IconButton, SkeletonBlock
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


class JobsModal(QWidget):
    """A minimal floating modal showing all background jobs."""
    def __init__(self, registry: JobRegistry, anchor=None, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.anchor = anchor
        self.setWindowTitle("Global Active Jobs")
        self.resize(500, 450)
        self.setObjectName("JobsModal")
        self.setStyleSheet("JobsModal { background: transparent; }")

        # Native Popup behavior (exactly like Chrome)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.cards_layout = None
        self._is_loading = True
        self._build_ui()
        
        # Render initial skeleton state
        for _ in range(3):
            self._add_skeleton_card()

        # Simulate brief loading delay to let the UI feel premium
        QTimer.singleShot(500, self._finish_loading)

        # Check for dynamic updates
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

        # Wire close shortcut
        self.close_btn.clicked.connect(self.close)

    def _finish_loading(self):
        self._is_loading = False
        self._refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self.anchor:
            pos = self.anchor.mapToGlobal(self.anchor.rect().bottomRight())
            # Align top-right of modal to bottom-right of button
            self.move(pos.x() - self.width(), pos.y() + 8)

    def paintEvent(self, event):
        # Ensure the 4 tiny corners outside the 8px border-radius are perfectly transparent
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.transparent)

    def _build_ui(self):
        root = QVBoxLayout(self)
        # ZERO margins! We do not reserve space for a custom shadow. This completely
        # eliminates the possibility of a dark bounding box leaking from the OS.
        root.setContentsMargins(0, 0, 0, 0)

        main_bg = QWidget()
        main_bg.setObjectName("JobsModalBg")
        main_bg.setStyleSheet(t.STYLESHEET + f"""
            QWidget#JobsModalBg {{
                background: {t.SURFACE_1};
                border: 1px solid {t.BORDER_LOW};
                border-radius: 8px;
            }}
            QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
        """)

        # No QGraphicsDropShadowEffect. We rely on the 1px border and native OS composite.
        
        lay = QVBoxLayout(main_bg)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(10)

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
        self.cards_layout.setContentsMargins(0, 0, 14, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        
        scroll.setWidget(container)
        lay.addWidget(scroll)

        root.addWidget(main_bg)

    def _refresh(self):
        if not self.isVisible() or not self.cards_layout:
            return
            
        if getattr(self, "_is_loading", False):
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

    def _add_skeleton_card(self):
        card = GlassCard()
        body = card.body()
        body.setContentsMargins(15, 15, 15, 15)

        top = QHBoxLayout()
        top.addWidget(SkeletonBlock(w=200, h=16))
        top.addStretch()
        top.addWidget(SkeletonBlock(w=80, h=14))
        body.addLayout(top)

        bottom = QHBoxLayout()
        bottom.addWidget(SkeletonBlock(w=50, h=12))
        bottom.addStretch()
        bottom.addWidget(SkeletonBlock(w=60, h=12))
        body.addLayout(bottom)

        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
