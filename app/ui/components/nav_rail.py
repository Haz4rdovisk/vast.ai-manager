"""Left nav rail — professional glass surface with vector icon set.
Emits `selected(key)` on click."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (
    QPainter, QLinearGradient, QColor, QPen, QPainterPath, QFont, QBrush,
)
from app import theme as t


# (key, label, icon_kind, section)
NAV_ITEMS = [
    # ── CLOUD ──
    ("instances",  "Instances",   "instances", "CLOUD"),
    ("store",      "Store",       "store",     "CLOUD"),
    ("analytics",  "Analytics",   "analytics", "CLOUD"),
    # ── AI LAB ──
    ("dashboard",  "Dashboard",   "dashboard", "AI LAB"),
    ("hardware",   "Hardware",    "hardware",  "AI LAB"),
    ("discover",   "Discover",    "discover",  "AI LAB"),
    ("models",     "Models",      "models",    "AI LAB"),
    ("monitor",    "Monitor",     "monitor",   "AI LAB"),
    # ── SYSTEM ──
    ("settings",   "Settings",    "settings",  "SYSTEM"),
]

ICON_PX = 20
ROW_H = 40


# ═══════════════════════════════════════════════════════════════════════════════
#  NavIcon — single-weight stroked line-art glyphs (Lucide-inspired)
# ═══════════════════════════════════════════════════════════════════════════════
class NavIcon(QWidget):
    """Cohesive line-art icon set rendered via QPainter.
    All glyphs share the same stroke width, cap style, and viewbox."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._color = QColor(t.TEXT_MID)
        self.setFixedSize(ICON_PX, ICON_PX)

    def setColor(self, color: QColor | str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # normalized 20x20 viewbox with 2px inset
        getattr(self, f"_draw_{self._kind}", self._draw_default)(p)
        p.end()

    # Each drawer works in 20x20 box, 2px padding → glyphs live in 16x16
    def _draw_instances(self, p: QPainter):
        # Two stacked rounded rects — "servers"
        p.drawRoundedRect(QRectF(3, 4, 14, 5), 1.2, 1.2)
        p.drawRoundedRect(QRectF(3, 11, 14, 5), 1.2, 1.2)
        # status dots
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(5.5, 6.5), 0.9, 0.9)
        p.drawEllipse(QPointF(5.5, 13.5), 0.9, 0.9)

    def _draw_store(self, p: QPainter):
        # Shopping bag: body with rounded corners + curved handle + dot accent
        # Body
        p.drawRoundedRect(QRectF(3.5, 7.5, 13, 10), 1.6, 1.6)
        # Handle (U-shape)
        path = QPainterPath()
        path.moveTo(7, 7.5)
        path.cubicTo(7, 4, 13, 4, 13, 7.5)
        p.drawPath(path)
        # Tiny accent dot (stock indicator)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(10, 13), 1.1, 1.1)
        # Restore pen for any subsequent drawing
        pen = QPen(self._color, 1.6)
        pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.NoBrush)

    def _draw_analytics(self, p: QPainter):
        # Three ascending bars
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(3.5, 12, 3, 5), 0.8, 0.8)
        p.drawRoundedRect(QRectF(8.5, 8, 3, 9), 0.8, 0.8)
        p.drawRoundedRect(QRectF(13.5, 4, 3, 13), 0.8, 0.8)

    def _draw_dashboard(self, p: QPainter):
        # 2x2 grid of rounded squares
        for (x, y) in [(3, 3), (11, 3), (3, 11), (11, 11)]:
            p.drawRoundedRect(QRectF(x, y, 6, 6), 1.2, 1.2)

    def _draw_hardware(self, p: QPainter):
        # CPU chip: outer square + inner square + 4 pins per side
        p.drawRoundedRect(QRectF(4, 4, 12, 12), 1.5, 1.5)
        p.drawRoundedRect(QRectF(7, 7, 6, 6), 0.6, 0.6)
        # pins (short strokes)
        for i, x in enumerate([7.5, 12.5]):
            p.drawLine(QPointF(x, 2.5), QPointF(x, 4))
            p.drawLine(QPointF(x, 16), QPointF(x, 17.5))
        for y in [7.5, 12.5]:
            p.drawLine(QPointF(2.5, y), QPointF(4, y))
            p.drawLine(QPointF(16, y), QPointF(17.5, y))

    def _draw_discover(self, p: QPainter):
        # Magnifying glass
        p.drawEllipse(QRectF(3, 3, 11, 11))
        p.drawLine(QPointF(12.2, 12.2), QPointF(17, 17))

    def _draw_models(self, p: QPainter):
        # Isometric cube outline
        # Top rhombus
        top = QPainterPath()
        top.moveTo(10, 2.5)
        top.lineTo(17, 6)
        top.lineTo(10, 9.5)
        top.lineTo(3, 6)
        top.closeSubpath()
        p.drawPath(top)
        # Side edges
        p.drawLine(QPointF(3, 6), QPointF(3, 13.5))
        p.drawLine(QPointF(17, 6), QPointF(17, 13.5))
        p.drawLine(QPointF(10, 9.5), QPointF(10, 17.5))
        # Bottom edges
        p.drawLine(QPointF(3, 13.5), QPointF(10, 17.5))
        p.drawLine(QPointF(17, 13.5), QPointF(10, 17.5))

    def _draw_monitor(self, p: QPainter):
        # Display + stand
        p.drawRoundedRect(QRectF(2.5, 3.5, 15, 10), 1.2, 1.2)
        p.drawLine(QPointF(7, 16.5), QPointF(13, 16.5))
        p.drawLine(QPointF(10, 13.5), QPointF(10, 16.5))

    def _draw_settings(self, p: QPainter):
        # Gear: 8 rounded teeth around a circle
        import math
        cx, cy = 10, 10
        outer, inner = 7.5, 5.5
        path = QPainterPath()
        teeth = 8
        for i in range(teeth * 2):
            angle = (i * math.pi) / teeth
            r = outer if i % 2 == 0 else inner + 0.6
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
        # Inner hole
        p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)

    def _draw_default(self, p: QPainter):
        p.drawEllipse(QRectF(5, 5, 10, 10))


# ═══════════════════════════════════════════════════════════════════════════════
#  NavItem — icon + label, clickable, hover/active states
# ═══════════════════════════════════════════════════════════════════════════════
class NavItem(QWidget):
    clicked = Signal()

    def __init__(self, label: str, kind: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumHeight(ROW_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._hover = False
        self._active = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(12)

        self._icon = NavIcon(kind)
        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"color: {t.TEXT}; font-family: {t.FONT_DISPLAY};"
            f" font-size: {t.FONT_SIZE_BODY}px; font-weight: 500;"
            f" letter-spacing: 0.2px; background: transparent;"
        )
        lay.addWidget(self._icon)
        lay.addWidget(self._label)
        lay.addStretch()

        self._refresh_colors()

    def setActive(self, on: bool):
        self._active = on
        self._refresh_colors()
        self.update()

    def _refresh_colors(self):
        if self._active:
            fg = t.TEXT_HERO
            weight = 700
        elif self._hover:
            fg = t.TEXT_HI
            weight = 600
        else:
            fg = t.TEXT
            weight = 500
        self._icon.setColor(fg)
        self._label.setStyleSheet(
            f"color: {fg}; font-family: {t.FONT_DISPLAY};"
            f" font-size: {t.FONT_SIZE_BODY}px; font-weight: {weight};"
            f" letter-spacing: 0.2px; background: transparent;"
        )

    def enterEvent(self, e):
        self._hover = True
        self._refresh_colors()
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._refresh_colors()
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(6, 3, w - 12, h - 6)
        r = t.RADIUS_MD

        if self._active:
            # Glass pill with accent tint + left accent bar
            bg = QLinearGradient(0, rect.top(), 0, rect.bottom())
            bg.setColorAt(0.0, QColor(124, 92, 255, 55))
            bg.setColorAt(1.0, QColor(124, 92, 255, 28))
            p.setBrush(bg)
            p.setPen(QPen(QColor(124, 92, 255, 90), 1.0))
            p.drawRoundedRect(rect, r, r)
            # Left accent bar
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.ACCENT))
            p.drawRoundedRect(
                QRectF(rect.left(), rect.top() + 8,
                       3, rect.height() - 16), 1.5, 1.5
            )
        elif self._hover:
            p.setBrush(QColor(255, 255, 255, 10))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, r, r)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  NavRail
# ═══════════════════════════════════════════════════════════════════════════════
class NavRail(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nav-rail")
        self.setFixedWidth(224)
        self.setAttribute(Qt.WA_StyledBackground, False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.SPACE_3, t.SPACE_5, t.SPACE_3, t.SPACE_4)
        lay.setSpacing(2)

        # Brand
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(14, 0, 14, 24)
        brand_row.setSpacing(10)
        brand_icon = _BrandMark()
        brand_lbl = QLabel("VAST.AI")
        brand_lbl.setStyleSheet(
            f"color: {t.TEXT_HERO}; font-family: {t.FONT_DISPLAY};"
            f" font-weight: 800; letter-spacing: 3px; font-size: 13pt;"
            f" background: transparent;"
        )
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand_lbl)
        brand_row.addStretch()
        lay.addLayout(brand_row)

        self._items: dict[str, NavItem] = {}
        current_section = ""

        for key, label, kind, section in NAV_ITEMS:
            if section != current_section:
                current_section = section
                if len(self._items) > 0:
                    lay.addSpacing(18)
                sec_lbl = QLabel(section)
                sec_lbl.setStyleSheet(
                    f"color: {t.TEXT_LOW}; background: transparent;"
                    f" font-family: {t.FONT_DISPLAY};"
                    f" font-size: {t.FONT_SIZE_LABEL}px;"
                    f" font-weight: 700; letter-spacing: 2px;"
                    f" padding: 6px 20px 8px 20px;"
                )
                lay.addWidget(sec_lbl)

            item = NavItem(label, kind)
            item.clicked.connect(lambda k=key: self._on_click(k))
            lay.addWidget(item)
            self._items[key] = item

        lay.addStretch()

        foot = QLabel("v2.1  •  remote inference")
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet(
            f"color: {t.TEXT_LOW}; background: transparent;"
            f" font-size: {t.FONT_SIZE_SMALL}px;"
            f" font-weight: 500; letter-spacing: 0.8px; padding: 8px;"
        )
        lay.addWidget(foot)

        self.set_active("instances")

    def _on_click(self, key: str):
        self.set_active(key)
        self.selected.emit(key)

    def set_active(self, key: str):
        for k, item in self._items.items():
            item.setActive(k == key)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Layer 1: vertical gradient base
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(t.BG_BASE))
        bg.setColorAt(1.0, QColor(t.BG_VOID))
        p.fillRect(0, 0, w, h, bg)

        # Layer 2: top refraction highlight
        highlight = QLinearGradient(0, 0, 0, 140)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 12))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, w, 140, highlight)

        # Layer 3: right-edge border with fade
        edge = QLinearGradient(0, 0, 0, h)
        edge.setColorAt(0.0, QColor(255, 255, 255, 0))
        edge.setColorAt(0.4, QColor(255, 255, 255, 20))
        edge.setColorAt(0.6, QColor(255, 255, 255, 20))
        edge.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(w - 1, 0, 1, h, edge)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  BrandMark — custom logo glyph (diamond + ring)
# ═══════════════════════════════════════════════════════════════════════════════
class _BrandMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Accent filled diamond
        path = QPainterPath()
        path.moveTo(11, 3)
        path.lineTo(19, 11)
        path.lineTo(11, 19)
        path.lineTo(3, 11)
        path.closeSubpath()
        grad = QLinearGradient(3, 3, 19, 19)
        grad.setColorAt(0.0, QColor(t.ACCENT_HI))
        grad.setColorAt(1.0, QColor(t.ACCENT_END))
        p.fillPath(path, QBrush(grad))
        # Inner highlight dot
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawEllipse(QPointF(11, 11), 1.8, 1.8)
        p.end()
