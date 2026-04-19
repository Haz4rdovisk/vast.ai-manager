from app.lab.services.fit_scorer import InstanceFitScorer
from app.lab.services.model_catalog import ModelCatalog
from app.lab.state.models import RemoteSystem
from app.lab.state.store import LabStore


def test_store_holds_scored_models_per_instance(qt_app):
    store = LabStore()
    store.set_remote_system(
        42,
        RemoteSystem(
            cpu_cores=16,
            ram_total_gb=64,
            has_gpu=True,
            gpu_vram_gb=24,
        ),
    )
    catalog = ModelCatalog.bundled()
    scorer = InstanceFitScorer()
    scored = [scorer.score(entry, store.get_state(42).system) for entry in catalog.entries]
    store.set_scored_models(42, scored)
    assert len(store.get_state(42).scored_models) == len(catalog.entries)


def test_store_emits_signal_on_scored_update(qt_app):
    store = LabStore()
    store.selected_instance_id = 7
    received: list = []
    store.scored_models_changed.connect(received.append)
    store.set_scored_models(7, [])
    assert received == [[]]


def test_install_job_progress_signal(qt_app):
    from app.lab.state.models import InstallJob

    store = LabStore()
    events: list = []
    store.install_job_changed.connect(
        lambda iid, job: events.append((iid, job.stage, job.percent))
    )
    job = InstallJob(kind="llamacpp", stage="cmake", percent=20, log_tail=[])
    store.update_install_job(5, job)
    assert events == [(5, "cmake", 20)]


def test_download_job_progress_signal(qt_app):
    from app.lab.state.models import DownloadJob

    store = LabStore()
    events: list = []
    store.download_job_changed.connect(lambda iid, job: events.append((iid, job.percent)))
    store.update_download_job(
        5,
        DownloadJob(
            repo_id="foo/bar",
            filename="bar.gguf",
            percent=37,
            bytes_downloaded=0,
            bytes_total=0,
            speed="",
        ),
    )
    assert events == [(5, 37)]
