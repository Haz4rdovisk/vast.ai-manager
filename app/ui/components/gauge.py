"""Custom half-moon gauge widget for hardware monitoring."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QConicalGradient
from PySide6.QtCore import Qt, QRectF, Property, QPropertyAnimation, QEasingCurve
from app import theme as t

class GaugeWidget(QWidget):
    def __init__(self, label: str, unit: str = "%", parent=None):
        super().__init__(parent)
        self.label = label
        self.unit = unit
        self._value = 0.0
        self._subtext = ""
        self.setMinimumSize(160, 160)
        
        # Animation for smooth transitions
        self._display_value = 0.0
        self.anim = QPropertyAnimation(self, b"display_value")
        self.anim.setDuration(600)
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
        # Maximized arc with a subtle 12px top margin (for "little" breathing)
        side = min(w, h) - 20
        rect = QRectF((w - side)/2, 12, side, side)
        
        # Thick, bold track for more impact
        pen = QPen(QColor(t.SURFACE_3), 16, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0 * 16, 180 * 16)
        
        # Determine color based on value
        color = t.OK
        if self._display_value > 85: color = t.ERR
        elif self._display_value > 60: color = t.WARN
        
        # Draw value arc
        pen.setColor(QColor(color))
        span = -1.8 * self._display_value
        p.setPen(pen)
        p.drawArc(rect, 180 * 16, span * 16)
        
        # Upscaled Information Hierarchy - Shifted down by 5px for balance
        # 1. Main Value (%) - Larger (24pt)
        p.setPen(QColor(t.TEXT_HI))
        p.setFont(QFont(t.FONT_DISPLAY, 24, QFont.Bold))
        val_rect = QRectF(0, h/2 - 1, w, 40)
        p.drawText(val_rect, Qt.AlignCenter, f"{self._value:.0f}{self.unit}")
        
        # 2. Label (TITLE) - Larger (9pt)
        p.setPen(QColor(t.TEXT_MID))
        p.setFont(QFont(t.FONT_DISPLAY, 9, QFont.Bold))
        label_rect = QRectF(0, h/2 + 39, w, 15)
        p.drawText(label_rect, Qt.AlignCenter, self.label.upper())

        # 3. Subtext (Absolute values) - Monospace, clearer (9pt)
        if self._subtext:
            p.setPen(QColor(t.TEXT_LOW))
            p.setFont(QFont(t.FONT_MONO, 9, QFont.Normal))
            sub_rect = QRectF(0, h/2 + 59, w, 22)
            p.drawText(sub_rect, Qt.AlignCenter, f"({self._subtext})")
