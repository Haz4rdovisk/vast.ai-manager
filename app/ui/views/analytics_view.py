"""Analytics view — Enterprise-grade cost intelligence dashboard.
3-tier layout: Hero metrics → Charts (50/50) → Tables (50/50).
All spending data is backed by persistent AnalyticsStore."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QGridLayout, QSizePolicy, QFrame, QPushButton, QComboBox,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QLinearGradient, QRadialGradient, QPainterPath,
)
from datetime import datetime, timedelta
from app import theme as t
from app.billing import (
    burn_rate_breakdown, total_burn_rate, project_balance,
    autonomy_hours, format_autonomy, BurnRateTracker,
)
from app.models import AppConfig, Instance, InstanceState, UserInfo
from app.analytics_store import AnalyticsStore
from app.ui.components.primitives import GlassCard, MetricTile


# ═══════════════════════════════════════════════════════════════════════════════
#  BalanceTimeline — area chart from persistent data
# ═══════════════════════════════════════════════════════════════════════════════

class BalanceTimeline(QWidget):
    """Area chart showing real balance over time from analytics store."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._points: list[tuple[str, float]] = []
        self._color = t.OK
        self._hours = 24
        self._forecast_hours = 0
        self._ymax_limit: float | None = None
        self._title = "Balance Timeline"

    def set_ymax_limit(self, val: float | None):
        self._ymax_limit = val
        self.update()

    def set_data(self, points: list[tuple[str, float]], color: str, hours: int = 24):
        self._points = points
        self._color = color
        self._hours = hours
        self.update()

    def set_forecast(self, hours: float):
        self._forecast_hours = max(0, hours)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 55, 16, 28, 24
        cw, ch = w - ml - mr, h - mt - mb

        # Background - Transparent to let GlassCard shine through
        # p.fillRect(0, 0, w, h, QColor(t.BG_VOID))

        if len(self._points) < 2:
            p.setPen(QColor(t.TEXT_LOW))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 9))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "Awaiting snapshots to build timeline...")
            p.end()
            return

        vals = [v for _, v in self._points]
        mn, mx = min(vals), max(vals)
        
        # Calculate final scale boundaries
        if self._ymax_limit and self._ymax_limit > mn:
            ymin, ymax = mn, self._ymax_limit
        else:
            pad = max(0.1, (mx - mn) * 0.15)
            ymin, ymax = mn - pad, mx + pad
        
        rng = ymax - ymin if ymax != ymin else 1.0

        # Grid
        grid_pen = QPen(QColor(255, 255, 255, 8), 1)
        p.setPen(grid_pen)
        for i in range(5):
            y = mt + ch * i / 4
            p.drawLine(ml, int(y), w - mr, int(y))

        # Y labels
        p.setPen(QColor(t.TEXT_LOW))
        p.setFont(QFont(t.FONT_MONO.split(",")[0], 8))
        for i in range(5):
            val = ymax - (ymax - ymin) * i / 4
            y = mt + ch * i / 4
            p.drawText(QRectF(0, y - 8, ml - 6, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"${val:.1f}")
        
        # Build points based on real time
        pts = []
        now = datetime.now()
        start_dt = now - timedelta(hours=self._hours)
        total_secs = self._hours * 3600

        for ts_str, val in self._points:
            try:
                dt = datetime.fromisoformat(ts_str)
                # Calculate X based on time position in the window (0.0 to 1.0)
                elapsed = (dt - start_dt).total_seconds()
                x_ratio = elapsed / total_secs
                x = ml + x_ratio * cw
                
                # Clamp X to chart area (in case of tiny clock drifts)
                x = max(ml, min(ml + cw, x))
                
                # Calculate Y
                y = mt + ch - ((val - ymin) / max(0.001, ymax - ymin)) * ch
                pts.append(QPointF(x, y))
            except Exception:
                continue

        if not pts:
            p.end()
            return

        # X labels (Fixed positions: Start, Mid, End of the WINDOW)
        p.setFont(QFont(t.FONT_MONO.split(",")[0], 7))
        p.setPen(QColor(t.TEXT_LOW))
        
        if self._hours < 24:
            labels = [
                (ml, (now - timedelta(hours=self._hours)).strftime("%H:%M")),
                (ml + cw/2, (now - timedelta(hours=self._hours/2)).strftime("%H:%M")),
                (ml + cw - 30, now.strftime("%H:%M"))
            ]
        else:
            labels = [
                (ml, (now - timedelta(hours=self._hours)).strftime("%d/%m %H:%M")),
                (ml + cw/2, (now - timedelta(hours=self._hours/2)).strftime("%d/%m %H:%M")),
                (ml + cw - 30, now.strftime("%d/%m %H:%M"))
            ]

        for x_pos, text in labels:
            p.drawText(QRectF(x_pos - 15, h - mb + 4, 50, 16), Qt.AlignCenter, text)

        # Line path
        line = QPainterPath()
        line.moveTo(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)

        # Fill
        fill = QPainterPath(line)
        fill.lineTo(QPointF(pts[-1].x(), mt + ch))
        fill.lineTo(QPointF(pts[0].x(), mt + ch))
        fill.closeSubpath()

        grad = QLinearGradient(0, mt, 0, mt + ch)
        grad.setColorAt(0.0, QColor(124, 92, 255, 50))
        grad.setColorAt(0.5, QColor(124, 92, 255, 15))
        grad.setColorAt(1.0, QColor(124, 92, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(fill)

        # Line
        p.setPen(QPen(QColor(t.ACCENT), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(line)

        # Final point dot with glow
        last = pts[-1] if pts else QPointF(0, 0)
        
        # Current Value Pulse
        p.setBrush(QColor(124, 92, 255, 60))
        p.setPen(Qt.NoPen)
        p.drawEllipse(last, 10, 10)
        p.setBrush(QColor(t.ACCENT))
        p.drawEllipse(last, 4, 4)

        # Forecasting Line (Enhanced Visibility)
        if self._forecast_hours > 0 and len(self._points) >= 2:
            # Draw a vibrant dashed line with glow
            forecast_pen = QPen(QColor(t.ACCENT), 2, Qt.DashLine)
            p.setPen(forecast_pen)
            
            # Predict trajectory: we draw towards zero balance (bottom of chart)
            f_px = cw * 0.20
            target_y = mt + ch # The "Zero" line
            
            # Sub-glow for the dashed line to make it pop
            glow_pen = QPen(QColor(124, 92, 255, 80), 4, Qt.DashLine)
            p.setPen(glow_pen)
            p.drawLine(last, QPointF(last.x() + f_px, target_y))
            
            p.setPen(forecast_pen)
            p.drawLine(last, QPointF(last.x() + f_px, target_y))

        # Title (Integrated)
        p.setPen(QColor(t.TEXT_MID))
        p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 10, QFont.Bold))
        p.drawText(QRectF(ml, 4, cw, 24), Qt.AlignLeft | Qt.AlignTop, self._title)

        # Current Value Highlight
        p.setPen(QColor(t.TEXT_HERO))
        p.setFont(QFont(t.FONT_MONO.split(",")[0], 12, QFont.Bold))
        p.drawText(QRectF(ml, 4, cw, 24), Qt.AlignRight | Qt.AlignTop,
                   f"${vals[-1]:.2f}")

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  DailySpendChart — bar chart for historical consumption
# ═══════════════════════════════════════════════════════════════════════════════

class DailySpendChart(QWidget):
    """Bar chart showing USD spent per day."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self._data: list[tuple[str, float]] = []
        self._title = "Daily Spend Pattern"

    def set_data(self, data: list[tuple[str, float]]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 45, 10, 28, 24
        cw, ch = w - ml - mr, h - mt - mb

        if not self._data:
            p.setPen(QColor(t.TEXT_LOW))
            p.drawText(self.rect(), Qt.AlignCenter, "No daily data yet")
            p.end()
            return

        # Scale
        vals = [v for _, v in self._data]
        mx = max(vals) * 1.1 if vals and max(vals) > 0 else 1.0

        # Draw Grid & Y Labels
        p.setFont(QFont(t.FONT_MONO.split(",")[0], 7))
        p.setPen(QPen(QColor(255, 255, 255, 8), 1))
        for i in range(4):
            y = mt + ch * i / 3
            p.drawLine(ml, int(y), w - mr, int(y))
            val = mx * (3 - i) / 3
            p.drawText(QRectF(0, y - 8, ml - 5, 16), Qt.AlignRight | Qt.AlignVCenter, f"${val:.1f}")

        # Draw Bars
        n = len(self._data)
        if n > 0:
            bar_gap = 8
            bar_w = (cw - (bar_gap * (n - 1))) / n if n > 1 else cw * 0.4
            
            for i, (label, val) in enumerate(self._data):
                bx = ml + i * (bar_w + bar_gap)
                bh = (val / mx) * ch
                by = mt + ch - bh
                
                rect = QRectF(bx, by, bar_w, bh)
                
                # Glass Bar
                grad = QLinearGradient(bx, by, bx, mt + ch)
                grad.setColorAt(0.0, QColor(t.ACCENT))
                grad.setColorAt(1.0, QColor(124, 92, 255, 40))
                p.setBrush(grad)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, 4, 4)
                
                # Label
                p.setPen(QColor(t.TEXT_LOW))
                p.drawText(QRectF(bx - 10, h - mb + 4, bar_w + 20, 16), Qt.AlignCenter, label)

        # Title
        p.setPen(QColor(t.TEXT_MID))
        p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 9, QFont.Bold))
        p.drawText(QRectF(ml, 4, cw, 20), Qt.AlignLeft, self._title)

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  CostComposition — horizontal bars for GPU/Storage/Network
# ═══════════════════════════════════════════════════════════════════════════════

class CostComposition(QWidget):
    """Horizontal bar chart: GPU vs Storage vs Network breakdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._gpu = 0.0
        self._storage = 0.0
        self._network = 0.0
        self._total = 0.0

    def set_values(self, gpu: float, storage: float, network: float):
        self._gpu = gpu
        self._storage = storage
        self._network = network
        self._total = gpu + storage + network
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background - Transparent
        # p.fillRect(0, 0, w, h, QColor(t.BG_VOID))

        # Title
        p.setPen(QColor(t.TEXT_MID))
        p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 9, QFont.Bold))
        p.drawText(QRectF(16, 4, w - 32, 20), Qt.AlignLeft, "Cost Composition")

        if self._total <= 0:
            p.setPen(QColor(t.TEXT_LOW))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 10))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "No active costs")
            p.end()
            return

        # Total + daily/monthly
        p.setPen(QColor(t.TEXT_HI))
        p.setFont(QFont(t.FONT_MONO.split(",")[0], 11, QFont.Bold))
        p.drawText(QRectF(16, 4, w - 32, 20), Qt.AlignRight,
                   f"${self._total:.3f}/h")

        items = [
            ("GPU Compute", self._gpu, QColor(124, 92, 255)),      # purple
            ("Storage", self._storage, QColor(90, 138, 255)),       # blue
            ("Network", self._network, QColor(50, 200, 180)),       # teal
        ]

        label_w = 110
        cost_w = 100
        bar_x = label_w + 12
        bar_w = w - bar_x - cost_w - 24
        row_h = 38
        start_y = 40

        for i, (name, value, color) in enumerate(items):
            y = start_y + i * (row_h + 8)
            pct = (value / self._total * 100) if self._total > 0 else 0

            # Label
            p.setPen(QColor(t.TEXT_HI))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 10))
            p.drawText(QRectF(16, y, label_w, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, name)

            # Bar track
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.SURFACE_3))
            p.drawRoundedRect(QRectF(bar_x, y + 11, bar_w, 14), 7, 7)

            # Bar fill
            fill_w = bar_w * min(1.0, pct / 100.0)
            if fill_w > 2:
                grad = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
                grad.setColorAt(0.0, color)
                faded = QColor(color)
                faded.setAlpha(150)
                grad.setColorAt(1.0, faded)
                p.setBrush(grad)
                p.drawRoundedRect(QRectF(bar_x, y + 11, fill_w, 14), 7, 7)

            # Cost + percentage
            p.setPen(color)
            p.setFont(QFont(t.FONT_MONO.split(",")[0], 10, QFont.Bold))
            p.drawText(QRectF(bar_x + bar_w + 8, y, cost_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"${value:.3f}/h")
            p.setPen(QColor(t.TEXT_MID))
            p.setFont(QFont(t.FONT_MONO.split(",")[0], 8))
            p.drawText(QRectF(bar_x + bar_w + 8, y + row_h / 2 - 2, cost_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{pct:.0f}%")

        # Bottom summary
        daily = self._total * 24
        monthly = daily * 30
        y_sum = start_y + 3 * (row_h + 8) + 4
        p.setPen(QColor(t.TEXT_MID))
        p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 9))
        p.drawText(QRectF(16, y_sum, w - 32, 20), Qt.AlignLeft,
                   f"Daily: ${daily:.2f}  ·  Monthly: ${monthly:.2f}")

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  InstanceCostBars — per-instance horizontal bars
# ═══════════════════════════════════════════════════════════════════════════════

class InstanceCostBars(QWidget):
    """Painted per-instance cost breakdown with storage line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []
        self._total = 0.0
        self.setMinimumHeight(40)

    def set_items(self, items: list[dict], total: float):
        self._items = items
        self._total = total
        self.setMinimumHeight(max(60, len(items) * 44 + 20))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()

        if not self._items:
            p.setPen(QColor(t.TEXT_LOW))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 10))
            p.drawText(QRectF(0, 0, w, self.height()), Qt.AlignCenter,
                       "No instances")
            p.end()
            return

        label_w = 100
        cost_w = 90
        bar_x = label_w + 8
        bar_w = w - bar_x - cost_w - 16
        row_h = 32

        for i, item in enumerate(self._items):
            y = i * (row_h + 4) + 2
            iid = str(item.get("id", "?"))
            gpu = item.get("gpu", "GPU")[:16]
            dph = item.get("dph", 0.0)
            stor = item.get("storage_h", 0.0)
            inst_total = dph + stor
            pct = (inst_total / self._total * 100) if self._total > 0 else 0

            # Label
            p.setPen(QColor(t.TEXT_HI))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 9, QFont.Bold))
            p.drawText(QRectF(0, y, label_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter, f"#{iid}")
            p.setPen(QColor(t.TEXT_MID))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 7))
            p.drawText(QRectF(0, y + row_h / 2 - 2, label_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter, gpu)

            # Bar track
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.SURFACE_3))
            p.drawRoundedRect(QRectF(bar_x, y + 9, bar_w, 12), 6, 6)

            # GPU fill
            gpu_w = bar_w * min(1.0, (dph / self._total)) if self._total > 0 else 0
            if gpu_w > 1:
                grad = QLinearGradient(bar_x, 0, bar_x + gpu_w, 0)
                grad.setColorAt(0.0, QColor(124, 92, 255))
                grad.setColorAt(1.0, QColor(90, 138, 255))
                p.setBrush(grad)
                p.drawRoundedRect(QRectF(bar_x, y + 9, gpu_w, 12), 6, 6)

            # Storage fill (stacked after GPU)
            if stor > 0:
                stor_w = bar_w * (stor / self._total) if self._total > 0 else 0
                if stor_w > 1:
                    p.setBrush(QColor(90, 138, 255, 100))
                    p.drawRoundedRect(
                        QRectF(bar_x + gpu_w, y + 9, stor_w, 12), 6, 6)

            # Cost
            p.setPen(QColor(t.ACCENT))
            p.setFont(QFont(t.FONT_MONO.split(",")[0], 9, QFont.Bold))
            p.drawText(QRectF(bar_x + bar_w + 6, y, cost_w, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"${inst_total:.3f}/h")

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  AnalyticsView — main 3-tier dashboard
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyticsView(QWidget):
    sync_requested = Signal()

    def __init__(self, config: AppConfig, analytics_store: AnalyticsStore | None = None, parent=None):
        super().__init__(parent)
        self._config = config
        self._store = analytics_store
        self._tracker = BurnRateTracker(window_size=10)
        
        self._last_instances: list[Instance] = []
        self._last_user: Optional[UserInfo] = None
        self._last_today = 0.0
        self._range_hours = 168  # 7 Days default para histórico
        self._line_hours = 6     # 6 Hours default para operacional
        self._mode = "FINANCE" # Fixed to finance for clarity

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_6, t.SPACE_5, t.SPACE_6, t.SPACE_4)
        root.setSpacing(t.SPACE_4)

        # Header
        head = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Analytics")
        title.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-size: {t.FONT_SIZE_DISPLAY}px;"
            f" font-weight: 700;"
        )
        sub = QLabel("Real-time cost intelligence")
        sub.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px;"
        )
        title_col.addWidget(title)
        title_col.addWidget(sub)
        head.addLayout(title_col)
        head.addStretch()

        # Data indicator
        self.data_lbl = QLabel("")
        self.data_lbl.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: {t.FONT_SIZE_SMALL}px;"
            f" font-family: {t.FONT_MONO};"
        )
        head.addWidget(self.data_lbl)
        root.addLayout(head)

        # Scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        self.clyt = QVBoxLayout(content)
        self.clyt.setContentsMargins(0, 0, t.SPACE_2, 0)
        self.clyt.setSpacing(t.SPACE_4)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        # ── TIER 1: Tiles (Hero Metrics) ──────────────────────────────
        t1 = QHBoxLayout()
        t1.setSpacing(t.SPACE_3)

        self.bal_tile = MetricTile("BALANCE", "$—")
        self.burn_tile = MetricTile("BURN RATE", "$0.000/h")
        self.today_tile = MetricTile("TODAY", "$0.00")
        self.week_tile = MetricTile("WEEK", "$0.00")
        self.auto_tile = MetricTile("AUTONOMY", "—")

        for tile in [self.bal_tile, self.burn_tile, self.today_tile, 
                     self.week_tile, self.auto_tile]:
            card = GlassCard()
            card.body().setContentsMargins(0, 0, 0, 0)
            card.body().addWidget(tile)
            t1.addWidget(card)
        
        self.clyt.addLayout(t1)
        self.clyt.addSpacing(t.SPACE_2)

        # ── TIER 2: Charts (Integrated Controls) ──────────────────────
        t2 = QHBoxLayout()
        t2.setSpacing(t.SPACE_3)

        # Chart 1: Timeline with independent Hour Filter
        timeline_card = GlassCard()
        tl_body = timeline_card.body()
        tl_body.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_4)
        
        tl_head = QHBoxLayout()
        tl_head.addStretch()
        
        # New Hour selector for Line Chart
        self.line_range_combo = QComboBox()
        self.line_range_combo.addItems(["1H", "3H", "6H", "12H", "24H", "SINCE RECHARGE"])
        self.line_range_combo.setCurrentIndex(2) # 6H
        self.line_range_combo.setFixedWidth(130)
        self.line_range_combo.setStyleSheet(self._combo_style())
        self.line_range_combo.currentIndexChanged.connect(self._on_line_range_changed)
        tl_head.addWidget(self.line_range_combo)

        # Sync Button
        self.sync_btn = QPushButton("Sync Now")
        self.sync_btn.setFixedWidth(80)
        self.sync_btn.setCursor(Qt.PointingHandCursor)
        self.sync_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.ACCENT}22;
                color: {t.ACCENT};
                border: 1px solid {t.ACCENT}44;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {t.ACCENT}44; }}
        """)
        self.sync_btn.currentIndexChanged = None # Fixed type error
        self.sync_btn.clicked.connect(self.sync_requested.emit)
        tl_head.addWidget(self.sync_btn)
        
        tl_body.addLayout(tl_head)
        
        self.timeline = BalanceTimeline()
        tl_body.addWidget(self.timeline)
        t2.addWidget(timeline_card, 1)

        # Chart 2: Historical Bars with independent Day Filter
        spend_card = GlassCard()
        sb_body = spend_card.body()
        sb_body.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_4)
        
        sb_head = QHBoxLayout()
        sb_head.addStretch()
        
        self.range_combo = QComboBox()
        self.range_combo.addItems(["24H", "7D", "30D"])
        self.range_combo.setCurrentIndex(1) # 7D
        self.range_combo.setFixedWidth(80)
        self.range_combo.setStyleSheet(self._combo_style())
        self.range_combo.currentIndexChanged.connect(self._on_bar_range_changed)
        sb_head.addWidget(self.range_combo)
        
        sb_body.addLayout(sb_head)
        
        self.spend_chart = DailySpendChart()
        sb_body.addWidget(self.spend_chart)
        t2.addWidget(spend_card, 1)
        
        self.clyt.addLayout(t2)

        # ── TIER 3: Tables & Composition ──────────────────────────────
        t3 = QHBoxLayout()
        t3.setSpacing(t.SPACE_3)

        # Left: Instance Breakdown + Composition
        breakdown_col = QVBoxLayout()
        breakdown_card = GlassCard()
        bl = breakdown_card.body()
        bl.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        bd_hdr = QLabel("Instance Breakdown")
        bd_hdr.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 600;"
            f" padding-bottom: 6px;"
        )
        bl.addWidget(bd_hdr)
        self.cost_bars = InstanceCostBars()
        bl.addWidget(self.cost_bars)
        breakdown_col.addWidget(breakdown_card, 2)
        
        comp_card = GlassCard()
        comp_card.body().setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        self.composition = CostComposition()
        self.composition.setMaximumHeight(100) # Compact for Tier 3
        comp_card.body().addWidget(self.composition)
        breakdown_col.addWidget(comp_card, 1)
        
        t3.addLayout(breakdown_col, 1)

        # Right: Projection
        proj_card = GlassCard()
        pl = proj_card.body()
        pl.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        pj_hdr = QLabel("Balance Projection")
        pj_hdr.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 600;"
            f" padding-bottom: 6px;"
        )
        pl.addWidget(pj_hdr)
        self.proj_grid = QGridLayout()
        self.proj_grid.setSpacing(0)
        for i, h in enumerate(["Period", "Balance", "Status"]):
            lbl = QLabel(h)
            lbl.setStyleSheet(
                f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_LABEL}px;"
                f" font-weight: 600; text-transform: uppercase;"
                f" padding: 8px 10px; background: {t.SURFACE_3};"
            )
            self.proj_grid.addWidget(lbl, 0, i)
        pl.addLayout(self.proj_grid)
        t3.addWidget(proj_card, 1)
        self.clyt.addLayout(t3)

        self.clyt.addStretch()

    # ── Public API ────────────────────────────────────────────────────

    def apply_config(self, config: AppConfig):
        self._config = config

    def set_store(self, store: AnalyticsStore):
        self._store = store

    def _on_line_range_changed(self, index: int):
        # Time range for operational LINE
        ranges = [1, 3, 6, 12, 24, -1]
        self._line_hours = ranges[index]
        self.sync(self._last_instances, self._last_user, self._last_today)

    def _on_bar_range_changed(self, index: int):
        ranges = [24, 168, 720]
        self._range_hours = ranges[index]
        self.sync(self._last_instances, self._last_user, self._last_today)

    def _toggle_mode(self):
        self._mode = "BURN" if self.mode_btn.isChecked() else "FINANCE"
        self.mode_btn.setText(self._mode)
        self.sync(self._last_instances, self._last_user, self._last_today)

    def _combo_style(self):
        return f"""
            QComboBox {{
                background: {t.SURFACE_3};
                border: 1px solid {t.SURFACE_1};
                border-radius: 4px;
                padding: 2px 8px;
                color: {t.TEXT_HI};
                font-size: 10px;
                font-weight: bold;
            }}
            QComboBox::drop-down {{ border: 0; width: 0px; }}
            QComboBox QAbstractItemView {{
                background: {t.SURFACE_2};
                border: 1px solid {t.SURFACE_1};
                color: {t.TEXT_HI};
                selection-background-color: {t.ACCENT};
            }}
        """

    def sync(self, instances: list[Instance], user: UserInfo | None,
             today_spend: float):
        # Security: Prevent crash if widget is being deleted during sync signal
        try:
            if not self.isVisible() and not self.parent():
                return
        except RuntimeError:
            return

        self._last_instances = instances
        self._last_user = user
        self._last_today = today_spend
        cfg = self._config
        bd = burn_rate_breakdown(
            instances,
            include_storage=cfg.include_storage_in_burn_rate,
            estimated_network_cost_per_hour=cfg.estimated_network_cost_per_hour,
        )
        balance = user.balance if user else 0.0
        hours = autonomy_hours(balance, bd["total"])
        smoothed = self._tracker.update(bd["total"])
        trend = self._tracker.get_trend()

        # TIER 1: Tiles
        self.bal_tile.set_value(f"${balance:.2f}")
        self.burn_tile.set_value(f"${bd['total']:.3f}/h {trend.arrow}")
        self.today_tile.set_value(f"${today_spend:.2f}")

        if self._store:
            week_spend = self._store.week_spend()
            self.week_tile.set_value(f"${week_spend:.2f}")

        if hours is not None:
            color = t.autonomy_color(hours)
            self.auto_tile.set_value(format_autonomy(hours))
            self.auto_tile.set_color(color)
            self.bal_tile.set_color(color)
        else:
            self.auto_tile.set_value("\u221e")
            self.auto_tile.set_color(t.OK)

        # TIER 2: Charts (Dual Engine)
        if self._store:
            # Operational Line (Current Window)
            line_hrs = self._line_hours if hasattr(self, "_line_hours") else 6
            recharge_val = self._store._last_recharge_val
            recharge_ts = self._store._last_recharge_ts
            
            # If SINCE RECHARGE (-1) is selected, calculate hours from last recharge
            is_cycle_view = line_hrs == -1
            if is_cycle_view:
                if recharge_ts > 0:
                    elapsed = (datetime.now() - datetime.fromtimestamp(recharge_ts)).total_seconds()
                    line_hrs = max(1, int(elapsed // 3600))
                    self.timeline.set_ymax_limit(recharge_val)
                    self.timeline._title = f"Cycle Tracker (Since ${recharge_val:.0f} Recharge)"
                else:
                    # Fallback to 24h if no recharge data
                    line_hrs = 24
                    self.timeline.set_ymax_limit(None)
                    self.timeline._title = "Balance Evolution (No Recharge Found)"
            else:
                self.timeline.set_ymax_limit(None)
                self.timeline._title = "Balance Evolution"

            if self._mode == "FINANCE":
                line_data = self._store.balance_timeline(line_hrs)
                self.timeline.set_data(line_data, t.OK, line_hrs)
                self.timeline.set_forecast(today_spend)
            else:
                line_data = self._store.burn_rate_timeline(line_hrs)
                self.timeline.set_data(line_data, t.ACCENT, line_hrs)
                self.timeline.set_forecast(0)
            
            # Historical Bars (Global Range)
            daily_data = self._store.daily_spend_history(max(1, self._range_hours // 24))
            self.spend_chart.set_data(daily_data)
            
            self.data_lbl.setText(
                f"{self._store.entry_count} snapshots logged"
            )

        self.composition.set_values(bd["gpu"], bd["storage"], bd["network"])
        self._last_today = today_spend

        # TIER 3: Instance bars
        self.cost_bars.set_items(bd["instances"], bd["total"])

        # Projection table
        _clear_grid(self.proj_grid, 1)
        if bd["total"] > 0 and balance > 0:
            for r, (label, hrs) in enumerate([
                ("24 hours", 24), ("3 days", 72), ("7 days", 168),
                ("14 days", 336), ("30 days", 720),
            ], start=1):
                proj = project_balance(balance, bd["total"], hrs)
                bal = proj["balance"]
                if bal > 10:
                    status, clr = "OK", t.OK
                elif bal > 0:
                    status, clr = "LOW", t.WARN
                else:
                    status, clr = "DEPLETED", t.ERR

                bg = t.SURFACE_1 if r % 2 == 0 else "transparent"
                s = f"padding: 7px 10px; background: {bg};"
                _cell(self.proj_grid, r, 0, label, s)
                _cell(self.proj_grid, r, 1, f"${bal:.2f}", s,
                      color=t.TEXT_HI, mono=True)
                _cell(self.proj_grid, r, 2, status, s, color=clr)


# ── Helpers ──

def _clear_grid(grid: QGridLayout, start_row: int):
    to_del = []
    for i in range(grid.count()):
        item = grid.itemAt(i)
        if item and item.widget():
            row, *_ = grid.getItemPosition(i)
            if row >= start_row:
                to_del.append(item.widget())
    for w in to_del:
        grid.removeWidget(w)
        w.deleteLater()


def _cell(grid, row, col, text, style, color=None, mono=False):
    lbl = QLabel(text)
    c = color or t.TEXT
    extra = f" font-family: {t.FONT_MONO};" if mono else ""
    lbl.setStyleSheet(f"color: {c};{extra} {style}")
    grid.addWidget(lbl, row, col)
