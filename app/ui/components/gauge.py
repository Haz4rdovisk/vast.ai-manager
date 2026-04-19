"""Custom half-moon gauge widget — glassmorphism polish."""
from __future__ import annotations
from PySide6.QtWidgets import QSizePolicy, QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtCore import Qt, QRectF, Property, QPropertyAnimation, QEasingCurve
from app import theme as t


class GaugeWidget(QWidget):
    def __init__(self, label: str, unit: str = "%", parent=None):
        super().__init__(parent)
        self.label = label
        self.unit = unit
        self._value = 0.0
        self._subtext = ""
        self.setMinimumSize(112, 112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Animation
        self._display_value = 0.0
        self.anim = QPropertyAnimation(self, b"display_value")
        self.anim.setDuration(t.ANIM_GAUGE)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    @Property(float)
    def display_value(self):
        return self._display_value

    @display_value.setter
    def display_value(self, val):
        self._display_value = val
        self.update()

    def setValue(self, val: float, subtext: str = ""):
        self._value = val
        self._subtext = subtext
        self.anim.stop()
        self.anim.setStartValue(self._display_value)
        self.anim.setEndValue(max(0.0, min(100.0, val)))
        self.anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        side = max(72, min(w, h) - 18)
        rect = QRectF((w - side) / 2, 10, side, side)
        scale = max(0.72, min(1.0, side / 150))
        pen_w = max(11, int(18 * scale))

        # Track arc — thick and bold
        track_pen = QPen(QColor(t.SURFACE_3), pen_w, Qt.SolidLine, Qt.RoundCap)
        p.setPen(track_pen)
        p.drawArc(rect, 0 * 16, 180 * 16)

        # Value color
        color = t.OK
        if self._display_value > 85:
            color = t.ERR
        elif self._display_value > 60:
            color = t.WARN

        # Glow pass (subtle, behind the main arc)
        if self._display_value > 0:
            glow_pen = QPen(QColor(color), max(pen_w + 5, int(24 * scale)), Qt.SolidLine, Qt.RoundCap)
            glow_pen.setColor(QColor(color))
            glow_color = QColor(color)
            glow_color.setAlpha(40)
            glow_pen.setColor(glow_color)
            p.setPen(glow_pen)
            span = -1.8 * self._display_value
            p.drawArc(rect, 180 * 16, span * 16)

        # Main value arc
        val_pen = QPen(QColor(color), pen_w, Qt.SolidLine, Qt.RoundCap)
        p.setPen(val_pen)
        span = -1.8 * self._display_value
        p.drawArc(rect, 180 * 16, span * 16)

        # 1. Main Value — 26pt bold
        p.setPen(QColor(t.TEXT_HI))
        p.setFont(QFont(t.FONT_DISPLAY, max(18, int(26 * scale)), QFont.Bold))
        val_rect = QRectF(0, h / 2 - 14, w, 36)
        p.drawText(val_rect, Qt.AlignCenter, f"{self._value:.0f}{self.unit}")

        # 2. Label — 10pt uppercase
        p.setPen(QColor(t.TEXT_MID))
        p.setFont(QFont(t.FONT_DISPLAY, max(8, int(10 * scale)), QFont.Bold))
        label_rect = QRectF(0, h / 2 + 18, w, 16)
        p.drawText(label_rect, Qt.AlignCenter, self.label.upper())

        # 3. Subtext — monospace detail
        if self._subtext:
            p.setPen(QColor(t.TEXT_LOW))
            p.setFont(QFont(t.FONT_MONO, max(8, int(10 * scale)), QFont.Normal))
            sub_rect = QRectF(0, h / 2 + 34, w, 22)
            p.drawText(sub_rect, Qt.AlignCenter, f"({self._subtext})")

        p.end()
