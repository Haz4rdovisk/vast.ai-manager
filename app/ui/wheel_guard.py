"""Global wheel guard for inputs that otherwise change values on hover."""
from __future__ import annotations

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QComboBox,
)


class WheelGuard(QObject):
    """Prevent accidental mouse-wheel value changes on combo/spin inputs.

    If the input lives inside a scroll area, wheel movement scrolls that area.
    Otherwise the wheel event is swallowed so hovering over a field cannot
    silently change app settings or filters.
    """

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Wheel:
            return super().eventFilter(obj, event)
        if not isinstance(obj, (QComboBox, QAbstractSpinBox)):
            return super().eventFilter(obj, event)

        delta = (
            event.pixelDelta().y()
            if not event.pixelDelta().isNull()
            else event.angleDelta().y()
        )
        scroll = _ancestor_scroll_area(obj)
        if delta and scroll is not None:
            bar = scroll.verticalScrollBar()
            bar.setValue(bar.value() - delta)
        event.accept()
        return True


def _ancestor_scroll_area(obj) -> QAbstractScrollArea | None:
    parent = obj.parentWidget() if hasattr(obj, "parentWidget") else None
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return parent
        parent = parent.parentWidget() if hasattr(parent, "parentWidget") else None
    return None


def install_wheel_guard(app: QApplication) -> WheelGuard:
    guard = getattr(app, "_vast_wheel_guard", None)
    if guard is None:
        guard = WheelGuard(app)
        app.installEventFilter(guard)
        setattr(app, "_vast_wheel_guard", guard)
    return guard

