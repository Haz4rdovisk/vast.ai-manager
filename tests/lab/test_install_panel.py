from app.lab.state.models import DownloadJob, InstallJob
from app.lab.state.store import LabStore
from app.lab.views.install_panel import InstallPanel
from app.ui.components.progress_panel import StepState


def test_panel_starts_with_pending_steps(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    panel = InstallPanel(store)
    assert panel.llamacpp_progress.step_state("apt") == StepState.PENDING
    assert panel.llamacpp_progress.step_state("build") == StepState.PENDING


def test_install_job_updates_panel_steps(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    panel = InstallPanel(store)
    store.update_install_job(
        1,
        InstallJob(kind="llamacpp", stage="cmake", percent=50),
    )
    assert panel.llamacpp_progress.step_state("apt") == StepState.DONE
    assert panel.llamacpp_progress.step_state("clone") == StepState.DONE
    assert panel.llamacpp_progress.step_state("cmake") == StepState.RUNNING


def test_download_job_updates_download_progress(qt_app):
    store = LabStore()
    store.selected_instance_id = 1
    panel = InstallPanel(store)
    store.update_download_job(
        1,
        DownloadJob(
            repo_id="r",
            filename="f",
            percent=73,
            bytes_downloaded=0,
            bytes_total=0,
            speed="14.2M",
        ),
    )
    assert panel.download_progress.percent() == 73
