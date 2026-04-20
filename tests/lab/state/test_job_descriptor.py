from app.lab.state.models import JobDescriptor, build_job_key


def test_build_key_slugifies_repo_and_appends_quant():
    key = build_job_key(
        iid=35273157,
        repo_id="bartowski/Meta-Llama-3-8B-Instruct-GGUF",
        quant="Q5_K_M",
    )
    assert key == "35273157-bartowski-meta-llama-3-8b-instruct-gguf-q5_k_m"


def test_job_descriptor_defaults_and_init():
    desc = JobDescriptor(
        key="35273157-x-q4",
        iid=35273157,
        repo_id="x/y",
        filename="y-Q4_K_M.gguf",
        quant="Q4_K_M",
        size_bytes=5_300_000_000,
        needs_llamacpp=True,
        remote_state_path="/workspace/.vastai-app/jobs/35273157-x-q4.json",
        remote_log_path="/tmp/install-35273157-x-q4.log",
        started_at=1_700_000_000.0,
    )
    assert desc.stage == "starting"
    assert desc.percent == 0
    assert desc.bytes_downloaded == 0
    assert desc.speed == ""
    assert desc.error is None
