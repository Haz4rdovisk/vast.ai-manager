"""Shared visual primitives — Premium Glassmorphism edition.
Every widget sets objectName/role properties for the global stylesheet.
No business logic here — only reusable visual building blocks."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QLinearGradient, QRadialGradient, QPen, QBrush, QPainterPath,
)
from app import theme as t


# ═══════════════════════════════════════════════════════════════════════════════
#  GlassCard — true glassmorphism surface with painted glass effect
# ═══════════════════════════════════════════════════════════════════════════════
class GlassCard(QFrame):
    """Primary surface with real painted glassmorphism:
    - Multi-layer gradient background (not flat color)
    - Top-edge inner highlight (simulates refraction)
    - Subtle radial glow at center
    - Hover: accent border glow
    """

    def __init__(self, raised: bool = False, parent=None):
        super().__init__(parent)
        self._raised = raised
        self.setProperty("role", "card-raised" if raised else "card")
        self.setAttribute(Qt.WA_StyledBackground, False)  # we paint ourselves
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        self._lay.setSpacing(t.SPACE_3)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(t.SHADOW_BLUR_LG if raised else t.SHADOW_BLUR_MD)
        shadow.setOffset(0, t.SHADOW_OFFSET_Y)
        shadow.setColor(QColor(0, 0, 0, 100 if raised else 70))
        self.setGraphicsEffect(shadow)

        self._hover = False

    def body(self) -> QVBoxLayout:
        return self._lay

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = t.RADIUS_LG

        # Clip to rounded rect
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), r, r)
        p.setClipPath(path)

        # Layer 1: Base fill — vertical gradient (darker at bottom)
        if self._raised:
            base_top = QColor(24, 30, 46)
            base_bot = QColor(16, 21, 34)
        else:
            base_top = QColor(17, 22, 34)
            base_bot = QColor(11, 15, 25)
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, base_top)
        bg.setColorAt(1.0, base_bot)
        p.fillRect(0, 0, w, h, bg)

        # Layer 2: Center radial glow (subtle purple warmth)
        glow = QRadialGradient(w * 0.5, h * 0.3, max(w, h) * 0.6)
        glow.setColorAt(0.0, QColor(124, 92, 255, 8))   # very subtle accent
        glow.setColorAt(0.5, QColor(124, 92, 255, 3))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, glow)

        # Layer 3: Top-edge highlight (glass refraction)
        highlight = QLinearGradient(0, 0, 0, 60)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 12 if self._raised else 8))
        highlight.setColorAt(0.3, QColor(255, 255, 255, 4))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, w, 60, highlight)

        # Border
        p.setClipping(False)
        border_color = QColor(124, 92, 255, 40) if self._hover else QColor(255, 255, 255, 16 if self._raised else 10)
        pen = QPen(border_color, 1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

        # Hover: extra glow at top edge
        if self._hover:
            hover_glow = QLinearGradient(0, 0, 0, 40)
            hover_glow.setColorAt(0.0, QColor(124, 92, 255, 15))
            hover_glow.setColorAt(1.0, QColor(124, 92, 255, 0))
            p.setClipPath(path)
            p.fillRect(0, 0, w, 40, hover_glow)

        p.end()

    def setGlow(self, on: bool):
        """Manual glow toggle (for programmatic use)."""
        self._hover = on
        self.update()


# ═══════════════════════════════════════════════════════════════════════════════
#  Badge — compact pill label (non-status); and Divider — 1px horizontal rule
# ═══════════════════════════════════════════════════════════════════════════════
class Badge(QLabel):
    """Inline metadata label for compact info.

    Badges stay visually light so dense cards do not turn into a wall of boxes.
    """

    def __init__(self, text: str = "", *, mono: bool = False,
                 accent: bool = False, parent=None):
        super().__init__(str(text or ""), parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._mono = mono
        self._accent = accent
        self._restyle()

    def _restyle(self):
        family = t.FONT_MONO if self._mono else t.FONT_DISPLAY
        fg = t.ACCENT_SOFT if self._accent else t.TEXT_HI
        line = t.ACCENT if self._accent else t.BORDER_HI
        self.setStyleSheet(
            f"QLabel {{ color: {fg}; background: transparent;"
            f" border: none; border-bottom: 1px solid {line};"
            f" padding: 1px 2px 4px 2px;"
            f" font-family: {family}; font-size: 12px;"
            f" font-weight: 700; }}"
        )


class Divider(QFrame):
    """1px horizontal hairline. Use inside cards to separate zones."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {t.BORDER_LOW}; border: none;")


class VDivider(QLabel):
    """Inline vertical dot divider (middle dot) for single-line strips."""

    def __init__(self, parent=None):
        super().__init__("\u00b7", parent)
        self.setStyleSheet(
            f"color: {t.TEXT_LOW}; font-size: 16px; font-weight: 700;"
            f" padding: 0 2px;"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  SectionHeader — eyebrow + title pair
# ═══════════════════════════════════════════════════════════════════════════════
class SectionHeader(QWidget):
    """Eyebrow + title pair. Used at the top of every view and in cards."""

    def __init__(self, eyebrow: str, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        e = QLabel(eyebrow)
        e.setProperty("role", "section")
        tl = QLabel(title)
        tl.setProperty("role", "title")
        lay.addWidget(e)
        lay.addWidget(tl)


# ═══════════════════════════════════════════════════════════════════════════════
#  StatusPill — colored chip with dot
# ═══════════════════════════════════════════════════════════════════════════════
class StatusPill(QLabel):
    """Inline colored state label. `level` controls dot + text color."""

    def __init__(self, text: str, level: str = "info", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._level = level
        self.set_status(text, level)

    def set_status(self, text: str, level: str):
        self._level = level
        color = t.health_color(level)
        self.setText(f"\u25CF  {text}")
        self.setStyleSheet(
            f"QLabel {{ color: {color}; background: transparent;"
            f" border: none; padding: 1px 2px 4px 2px;"
            f" font-size: 12px; font-weight: 800; }}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  HealthDot — tiny colored indicator
# ═══════════════════════════════════════════════════════════════════════════════
class HealthDot(QLabel):
    """Tiny colored dot with glow."""

    def __init__(self, level: str = "info", parent=None):
        super().__init__(parent)
        self.set_level(level)

    def set_level(self, level: str):
        color = t.health_color(level)
        self.setFixedSize(12, 12)
        self.setStyleSheet(
            f"QLabel {{ background: {color}; border-radius: 6px; }}"
        )
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(10)
        glow.setOffset(0, 0)
        glow.setColor(QColor(color))
        self.setGraphicsEffect(glow)


# ═══════════════════════════════════════════════════════════════════════════════
#  MetricTile — single big-number with glass background
# ═══════════════════════════════════════════════════════════════════════════════
class MetricTile(GlassCard):
    """Single big number + label + optional hint."""

    def __init__(self, label: str, value: str = "\u2014", hint: str = "", parent=None):
        super().__init__(parent=parent)
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        self._lay.setSpacing(2)
        self._label = QLabel(label)
        self._label.setProperty("role", "section")
        self._value = QLabel(value)
        self._value.setStyleSheet(
            f"color: {t.TEXT_HI}; font-size: 22px; font-weight: 700;"
        )
        self._hint = QLabel(hint)
        self._hint.setProperty("role", "muted")
        self._hint.setStyleSheet(f"font-size: {t.FONT_SIZE_SMALL}px; color: {t.TEXT_MID};")
        self._lay.addWidget(self._label)
        self._lay.addWidget(self._value)
        self._lay.addWidget(self._hint)

    def set_value(self, value: str, hint: str = ""):
        self._value.setText(value)
        self._hint.setText(hint)

    def set_color(self, color: str):
        self._value.setStyleSheet(
            f"color: {color}; font-size: 22px; font-weight: 700;"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  KeyValueRow
# ═══════════════════════════════════════════════════════════════════════════════
class KeyValueRow(QWidget):
    """Two-column row — key on the left, value monospace on the right."""

    def __init__(self, key: str, value: str = "\u2014", mono: bool = True, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._k = QLabel(key)
        self._k.setProperty("role", "muted")
        self._v = QLabel(value)
        if mono:
            self._v.setProperty("role", "mono")
        lay.addWidget(self._k)
        lay.addStretch()
        lay.addWidget(self._v)

    def set_value(self, value: str):
        self._v.setText(value)


# ═══════════════════════════════════════════════════════════════════════════════
#  SkeletonBlock — shimmer loader placeholder
# ═══════════════════════════════════════════════════════════════════════════════
class SkeletonBlock(QWidget):
    """Rectangle with animated shimmer — loading placeholder."""

    def __init__(self, w: int = 200, h: int = 20, parent=None):
        super().__init__(parent)
        self.setFixedSize(w, h)
        self._phase = 0.0

        self._anim = QPropertyAnimation(self, b"phase")
        self._anim.setDuration(1500)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.start()

    @Property(float)
    def phase(self):
        return self._phase

    @phase.setter
    def phase(self, val):
        self._phase = val
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        radius = min(8, h // 2)

        p.setBrush(QColor(t.SURFACE_3))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, radius, radius)

        highlight_w = w * 0.4
        x = -highlight_w + (w + highlight_w) * self._phase
        grad = QLinearGradient(x, 0, x + highlight_w, 0)
        grad.setColorAt(0.0, QColor(t.SURFACE_3))
        grad.setColorAt(0.5, QColor(t.SURFACE_2))
        grad.setColorAt(1.0, QColor(t.SURFACE_3))
        p.setBrush(grad)
        p.setClipRect(0, 0, w, h)
        p.drawRoundedRect(0, 0, w, h, radius, radius)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  Instances revamp primitives
# ═══════════════════════════════════════════════════════════════════════════════
import qtawesome as qta
from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton


def icon(name: str, color: str = t.TEXT, size: int = 16) -> QIcon:
    """Return a MaterialDesignIcons QIcon via qtawesome."""
    return qta.icon(f"mdi.{name}", color=color)


class IconButton(QPushButton):
    """26x26 ghost button with an MDI icon and tooltip."""

    def __init__(
        self,
        mdi_name: str,
        tooltip: str,
        *,
        color: str = t.TEXT,
        danger: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mdi = mdi_name
        self._base_color = t.ERR if danger else color
        self._refresh_icon()
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {t.BORDER_LOW};"
            f" border-radius: 6px; padding: 0; }}"
            f"QPushButton:hover {{ background: {t.GLASS_HOVER}; border-color: {t.BORDER_MED}; }}"
            f"QPushButton:disabled {{ background: transparent; border-color: {t.BORDER_LOW}; }}"
        )

    def _refresh_icon(self) -> None:
        color = t.TEXT_LOW if not self.isEnabled() else self._base_color
        self.setIcon(icon(self._mdi, color=color))

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._refresh_icon()


_CHIP_VARIANTS = {
    "default": (t.SURFACE_2, t.BORDER_LOW, t.TEXT),
    "ok": ("rgba(59,212,136,0.10)", "rgba(59,212,136,0.30)", t.OK),
    "accent": ("rgba(124,92,255,0.10)", "rgba(124,92,255,0.30)", t.ACCENT_SOFT),
    "danger": ("rgba(240,85,106,0.10)", "rgba(240,85,106,0.30)", t.ERR),
}


class Chip(QFrame):
    """Pill-style label. Variants: default | ok | accent | danger."""

    clicked = Signal()

    def __init__(
        self,
        text: str,
        *,
        variant: str = "default",
        mono: bool = False,
        clickable: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        bg, border, fg = _CHIP_VARIANTS.get(variant, _CHIP_VARIANTS["default"])
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(0)
        self.label = QLabel(text, self)
        font = self.label.font()
        font.setFamily(t.FONT_MONO if mono else t.FONT_DISPLAY)
        font.setPointSize(9)
        self.label.setFont(font)
        self.label.setStyleSheet(f"color: {fg}; background: transparent;")
        lay.addWidget(self.label)

        self.setObjectName("chip")
        self.setStyleSheet(
            f"QFrame#chip {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: {t.RADIUS_PILL}px; }}"
        )

    def mousePressEvent(self, e):
        if self._clickable and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class ChipRow(QFrame):
    """Horizontal row of chips with consistent gap."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)

    def add(self, chip: Chip) -> None:
        self._lay.insertWidget(self._lay.count() - 1, chip)

    def clear(self) -> None:
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
