"""Animated GPU temperature thermometer widget."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from app import theme as t


class ThermometerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._temperature = 0.0
        self._display_temperature = 0.0
        self.setMinimumSize(84, 230)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self.anim = QPropertyAnimation(self, b"display_temperature")
        self.anim.setDuration(t.ANIM_GAUGE)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    @Property(float)
    def display_temperature(self):
        return self._display_temperature

    @display_temperature.setter
    def display_temperature(self, value):
        self._display_temperature = max(0.0, min(110.0, float(value)))
        self.update()

    def set_temperature(self, value: float | None) -> None:
        self._temperature = max(0.0, float(value or 0.0))
        self.anim.stop()
        self.anim.setStartValue(self._display_temperature)
        self.anim.setEndValue(max(0.0, min(110.0, self._temperature)))
        self.anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        color = QColor(t.temp_color(self._display_temperature))
        low_color = QColor(t.OK)
        high_color = QColor(t.ERR if self._display_temperature >= 80 else t.WARN)

        tube_w = max(12, min(18, int(w * 0.18)))
        bulb = max(34, min(46, int(w * 0.48)))
        top = 20
        bottom = h - 72
        cx = w / 2
        tube_x = cx - tube_w / 2
        tube_h = max(40, bottom - top)
        fill_ratio = min(1.0, max(0.0, self._display_temperature / 100.0))

        # Title
        p.setPen(QColor(t.TEXT_MID))
        p.setFont(QFont(t.FONT_DISPLAY, 8, QFont.Bold))
        p.drawText(QRectF(0, 0, w, 18), Qt.AlignCenter, "GPU TEMP")

        # Glass tube
        tube = QRectF(tube_x, top, tube_w, tube_h)
        p.setPen(QPen(QColor(t.BORDER_HI), 1.2))
        p.setBrush(QColor(255, 255, 255, 8))
        p.drawRoundedRect(tube, tube_w / 2, tube_w / 2)

        # Fill
        fill_h = tube_h * fill_ratio
        fill_rect = QRectF(tube_x + 3, top + tube_h - fill_h + 3, tube_w - 6, max(0, fill_h - 3))
        grad = QLinearGradient(0, fill_rect.bottom(), 0, fill_rect.top())
        grad.setColorAt(0.0, low_color)
        grad.setColorAt(1.0, high_color)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(fill_rect, max(4, (tube_w - 6) / 2), max(4, (tube_w - 6) / 2))

        # Bulb glow and body
        bulb_rect = QRectF(cx - bulb / 2, bottom - bulb * 0.18, bulb, bulb)
        glow = QColor(color)
        glow.setAlpha(45)
        p.setBrush(glow)
        p.drawEllipse(bulb_rect.adjusted(-5, -5, 5, 5))
        p.setBrush(color)
        p.drawEllipse(bulb_rect)

        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(tube, tube_w / 2, tube_w / 2)
        p.drawEllipse(bulb_rect)

        # Readout
        p.setPen(color)
        p.setFont(QFont(t.FONT_MONO, 17, QFont.Bold))
        p.drawText(QRectF(0, h - 34, w, 28), Qt.AlignCenter, f"{self._temperature:.0f}°C")
        p.end()
