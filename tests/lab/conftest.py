import pytest
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app
