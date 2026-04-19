"""Analytics view — fleet-level cost intelligence dashboard.
Metrics and charts are backed by persistent AnalyticsStore billing data."""
from __future__ import annotations

import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QGridLayout, QSizePolicy, QFrame, QComboBox, QToolTip,
)
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QLinearGradient, QPainterPath,
)
from datetime import datetime, timedelta
from typing import Optional
from app import theme as t
from app.billing import (
    burn_rate_breakdown, autonomy_hours, format_autonomy, BurnRateTracker,
)
from app.models import AppConfig, Instance, InstanceState, UserInfo
from app.analytics_store import AnalyticsStore
from app.ui.components.primitives import GlassCard, MetricTile


CARD_TITLE_HEIGHT = 24


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
        self._forecast_burn_per_hour = 0.0
        self._ymax_limit: float | None = None
        self._ymin_limit: float | None = 0.0
        self._title = "Balance Timeline"

    def set_ymax_limit(self, val: float | None):
        self._ymax_limit = val
        self.update()

    def set_ymin_limit(self, val: float | None):
        self._ymin_limit = val
        self.update()

    def set_data(self, points: list[tuple[str, float]], color: str, hours: int = 24):
        self._points = points
        self._color = color
        self._hours = hours
        self.update()

    def set_forecast(self, burn_per_hour: float):
        self._forecast_burn_per_hour = max(0.0, burn_per_hour)
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
        last_value = vals[-1]
        has_forecast = self._forecast_burn_per_hour > 0 and last_value > 0
        hours_to_zero = (
            last_value / self._forecast_burn_per_hour
            if has_forecast else 0.0
        )
        forecast_span_hours = min(max(self._hours * 0.25, 1.0), hours_to_zero) if has_forecast else 0.0
        forecast_value = max(0.0, last_value - self._forecast_burn_per_hour * forecast_span_hours)
        chart_vals = vals + ([forecast_value] if has_forecast else [])
        mn, mx = min(chart_vals), max(chart_vals)
        
        ymin, ymax = _chart_axis_bounds(chart_vals, self._ymin_limit, self._ymax_limit)
        
        data_cw = cw * (0.84 if has_forecast else 1.0)
        forecast_cw = cw - data_cw

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
                       Qt.AlignRight | Qt.AlignVCenter, _format_axis_money(val))
        
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
                x = ml + x_ratio * data_cw
                
                # Clamp X to chart area (in case of tiny clock drifts)
                x = max(ml, min(ml + data_cw, x))
                
                # Calculate Y. Clamp values to the visible axis so a partial
                # billing reconstruction cannot pull a money chart below $0.
                plot_val = max(ymin, min(val, ymax))
                y = mt + ch - ((plot_val - ymin) / max(0.001, ymax - ymin)) * ch
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
                (ml + data_cw/2, (now - timedelta(hours=self._hours/2)).strftime("%H:%M")),
                (ml + data_cw - 30, now.strftime("%H:%M"))
            ]
        else:
            labels = [
                (ml, (now - timedelta(hours=self._hours)).strftime("%d/%m %H:%M")),
                (ml + data_cw/2, (now - timedelta(hours=self._hours/2)).strftime("%d/%m %H:%M")),
                (ml + data_cw - 30, now.strftime("%d/%m %H:%M"))
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

        line_color = QColor(self._color)
        grad = QLinearGradient(0, mt, 0, mt + ch)
        top_fill = QColor(line_color)
        top_fill.setAlpha(48)
        mid_fill = QColor(line_color)
        mid_fill.setAlpha(14)
        bot_fill = QColor(line_color)
        bot_fill.setAlpha(0)
        grad.setColorAt(0.0, top_fill)
        grad.setColorAt(0.5, mid_fill)
        grad.setColorAt(1.0, bot_fill)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(fill)

        # Line
        p.setPen(QPen(line_color, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(line)

        # Final point dot with glow
        last = pts[-1] if pts else QPointF(0, 0)
        
        # Current Value Pulse
        dot_glow = QColor(line_color)
        dot_glow.setAlpha(60)
        p.setBrush(dot_glow)
        p.setPen(Qt.NoPen)
        p.drawEllipse(last, 10, 10)
        p.setBrush(line_color)
        p.drawEllipse(last, 4, 4)

        if has_forecast and forecast_cw > 8:
            p.setPen(QPen(QColor(255, 255, 255, 16), 1, Qt.DashLine))
            p.drawLine(QPointF(ml + data_cw, mt), QPointF(ml + data_cw, mt + ch))

            forecast_x = min(ml + cw, last.x() + forecast_cw * 0.9)
            forecast_y = mt + ch - ((forecast_value - ymin) / max(0.001, ymax - ymin)) * ch
            target = QPointF(forecast_x, forecast_y)

            glow_pen = QPen(QColor(line_color.red(), line_color.green(), line_color.blue(), 80), 4, Qt.DashLine)
            p.setPen(glow_pen)
            p.drawLine(last, target)
            p.setPen(QPen(line_color, 2, Qt.DashLine))
            p.drawLine(last, target)

            p.setPen(QColor(t.TEXT_LOW))
            p.setFont(QFont(t.FONT_MONO.split(",")[0], 7))
            p.drawText(
                QRectF(ml + data_cw + 4, h - mb + 4, forecast_cw - 4, 16),
                Qt.AlignCenter,
                f"{format_autonomy(hours_to_zero)}",
            )

        # Title (Integrated)
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
        self.setMouseTracking(True)
        self.setMinimumHeight(190)
        self._data: list[tuple[str, float]] = []
        self._title = "Daily Spend Pattern"
        self._bar_hits: list[tuple[QRectF, str, float]] = []

    def set_data(self, data: list[tuple[str, float]]):
        self._data = data
        self.update()

    def set_title(self, title: str):
        self._title = title
        self.update()

    def total(self) -> float:
        return round(sum(v for _, v in self._data), 4)

    def mouseMoveEvent(self, event):
        for rect, label, value in self._bar_hits:
            if rect.contains(event.position()):
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{label}\nSpend: ${value:.3f}",
                    self,
                )
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 45, 10, 28, 24
        cw, ch = w - ml - mr, h - mt - mb

        if not self._data:
            self._bar_hits = []
            p.setPen(QColor(t.TEXT_LOW))
            p.drawText(self.rect(), Qt.AlignCenter, "No daily data yet")
            p.end()
            return

        # Scale
        vals = [v for _, v in self._data]
        mx = max(vals) * 1.1 if vals and max(vals) > 0 else 1.0
        self._bar_hits = []

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
            bar_gap = 4 if n > 12 else 8
            bar_w = (cw - (bar_gap * (n - 1))) / n if n > 1 else cw * 0.4
            label_step = max(1, math.ceil(n / 8))
            
            for i, (label, val) in enumerate(self._data):
                bx = ml + i * (bar_w + bar_gap)
                bh = (val / mx) * ch
                by = mt + ch - bh
                
                rect = QRectF(bx, by, bar_w, bh)
                hit_rect = QRectF(bx, mt, bar_w, ch)
                self._bar_hits.append((hit_rect, label, val))
                
                # Glass Bar
                grad = QLinearGradient(bx, by, bx, mt + ch)
                grad.setColorAt(0.0, QColor(t.ACCENT))
                accent_fade = QColor(t.ACCENT); accent_fade.setAlpha(40)
                grad.setColorAt(1.0, accent_fade)
                p.setBrush(grad)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, 4, 4)
                
                # Label
                if i % label_step == 0 or i == n - 1:
                    p.setPen(QColor(t.TEXT_LOW))
                    p.drawText(QRectF(bx - 16, h - mb + 4, bar_w + 32, 16), Qt.AlignCenter, label)

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  CostComposition — horizontal bars for GPU/Storage/Network
# ═══════════════════════════════════════════════════════════════════════════════

class CostComposition(QWidget):
    """Horizontal bar chart: GPU vs Storage vs Network breakdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._gpu = 0.0
        self._storage = 0.0
        self._network = 0.0
        self._total = 0.0
        self._bar_hits: list[tuple[QRectF, str, float, float]] = []

    def set_values(self, gpu: float, storage: float, network: float):
        self._gpu = gpu
        self._storage = storage
        self._network = network
        self._total = gpu + storage + network
        self.update()

    def mouseMoveEvent(self, event):
        for rect, name, value, pct in self._bar_hits:
            if rect.contains(event.position()):
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{name}\nRate: ${value:.4f}/h\nShare: {pct:.1f}%",
                    self,
                )
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        self._bar_hits = []

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
            ("GPU Compute", self._gpu, QColor(t.ACCENT)),
            ("Storage", self._storage, QColor(t.ACCENT_END)),
            ("Network", self._network, QColor(t.LIVE)),
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
            bar_rect = QRectF(bar_x, y + 11, bar_w, 14)
            self._bar_hits.append((QRectF(bar_x, y, bar_w, row_h), name, value, pct))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.SURFACE_3))
            p.drawRoundedRect(bar_rect, 7, 7)

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

    _MIN_VISIBLE_ROWS = 6
    _ROW_H = 32
    _MIN_ROW_SLOT = 42
    _TOP_PAD = 12
    _BOTTOM_PAD = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._items: list[dict] = []
        self._total = 0.0
        self._bar_hits: list[tuple[QRectF, dict, float, float]] = []
        self._placeholder_rows = self._MIN_VISIBLE_ROWS
        self.setMinimumHeight(40)

    def set_items(self, items: list[dict], total: float):
        ranked = sorted(
            items,
            key=lambda item: float(item.get("dph") or 0.0) + float(item.get("storage_h") or 0.0),
            reverse=True,
        )
        visible = ranked
        if len(ranked) > 8:
            rest = ranked[8:]
            visible = ranked[:8] + [{
                "id": f"+{len(rest)}",
                "gpu": "Other instances",
                "dph": sum(float(item.get("dph") or 0.0) for item in rest),
                "storage_h": sum(float(item.get("storage_h") or 0.0) for item in rest),
                "state": "mixed",
            }]
        visible_total = sum(
            float(item.get("dph") or 0.0) + float(item.get("storage_h") or 0.0)
            for item in ranked
        )
        self._items = visible
        self._total = max(0.0, float(total or 0.0), visible_total)
        self._placeholder_rows = max(0, self._MIN_VISIBLE_ROWS - len(visible))
        row_count = len(visible) + self._placeholder_rows
        self.setMinimumHeight(
            max(
                90,
                self._TOP_PAD + row_count * self._MIN_ROW_SLOT + self._BOTTOM_PAD,
            )
        )
        self.update()

    def mouseMoveEvent(self, event):
        for rect, item, inst_total, pct in self._bar_hits:
            if rect.contains(event.position()):
                iid = item.get("id", "?")
                gpu = item.get("gpu", "GPU")
                dph = float(item.get("dph") or 0.0)
                storage = float(item.get("storage_h") or 0.0)
                state = str(item.get("state") or "unknown")
                title = f"{iid} · {gpu}" if str(iid).startswith("+") else f"Instance #{iid} · {gpu}"
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    (
                        f"{title}\n"
                        f"Total: ${inst_total:.4f}/h ({pct:.1f}%)\n"
                        f"GPU: ${dph:.4f}/h\n"
                        f"Storage: ${storage:.4f}/h\n"
                        f"State: {state}"
                    ),
                    self,
                )
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        self._bar_hits = []

        label_w = 108
        cost_w = 90
        bar_x = label_w + 8
        bar_w = w - bar_x - cost_w - 16
        row_h = self._ROW_H
        total_rows = max(1, len(self._items) + self._placeholder_rows)
        available_h = max(row_h, h - self._TOP_PAD - self._BOTTOM_PAD)
        row_slot = max(self._MIN_ROW_SLOT, available_h / total_rows)

        for i, item in enumerate(self._items):
            y = self._TOP_PAD + i * row_slot
            iid = str(item.get("id", "?"))
            gpu = item.get("gpu", "GPU")[:16]
            dph = item.get("dph", 0.0)
            stor = item.get("storage_h", 0.0)
            inst_total = dph + stor
            pct = (inst_total / self._total * 100) if self._total > 0 else 0
            id_label = iid if iid.startswith("+") else f"#{iid}"

            # Label
            p.setPen(QColor(t.TEXT_HI))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 9, QFont.Bold))
            p.drawText(QRectF(0, y, label_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter, id_label)
            p.setPen(QColor(t.TEXT_MID))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 7))
            p.drawText(QRectF(0, y + row_h / 2 - 2, label_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter, gpu)

            # Bar track
            bar_hit = QRectF(bar_x, y, bar_w, row_h)
            self._bar_hits.append((bar_hit, item, inst_total, pct))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.SURFACE_3))
            p.drawRoundedRect(QRectF(bar_x, y + 9, bar_w, 12), 6, 6)

            # GPU fill
            gpu_w = bar_w * min(1.0, (dph / self._total)) if self._total > 0 else 0
            if gpu_w > 1:
                grad = QLinearGradient(bar_x, 0, bar_x + gpu_w, 0)
                grad.setColorAt(0.0, QColor(t.ACCENT))
                grad.setColorAt(1.0, QColor(t.ACCENT_END))
                p.setBrush(grad)
                p.drawRoundedRect(QRectF(bar_x, y + 9, gpu_w, 12), 6, 6)

            # Storage fill (stacked after GPU)
            if stor > 0:
                stor_w = bar_w * (stor / self._total) if self._total > 0 else 0
                if stor_w > 1:
                    stor_col = QColor(t.ACCENT_END); stor_col.setAlpha(100)
                    p.setBrush(stor_col)
                    p.drawRoundedRect(
                        QRectF(bar_x + gpu_w, y + 9, stor_w, 12), 6, 6)

            # Cost
            p.setPen(QColor(t.ACCENT))
            p.setFont(QFont(t.FONT_MONO.split(",")[0], 9, QFont.Bold))
            p.drawText(QRectF(bar_x + bar_w + 6, y, cost_w, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"${inst_total:.3f}/h")

        if self._placeholder_rows:
            self._draw_placeholder_rows(
                p,
                w,
                len(self._items),
                label_w=label_w,
                cost_w=cost_w,
                row_h=row_h,
                row_slot=row_slot,
            )

        p.end()

    def _draw_placeholder_rows(
        self,
        p: QPainter,
        w: int,
        start_index: int,
        *,
        label_w: int,
        cost_w: int,
        row_h: int,
        row_slot: float,
    ):
        bar_x = label_w + 8
        bar_w = w - bar_x - cost_w - 16
        rows = self._placeholder_rows
        for offset in range(rows):
            i = start_index + offset
            y = self._TOP_PAD + i * row_slot
            alpha = max(22, 48 - offset * 8)

            p.setPen(QColor(139, 151, 180, alpha + 22))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 9, QFont.Bold))
            p.drawText(QRectF(0, y, label_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter, "Pending")
            p.setPen(QColor(139, 151, 180, alpha))
            p.setFont(QFont(t.FONT_DISPLAY.split(",")[0], 7))
            p.drawText(QRectF(0, y + row_h / 2 - 2, label_w, row_h / 2),
                       Qt.AlignLeft | Qt.AlignVCenter, "Next instance")

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, alpha))
            p.drawRoundedRect(QRectF(bar_x, y + 9, bar_w, 12), 6, 6)

            p.setPen(QColor(139, 151, 180, alpha))
            p.setFont(QFont(t.FONT_MONO.split(",")[0], 9, QFont.Bold))
            p.drawText(QRectF(bar_x + bar_w + 6, y, cost_w, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, "$--/h")


# ═══════════════════════════════════════════════════════════════════════════════
#  AnalyticsView — main 3-tier dashboard
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyticsView(QWidget):
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
        self.summary_cards: list[GlassCard] = []
        self._summary_cols: int | None = None

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
        sub = QLabel("Fleet cost intelligence")
        sub.setStyleSheet(
            f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px;"
        )
        title_col.addWidget(title)
        title_col.addWidget(sub)
        head.addLayout(title_col)
        head.addStretch()

        # Data indicator kept for internal sync state; not shown as a loose tag.
        self.data_lbl = QLabel("")
        self.data_lbl.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: {t.FONT_SIZE_SMALL}px;"
            f" font-family: {t.FONT_MONO};"
        )
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
        t1 = QGridLayout()
        t1.setHorizontalSpacing(t.SPACE_3)
        t1.setVerticalSpacing(t.SPACE_3)

        self.bal_tile = MetricTile("BALANCE", "$—")
        self.burn_tile = MetricTile("BURN RATE", "$0.000/h")
        self.today_tile = MetricTile("TODAY", "$0.00")
        self.week_tile = MetricTile("WEEK", "$0.00")
        self.month_tile = MetricTile("MONTH", "$0.00")
        self.auto_tile = MetricTile("AUTONOMY", "—")
        self.running_tile = MetricTile("RUNNING", "0/0")
        self.util_tile = MetricTile("GPU LOAD", "—")

        for idx, tile in enumerate([
            self.bal_tile, self.burn_tile, self.today_tile, self.week_tile,
            self.month_tile, self.auto_tile, self.running_tile, self.util_tile,
        ]):
            t1.addWidget(tile, idx // 4, idx % 4)
        
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
        self.timeline_title_lbl = _card_title("Balance Evolution")
        tl_head.addWidget(self.timeline_title_lbl)
        tl_head.addStretch()
        
        # New Hour selector for Line Chart
        self.line_range_combo = QComboBox()
        self.line_range_combo.addItems(["1H", "3H", "6H", "12H", "24H", "SINCE RECHARGE"])
        self.line_range_combo.setCurrentIndex(2) # 6H
        self.line_range_combo.setFixedWidth(130)
        self.line_range_combo.currentIndexChanged.connect(self._on_line_range_changed)
        tl_head.addWidget(self.line_range_combo)

        tl_body.addLayout(tl_head)
        
        self.timeline = BalanceTimeline()
        tl_body.addWidget(self.timeline)
        t2.addWidget(timeline_card, 1)

        # Chart 2: Historical Bars with independent Day Filter
        spend_card = GlassCard()
        sb_body = spend_card.body()
        sb_body.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_4)
        
        sb_head = QHBoxLayout()
        self.spend_title_lbl = _card_title("Daily Spend")
        self.spend_total_lbl = _card_value("$0.00")
        sb_head.addWidget(self.spend_title_lbl)
        sb_head.addStretch()
        sb_head.addWidget(self.spend_total_lbl)
        
        self.range_combo = QComboBox()
        self.range_combo.addItems(["24H", "7D", "30D"])
        self.range_combo.setCurrentIndex(1) # 7D
        self.range_combo.setFixedWidth(80)
        self.range_combo.currentIndexChanged.connect(self._on_bar_range_changed)
        sb_head.addWidget(self.range_combo)
        
        sb_body.addLayout(sb_head)
        
        self.spend_chart = DailySpendChart()
        sb_body.addWidget(self.spend_chart)
        t2.addWidget(spend_card, 1)
        
        self.clyt.addLayout(t2)

        # ── TIER 3: Fleet cost allocation ─────────────────────────────
        t3 = QHBoxLayout()
        t3.setSpacing(t.SPACE_3)

        breakdown_card = GlassCard()
        bl = breakdown_card.body()
        bl.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        bl.addWidget(_card_title("Cost by Instance"))
        self.cost_bars = InstanceCostBars()
        bl.addWidget(_scroll_viewport(self.cost_bars, 286))
        t3.addWidget(breakdown_card, 1)
        
        comp_card = GlassCard()
        comp_card.body().setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        comp_card.body().addWidget(_card_title("Cost Composition"))
        self.composition = CostComposition()
        self.composition.setMinimumHeight(260)
        comp_card.body().addWidget(_scroll_viewport(self.composition, 286))
        t3.addWidget(comp_card, 1)
        self.clyt.addLayout(t3)

        # ── TIER 4: Fleet intelligence summary ───────────────────────
        health_card = GlassCard()
        hl = health_card.body()
        hl.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        hl.addWidget(_card_title("Fleet Health"))
        self.health_grid = QGridLayout()
        self.health_grid.setHorizontalSpacing(t.SPACE_3)
        self.health_grid.setVerticalSpacing(t.SPACE_2)
        self.health_labels: dict[str, QLabel] = {}
        for row, (key, label) in enumerate([
            ("instances", "Instances"),
            ("gpus", "GPUs"),
            ("gpu", "GPU utilization"),
            ("cpu", "CPU utilization"),
            ("vram", "VRAM used"),
            ("ram", "RAM used"),
            ("disk", "Disk allocated"),
            ("network", "Network now"),
            ("billed", "Network billed"),
            ("temp", "Max GPU temp"),
            ("reliability", "Avg reliability"),
        ]):
            _metric_row(self.health_grid, self.health_labels, row, key, label)
        hl.addLayout(self.health_grid)

        billing_card = GlassCard()
        bil = billing_card.body()
        bil.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        self.billing_title_lbl = _card_title("Billing")
        bil.addWidget(self.billing_title_lbl)
        self.billing_grid = QGridLayout()
        self.billing_grid.setHorizontalSpacing(t.SPACE_3)
        self.billing_grid.setVerticalSpacing(t.SPACE_2)
        self.billing_labels: dict[str, QLabel] = {}
        for row, (key, label) in enumerate([
            ("sync", "Last sync"),
            ("records", "Records"),
            ("charges", "Charges"),
            ("credits", "Credits"),
            ("gpu", "GPU spend"),
            ("storage", "Storage"),
            ("network", "Bandwidth"),
            ("top", "Top source"),
        ]):
            _metric_row(self.billing_grid, self.billing_labels, row, key, label)
        bil.addLayout(self.billing_grid)

        efficiency_card = GlassCard()
        el = efficiency_card.body()
        el.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        el.addWidget(_card_title("Economic Efficiency"))
        self.efficiency_grid = QGridLayout()
        self.efficiency_grid.setHorizontalSpacing(t.SPACE_3)
        self.efficiency_grid.setVerticalSpacing(t.SPACE_2)
        self.efficiency_labels: dict[str, QLabel] = {}
        for row, (key, label) in enumerate([
            ("gpu_cost", "Cost / GPU"),
            ("vram_cost", "Cost / GB VRAM"),
            ("tflop_cost", "Cost / TFLOP"),
            ("perf_dollar", "Performance / $"),
            ("risk_rate", "Reliability-adjusted"),
            ("discount", "Discounted rate"),
            ("storage_price", "Storage price"),
            ("verified", "Verified hosts"),
        ]):
            _metric_row(self.efficiency_grid, self.efficiency_labels, row, key, label)
        el.addLayout(self.efficiency_grid)

        ranking_card = GlassCard()
        rl = ranking_card.body()
        rl.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        rl.addWidget(_card_title("Efficiency Ranking"))
        self.ranking_grid = QGridLayout()
        self.ranking_grid.setHorizontalSpacing(t.SPACE_3)
        self.ranking_grid.setVerticalSpacing(t.SPACE_2)
        self.ranking_labels: dict[str, QLabel] = {}
        for row, (key, label) in enumerate([
            ("best", "Best value"),
            ("worst", "Worst value"),
            ("highest_cost", "Highest cost"),
            ("lowest_reliability", "Lowest reliability"),
            ("idle", "Idle burn"),
            ("alert", "Alert"),
        ]):
            _metric_row(self.ranking_grid, self.ranking_labels, row, key, label)
        rl.addLayout(self.ranking_grid)

        self.summary_grid = QGridLayout()
        self.summary_grid.setHorizontalSpacing(t.SPACE_3)
        self.summary_grid.setVerticalSpacing(t.SPACE_3)
        self.summary_cards = [health_card, billing_card, efficiency_card, ranking_card]
        for card in self.summary_cards:
            card.setMinimumWidth(280)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.clyt.addLayout(self.summary_grid)
        self._arrange_summary_cards(force_cols=4)

        self.clyt.addStretch()

    # ── Public API ────────────────────────────────────────────────────

    def apply_config(self, config: AppConfig):
        self._config = config

    def set_store(self, store: AnalyticsStore):
        self._store = store

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._arrange_summary_cards)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_summary_cards()

    def _summary_width(self) -> int:
        viewport = self.scroll.viewport().width() if hasattr(self, "scroll") else 0
        if viewport <= 0:
            viewport = self.width()
        return max(0, viewport - t.SPACE_2)

    def _summary_column_count(self, width: int | None = None) -> int:
        width = self._summary_width() if width is None else width
        if width >= 1240:
            return 4
        if width >= 720:
            return 2
        return 1

    def _arrange_summary_cards(self, force_cols: int | None = None):
        if not hasattr(self, "summary_grid"):
            return
        cols = force_cols or self._summary_column_count()
        if cols == self._summary_cols and self.summary_grid.count():
            return
        self._summary_cols = cols

        while self.summary_grid.count():
            self.summary_grid.takeAt(0)

        for index, card in enumerate(self.summary_cards):
            row = index // cols
            col = index % cols
            self.summary_grid.addWidget(card, row, col)

        for c in range(4):
            self.summary_grid.setColumnStretch(c, 0)
        for c in range(cols):
            self.summary_grid.setColumnStretch(c, 1)

    def _on_line_range_changed(self, index: int):
        # Time range for operational LINE
        ranges = [1, 3, 6, 12, 24, -1]
        self._line_hours = ranges[index]
        self.sync(self._last_instances, self._last_user, self._last_today)

    def _on_bar_range_changed(self, index: int):
        ranges = [24, 168, 720]
        self._range_hours = ranges[index]
        self.sync(self._last_instances, self._last_user, self._last_today)

    def sync(self, instances: list[Instance], user: UserInfo | None,
             today_spend: float,
             week_spend: float | None = None,
             month_spend: float | None = None):
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
        smoothed = self._tracker.update(bd["total"])
        trend = self._tracker.get_trend()
        display_burn = smoothed if smoothed > 0 else bd["total"]
        running_instances = [i for i in instances if i.state == InstanceState.RUNNING]

        # TIER 1: Tiles
        self.bal_tile.set_value(f"${balance:.2f}")
        self.burn_tile.set_value(f"${display_burn:.3f}/h {trend.arrow}")
        self.today_tile.set_value(f"${today_spend:.2f}")
        self.running_tile.set_value(
            f"{len(running_instances)}/{len(instances)}"
        )
        self.util_tile.set_value(_format_percent(_avg(i.gpu_util for i in running_instances)))

        if week_spend is None and self._store:
            week_spend = self._store.week_spend()
        if month_spend is None and self._store:
            month_spend = self._store.month_spend()
        if week_spend is not None:
            self.week_tile.set_value(f"${week_spend:.2f}")
        if month_spend is not None:
            self.month_tile.set_value(f"${month_spend:.2f}")

        hours = autonomy_hours(balance, display_burn)
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
                    self.timeline.set_ymin_limit(0.0)
                    self.timeline.set_ymax_limit(recharge_val)
                    self.timeline._title = f"Cycle Tracker (Since ${recharge_val:.0f} Recharge)"
                    self.timeline_title_lbl.setText(self.timeline._title)
                else:
                    # Fallback to 24h if no recharge data
                    line_hrs = 24
                    self.timeline.set_ymin_limit(0.0)
                    self.timeline.set_ymax_limit(None)
                    self.timeline._title = "Balance Evolution (No Recharge Found)"
                    self.timeline_title_lbl.setText(self.timeline._title)
            else:
                self.timeline.set_ymin_limit(0.0)
                self.timeline.set_ymax_limit(None)
                self.timeline._title = "Balance Evolution"
                self.timeline_title_lbl.setText(self.timeline._title)

            # Metrics for live extrapolation
            live_dph = sum(
                float(getattr(i, "dph", 0.0) or 0.0)
                for i in running_instances
            )
            live_since = self._store.last_charge_end() if self._store else None

            if self._mode == "FINANCE":
                line_data = self._store.smoothed_balance_timeline(
                    line_hrs, balance, live_dph=live_dph, live_since=live_since
                )
                self.timeline.set_data(line_data, t.OK, line_hrs)
                self.timeline.set_forecast(display_burn)
            else:
                line_data = self._store.burn_rate_timeline(line_hrs)
                self.timeline.set_data(line_data, t.ACCENT, line_hrs)
                self.timeline.set_forecast(0)
            
            # Historical Bars (Global Range)
            if self._range_hours <= 24:
                title = "Spend Last 24 Hours"
                spend_data = self._store.spend_buckets(
                    24, bucket_count=8,
                    live_dph=live_dph, live_since=live_since,
                )
            else:
                days = max(1, self._range_hours // 24)
                title = f"Daily Spend ({days}D)"
                spend_data = self._store.daily_spend_history(days)
            self.spend_chart.set_title(title)
            self.spend_title_lbl.setText(title)
            self.spend_chart.set_data(spend_data)
            self.spend_total_lbl.setText(f"${self.spend_chart.total():.2f}")
            
            self._sync_billing_summary(self._store.billing_summary)

        self.composition.set_values(bd["gpu"], bd["storage"], bd["network"])
        self._last_today = today_spend

        # TIER 3: Instance bars
        self.cost_bars.set_items(bd["instances"], bd["gpu"] + bd["storage"])
        self._sync_fleet_health(instances)
        self._sync_economic_efficiency(instances, bd)

    def _sync_fleet_health(self, instances: list[Instance]):
        running = [i for i in instances if i.state == InstanceState.RUNNING]
        total_gpus = sum(max(1, i.num_gpus) for i in instances)
        running_gpus = sum(max(1, i.num_gpus) for i in running)
        gpu_avg = _avg(i.gpu_util for i in running)
        cpu_avg = _avg(i.cpu_util for i in running)
        vram_used = sum(i.vram_usage_gb or 0.0 for i in running)
        vram_total = sum((i.gpu_ram_gb or 0.0) * max(1, i.num_gpus) for i in running)
        ram_used = sum(i.ram_used_gb or 0.0 for i in running)
        ram_total = sum(i.ram_total_gb or 0.0 for i in running)
        disk_used = sum(i.disk_usage_gb or 0.0 for i in running)
        disk_total = sum(i.disk_space_gb or 0.0 for i in instances)
        down = sum(i.inet_down_mbps or 0.0 for i in running)
        up = sum(i.inet_up_mbps or 0.0 for i in running)
        billed_down = sum(i.inet_down_billed_gb or 0.0 for i in instances)
        billed_up = sum(i.inet_up_billed_gb or 0.0 for i in instances)
        temp_max = max((i.gpu_temp for i in running if i.gpu_temp is not None), default=None)
        reliability = _avg(i.reliability for i in instances)

        _set_metric(self.health_labels, "instances", f"{len(running)} running / {len(instances)} total")
        _set_metric(self.health_labels, "gpus", f"{running_gpus} running / {total_gpus} total")
        _set_metric(self.health_labels, "gpu", _format_percent(gpu_avg), _metric_color(gpu_avg))
        _set_metric(self.health_labels, "cpu", _format_percent(cpu_avg), _metric_color(cpu_avg))
        _set_metric(self.health_labels, "vram", _format_used_total(vram_used, vram_total, "GB"))
        _set_metric(self.health_labels, "ram", _format_used_total(ram_used, ram_total, "GB"))
        _set_metric(self.health_labels, "disk", _format_used_total(disk_used, disk_total, "GB"))
        _set_metric(self.health_labels, "network", f"{down:.1f} down / {up:.1f} up Mbps")
        _set_metric(self.health_labels, "billed", f"{billed_down:.2f} down / {billed_up:.2f} up GB")
        _set_metric(self.health_labels, "temp", "—" if temp_max is None else f"{temp_max:.0f}°C", t.temp_color(temp_max))
        _set_metric(self.health_labels, "reliability", _format_percent(reliability * 100 if reliability and reliability <= 1 else reliability))

    def _sync_economic_efficiency(self, instances: list[Instance], bd: dict):
        running = [i for i in instances if i.state == InstanceState.RUNNING]
        active = [
            i for i in instances
            if i.state in (InstanceState.RUNNING, InstanceState.STARTING)
        ]
        running_gpus = sum(max(1, i.num_gpus) for i in running)
        active_rate = sum(_effective_rate(i) for i in active)
        running_vram = sum((i.gpu_ram_gb or 0.0) * max(1, i.num_gpus) for i in running)
        active_flops = sum(i.total_flops or 0.0 for i in active)
        perf_per_dollar = _fleet_perf_per_dollar(active)
        reliability = _avg(_reliability_percent(i) for i in active)
        reliability_factor = (reliability / 100.0) if reliability else None
        risk_rate = (active_rate / reliability_factor) if reliability_factor else None
        discounted = sum(i.discounted_total_per_hour or 0.0 for i in active)
        listed = sum(i.dph or 0.0 for i in active)
        storage_price = _avg(i.storage_cost_per_gb_month for i in instances)
        verified_count = sum(1 for i in instances if str(i.verification or "").lower() == "verified")

        gpu_cost = (bd.get("gpu", 0.0) / running_gpus) if running_gpus else None
        vram_cost = (bd.get("gpu", 0.0) / running_vram) if running_vram else None
        tflop_cost = (active_rate / active_flops) if active_flops > 0 else None

        _set_metric(self.efficiency_labels, "gpu_cost", _format_money_unit(gpu_cost, "/GPU-h"))
        _set_metric(self.efficiency_labels, "vram_cost", _format_money_unit(vram_cost, "/GB-h"))
        _set_metric(self.efficiency_labels, "tflop_cost", _format_money_unit(tflop_cost, "/TFLOP-h"))
        _set_metric(self.efficiency_labels, "perf_dollar", "—" if perf_per_dollar is None else f"{perf_per_dollar:.1f} TFLOP/$")
        _set_metric(self.efficiency_labels, "risk_rate", _format_money_unit(risk_rate, "/h"))
        if discounted > 0 and listed > 0:
            savings = max(0.0, listed - discounted)
            _set_metric(self.efficiency_labels, "discount", f"${discounted:.3f}/h · saves ${savings:.3f}/h", t.OK if savings > 0 else None)
        else:
            _set_metric(self.efficiency_labels, "discount", "—")
        _set_metric(self.efficiency_labels, "storage_price", "—" if storage_price is None else f"${storage_price:.3f}/GB-mo")
        _set_metric(self.efficiency_labels, "verified", f"{verified_count}/{len(instances)}" if instances else "—")

        ranked = _rank_economic_instances(active)
        best = ranked[0] if ranked else None
        worst = ranked[-1] if len(ranked) > 1 else None
        high_cost = max(active, key=lambda i: _effective_rate(i), default=None)
        low_rel = min(
            (i for i in active if _reliability_percent(i) is not None),
            key=lambda i: _reliability_percent(i) or 0.0,
            default=None,
        )
        idle = max(
            (
                (i, _idle_burn(i))
                for i in running
                if i.gpu_util is not None
            ),
            key=lambda item: item[1],
            default=None,
        )
        alert_text, alert_color = _economic_alert(active, ranked, idle)

        _set_metric(self.ranking_labels, "best", _format_rank(best))
        _set_metric(self.ranking_labels, "worst", _format_rank(worst), t.WARN if worst else None)
        _set_metric(self.ranking_labels, "highest_cost", _format_instance_rate(high_cost))
        _set_metric(self.ranking_labels, "lowest_reliability", _format_instance_reliability(low_rel), t.WARN if low_rel else None)
        _set_metric(self.ranking_labels, "idle", "—" if not idle or idle[1] <= 0 else f"#{idle[0].id} · ${idle[1]:.3f}/h wasted", t.WARN if idle and idle[1] > 0 else None)
        _set_metric(self.ranking_labels, "alert", alert_text, alert_color)

    def _sync_billing_summary(self, summary: dict):
        if not summary:
            for key in self.billing_labels:
                _set_metric(self.billing_labels, key, "—")
            return

        cats = summary.get("categories") or {}
        top_sources = summary.get("top_sources") or []
        top = "—"
        if top_sources:
            source = str(top_sources[0].get("source") or "unknown").replace("instance-", "#")
            top = f"{source[:28]} · ${float(top_sources[0].get('amount') or 0.0):.2f}"

        synced_at = summary.get("synced_at")
        try:
            sync_text = datetime.fromisoformat(str(synced_at)).strftime("%d/%m %H:%M")
        except (TypeError, ValueError):
            sync_text = "—"

        _set_metric(self.billing_labels, "sync", sync_text)
        _set_metric(
            self.billing_labels,
            "records",
            f"{summary.get('charge_count', 0)} charges / {summary.get('invoice_count', 0)} invoices",
        )
        _set_metric(self.billing_labels, "charges", f"${float(summary.get('charges') or 0.0):.2f}")
        _set_metric(self.billing_labels, "credits", f"${float(summary.get('credits') or 0.0):.2f}", t.OK)
        
        # GPU/Storage/Bandwidth labels with context
        start_lbl = summary.get("coverage_start_label")
        range_suffix = f" (since {start_lbl})" if start_lbl else ""
        
        _set_metric(self.billing_labels, "gpu", f"${float(cats.get('gpu') or 0.0):.2f}")
        _set_metric(self.billing_labels, "storage", f"${float(cats.get('storage') or 0.0):.2f}")
        _set_metric(self.billing_labels, "network", f"${float(cats.get('network') or 0.0):.2f}")
        _set_metric(self.billing_labels, "top", top)

        if start_lbl:
            self.billing_title_lbl.setText(f"Billing (Since {start_lbl})")
        else:
            self.billing_title_lbl.setText("Billing")


# ── Helpers ──


def _card_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFixedHeight(CARD_TITLE_HEIGHT)
    lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    lbl.setStyleSheet(
        f"color: {t.TEXT_HI}; font-size: 13px; font-weight: 650;"
        f" font-family: {t.FONT_DISPLAY}; padding: 0;"
    )
    return lbl


def _card_value(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFixedHeight(CARD_TITLE_HEIGHT)
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lbl.setStyleSheet(
        f"color: {t.TEXT_HI}; font-size: 12px; font-weight: 700;"
        f" font-family: {t.FONT_MONO}; padding: 0 8px 0 0;"
    )
    return lbl


def _scroll_viewport(widget: QWidget, height: int) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setFixedHeight(height)
    scroll.setStyleSheet(f"""
        QScrollArea {{
            background: transparent;
            border: 0;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 2px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {t.SURFACE_3};
            border-radius: 3px;
            min-height: 28px;
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
            background: transparent;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """)
    scroll.setWidget(widget)
    return scroll


def _metric_row(grid: QGridLayout, labels: dict[str, QLabel], row: int, key: str, label: str):
    name = QLabel(label)
    name.setStyleSheet(
        f"color: {t.TEXT_MID}; font-size: {t.FONT_SIZE_SMALL}px;"
        f" padding: 4px 0;"
    )
    value = QLabel("—")
    value.setStyleSheet(
        f"color: {t.TEXT_HI}; font-size: {t.FONT_SIZE_SMALL}px;"
        f" font-family: {t.FONT_MONO}; padding: 4px 0;"
    )
    value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    grid.addWidget(name, row, 0)
    grid.addWidget(value, row, 1)
    labels[key] = value


def _set_metric(labels: dict[str, QLabel], key: str, value: str, color: str | None = None):
    lbl = labels.get(key)
    if lbl is None:
        return
    lbl.setText(value)
    lbl.setStyleSheet(
        f"color: {color or t.TEXT_HI}; font-size: {t.FONT_SIZE_SMALL}px;"
        f" font-family: {t.FONT_MONO}; padding: 4px 0;"
    )


def _avg(values) -> float | None:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _effective_rate(inst: Instance) -> float:
    discounted = inst.discounted_total_per_hour
    if discounted is not None and discounted > 0:
        return float(discounted)
    return max(0.0, float(inst.dph or 0.0))


def _reliability_percent(inst: Instance) -> float | None:
    rel = inst.reliability
    if rel is None:
        return None
    rel = float(rel)
    if rel <= 1.5:
        return rel * 100.0
    return rel


def _fleet_perf_per_dollar(instances: list[Instance]) -> float | None:
    total_rate = sum(_effective_rate(i) for i in instances)
    total_flops = sum(i.total_flops or 0.0 for i in instances)
    if total_rate > 0 and total_flops > 0:
        return total_flops / total_rate
    return _avg(i.flops_per_dphtotal for i in instances)


def _instance_value_score(inst: Instance) -> float | None:
    rate = _effective_rate(inst)
    if rate <= 0:
        return None
    if inst.total_flops and inst.total_flops > 0:
        score = inst.total_flops / rate
    elif inst.flops_per_dphtotal and inst.flops_per_dphtotal > 0:
        score = inst.flops_per_dphtotal
    else:
        vram = (inst.gpu_ram_gb or 0.0) * max(1, inst.num_gpus)
        if vram <= 0:
            return None
        score = vram / rate
    rel = _reliability_percent(inst)
    if rel is not None:
        score *= max(0.0, min(rel / 100.0, 1.0))
    if str(inst.verification or "").lower() == "verified":
        score *= 1.03
    return score


def _rank_economic_instances(instances: list[Instance]) -> list[tuple[Instance, float]]:
    ranked = []
    for inst in instances:
        score = _instance_value_score(inst)
        if score is not None:
            ranked.append((inst, score))
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def _idle_burn(inst: Instance) -> float:
    util = inst.gpu_util
    if util is None:
        return 0.0
    idle_ratio = max(0.0, min(1.0, 1.0 - (float(util) / 100.0)))
    return _effective_rate(inst) * idle_ratio


def _economic_alert(
    active: list[Instance],
    ranked: list[tuple[Instance, float]],
    idle: tuple[Instance, float] | None,
) -> tuple[str, str | None]:
    low_rel = [
        i for i in active
        if (_reliability_percent(i) is not None and (_reliability_percent(i) or 0.0) < 95)
    ]
    if low_rel:
        worst = min(low_rel, key=lambda i: _reliability_percent(i) or 0.0)
        return f"#{worst.id} low reliability", t.WARN
    if idle and idle[1] >= 0.02:
        return f"#{idle[0].id} idle burn ${idle[1]:.3f}/h", t.WARN
    if len(ranked) > 1 and ranked[-1][1] < ranked[0][1] * 0.70:
        return f"#{ranked[-1][0].id} weak value score", t.WARN
    if not active:
        return "No active compute", None
    return "No cost anomalies", t.OK


def _format_money_unit(value: float | None, suffix: str) -> str:
    if value is None:
        return "—"
    if value < 0.01:
        return f"${value:.4f}{suffix}"
    return f"${value:.3f}{suffix}"


def _format_rank(item: tuple[Instance, float] | None) -> str:
    if item is None:
        return "—"
    inst, score = item
    return f"#{inst.id} · {score:.1f} score"


def _format_instance_rate(inst: Instance | None) -> str:
    if inst is None:
        return "—"
    return f"#{inst.id} · ${_effective_rate(inst):.3f}/h"


def _format_instance_reliability(inst: Instance | None) -> str:
    if inst is None:
        return "—"
    rel = _reliability_percent(inst)
    return f"#{inst.id} · {_format_percent(rel)}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def _format_axis_money(value: float) -> str:
    if abs(value) < 0.005:
        return "$0"
    if value >= 10:
        return f"${value:.0f}"
    return f"${value:.1f}"


def _chart_axis_bounds(
    values: list[float],
    ymin_limit: float | None = 0.0,
    ymax_limit: float | None = None,
) -> tuple[float, float]:
    vals = values or [0.0]
    mn, mx = min(vals), max(vals)
    pad = max(0.1, (mx - mn) * 0.15)
    ymin = mn - pad
    ymax = mx + pad
    if ymin_limit is not None:
        ymin = ymin_limit
        ymax = max(ymax, ymin + 1.0)
    if ymax_limit is not None:
        ymax = max(mx, ymax_limit)
    if ymax <= ymin:
        ymax = ymin + 1.0
    return ymin, ymax


def _format_used_total(used: float, total: float, unit: str) -> str:
    if total <= 0 and used <= 0:
        return "—"
    if total <= 0:
        return f"{used:.1f} {unit}"
    pct = (used / total) * 100 if total > 0 else 0.0
    return f"{used:.1f}/{total:.1f} {unit} ({pct:.0f}%)"


def _metric_color(value: float | None) -> str | None:
    if value is None:
        return None
    return t.metric_color(value)
