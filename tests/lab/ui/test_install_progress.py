from app.ui.components.install_progress import STAGES, InstallProgress


def test_set_stage_marks_priors_done(qt_app):
    widget = InstallProgress()
    widget.set_stage("build", percent=45)
    assert STAGES == ["apt", "clone", "cmake", "build", "download", "verify"]
    assert widget.stage_state("apt") == "done"
    assert widget.stage_state("clone") == "done"
    assert widget.stage_state("cmake") == "done"
    assert widget.stage_state("build") == "running"
    assert widget.stage_state("download") == "pending"
    assert widget.percent() == 45


def test_set_stage_failed_marks_current_failed(qt_app):
    widget = InstallProgress()
    widget.set_stage("cmake", percent=25)
    widget.set_stage("failed", percent=25)
    assert widget.stage_state("cmake") == "failed"
