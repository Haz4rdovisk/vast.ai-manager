from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from app.config import ConfigStore
from app import theme
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Vast.ai Manager")
    app.setStyleSheet(theme.STYLESHEET)

    store = ConfigStore()
    win = MainWindow(store)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
