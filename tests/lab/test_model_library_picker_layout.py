from PySide6.QtWidgets import QComboBox

from app.lab.state.store import LabStore
from app.lab.views.models_view import ConfigurePanel


def test_model_library_picker_row_prioritizes_model_width(qt_app):
    panel = ConfigurePanel(LabStore())

    assert panel._picker_grid.columnStretch(0) < panel._picker_grid.columnStretch(1)
    assert panel._model_picker.minimumContentsLength() > panel._instance_combo.minimumContentsLength()
    assert panel._model_picker.sizeAdjustPolicy() == QComboBox.AdjustToMinimumContentsLengthWithIcon
