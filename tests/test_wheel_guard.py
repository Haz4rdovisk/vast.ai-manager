from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QScrollArea, QSpinBox, QWidget

from app.ui.wheel_guard import install_wheel_guard


def _wheel(delta=120):
    return QWheelEvent(
        QPointF(8, 8),
        QPointF(8, 8),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )


def test_wheel_does_not_change_combo_value(qt_app):
    install_wheel_guard(qt_app)
    combo = QComboBox()
    combo.addItems(["one", "two", "three"])
    combo.setCurrentIndex(1)

    qt_app.sendEvent(combo, _wheel(120))

    assert combo.currentIndex() == 1


def test_wheel_does_not_change_spin_values(qt_app):
    install_wheel_guard(qt_app)
    spin = QSpinBox()
    spin.setRange(0, 10)
    spin.setValue(5)
    double_spin = QDoubleSpinBox()
    double_spin.setRange(0, 10)
    double_spin.setValue(5.0)

    qt_app.sendEvent(spin, _wheel(120))
    qt_app.sendEvent(double_spin, _wheel(-120))

    assert spin.value() == 5
    assert double_spin.value() == 5.0


def test_wheel_scrolls_parent_scroll_area(qt_app):
    install_wheel_guard(qt_app)
    scroll = QScrollArea()
    content = QWidget()
    content.setMinimumHeight(1000)
    combo = QComboBox(content)
    combo.addItems(["one", "two"])
    combo.move(10, 600)
    scroll.setWidget(content)
    scroll.resize(200, 200)
    scroll.show()
    qt_app.processEvents()

    scroll.verticalScrollBar().setValue(100)
    qt_app.sendEvent(combo, _wheel(-120))

    assert scroll.verticalScrollBar().value() > 100
