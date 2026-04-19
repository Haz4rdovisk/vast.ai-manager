from PySide6.QtWidgets import QWidget

from app.ui.components.progress_panel import ProgressPanel, StepState


def test_progress_panel_constructs_with_steps(qt_app):
    panel = ProgressPanel(["apt", "clone", "cmake", "build"])
    assert isinstance(panel, QWidget)
    assert panel.step_state("apt") == StepState.PENDING


def test_progress_panel_set_step_state(qt_app):
    panel = ProgressPanel(["apt", "clone"])
    panel.set_step("apt", StepState.RUNNING)
    assert panel.step_state("apt") == StepState.RUNNING
    panel.set_step("apt", StepState.DONE)
    assert panel.step_state("apt") == StepState.DONE


def test_progress_panel_append_log_line(qt_app):
    panel = ProgressPanel(["apt"])
    panel.append_log("hello")
    panel.append_log("world")
    assert "hello" in panel.log_text()
    assert "world" in panel.log_text()


def test_progress_panel_set_percent(qt_app):
    panel = ProgressPanel(["apt"])
    panel.set_percent(42)
    assert panel.percent() == 42
