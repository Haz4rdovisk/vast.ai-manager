"""Shared visual primitives for the Lab. Every widget sets objectName/role
properties so the scoped stylesheet can target them. No business logic here."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget
from PySide6.QtCore import Qt
from app.lab import theme as t


class GlassCard(QFrame):
    """Primary surface. Rounded, bordered, layered over the shell bg."""
    def __init__(self, raised: bool = False, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card-raised" if raised else "card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        self._lay.setSpacing(t.SPACE_3)

    def body(self) -> QVBoxLayout:
        return self._lay


class SectionHeader(QWidget):
    """Eyebrow + title pair. Used at the top of every view and in cards."""
    def __init__(self, eyebrow: str, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        e = QLabel(eyebrow)
        e.setProperty("role", "section")
        tl = QLabel(title)
        tl.setProperty("role", "title")
        lay.addWidget(e)
        lay.addWidget(tl)


class StatusPill(QLabel):
    """Small colored chip. `level` controls dot + text color."""
    def __init__(self, text: str, level: str = "info", parent=None):
        super().__init__(parent)
        self.set_status(text, level)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def set_status(self, text: str, level: str):
        color = t.health_color(level)
        self.setText(f"\u25CF  {text}")
        self.setStyleSheet(
            f"QLabel {{ color: {color}; background: {t.SURFACE_2};"
            f" border: 1px solid {t.BORDER_MED};"
            f" border-radius: 999px; padding: 4px 10px;"
            f" font-size: 9pt; font-weight: 600; }}"
        )


class HealthDot(QLabel):
    """Tiny colored dot — inline health signal, no label."""
    def __init__(self, level: str = "info", parent=None):
        super().__init__(parent)
        self.set_level(level)

    def set_level(self, level: str):
        color = t.health_color(level)
        self.setFixedSize(10, 10)
        self.setStyleSheet(
            f"QLabel {{ background: {color}; border-radius: 5px; }}"
        )


class MetricTile(GlassCard):
    """Single big number + label + optional delta line. For Machine + Overview."""
    def __init__(self, label: str, value: str = "\u2014", hint: str = "", parent=None):
        super().__init__(parent=parent)
        self._lay.setContentsMargins(t.SPACE_4, t.SPACE_3, t.SPACE_4, t.SPACE_3)
        self._lay.setSpacing(2)
        self._label = QLabel(label)
        self._label.setProperty("role", "section")
        self._value = QLabel(value)
        self._value.setProperty("role", "display")
        self._hint = QLabel(hint)
        self._hint.setProperty("role", "muted")
        self._hint.setStyleSheet(f"font-size: 9pt; color: {t.TEXT_MID};")
        self._lay.addWidget(self._label)
        self._lay.addWidget(self._value)
        self._lay.addWidget(self._hint)

    def set_value(self, value: str, hint: str = ""):
        self._value.setText(value)
        self._hint.setText(hint)


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
