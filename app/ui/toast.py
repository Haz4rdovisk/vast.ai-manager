from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from app import theme as t


class Toast(QFrame):
    _stack: list["Toast"] = []

    def __init__(self, parent: QWidget, message: str, level: str = "info", duration_ms: int = 3000):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        
        bg = {
            "success": t.SURFACE_2,
            "error": t.SURFACE_2,
            "warning": t.SURFACE_2,
            "info": t.SURFACE_2
        }.get(level, t.SURFACE_2)

        icon_color = {
            "success": t.OK,
            "error": t.ERR,
            "warning": t.WARN,
            "info": t.INFO
        }.get(level, t.TEXT)

        border = {
            "success": t.OK,
            "error": t.ERR,
            "warning": t.WARN,
            "info": t.INFO
        }.get(level, t.BORDER_MED)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                color: {t.TEXT};
                border: 1px solid {t.BORDER_MED};
                border-left: 4px solid {border};
                border-radius: 6px;
                padding: 4px;
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        self.icon_lbl = QLabel()
        sym = {"success": "✓", "error": "✗", "warning": "⚠", "info": "ℹ"}.get(level, "ℹ")
        self.icon_lbl.setText(sym)
        self.icon_lbl.setStyleSheet(f"color: {icon_color}; font-weight: bold; font-family: {t.FONT_MONO}; font-size: 14pt; border: none; padding: 0; background: transparent;")
        self.icon_lbl.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.msg_lbl = QLabel(message)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet(f"color: {t.TEXT}; font-size: 10pt; border: none; padding: 0; background: transparent;")

        lay.addWidget(self.icon_lbl)
        lay.addWidget(self.msg_lbl, 1)

        self.setFixedWidth(340)
        self.adjustSize()

        # Fade in
        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.anim = QPropertyAnimation(self.opacity, b"opacity", self)
        self.anim.setDuration(300)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

        Toast._stack.append(self)
        self._reposition_stack()
        self.show()
        self.raise_()
        self.anim.start()

        QTimer.singleShot(duration_ms, self._fade_out)

    def mousePressEvent(self, event):
        self._fade_out()
        super().mousePressEvent(event)

    def _fade_out(self):
        self.anim.stop()
        self.anim.setStartValue(self.opacity.opacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self._close)
        self.anim.start()

    def _close(self):
        if self in Toast._stack:
            Toast._stack.remove(self)
        self.close()
        self.deleteLater()
        self._reposition_stack()

    def _reposition_stack(self):
        parent = self.parent()
        if parent is None:
            return
        margin = 20
        y = parent.height() - margin
        for toast in reversed(Toast._stack):
            y -= toast.height() + 8
            x = parent.width() - toast.width() - margin
            toast.move(x, y)
