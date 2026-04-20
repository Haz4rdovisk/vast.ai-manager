from app.lab.services.remote_setup import (
    parse_check_job_output,
    script_cancel_job,
    script_check_job,
    script_download_model,
    script_install_llamacpp,
)


def test_install_llamacpp_accepts_job_key_and_writes_state():
    script = script_install_llamacpp(job_key="iid-x-q")
    assert "write_state" in script
    assert "/workspace/.vastai-app/jobs/iid-x-q.json" in script
    assert "write_state apt" in script
    assert "write_state clone" in script
    assert "write_state cmake" in script
    assert "write_state build" in script
    assert "write_state done 100" in script


def test_install_llamacpp_without_job_key_keeps_legacy_output():
    assert "INSTALL_LLAMACPP_DONE" in script_install_llamacpp()


def test_download_model_accepts_job_key_and_writes_state():
    script = script_download_model(
        repo_id="bartowski/Meta-Llama-3-8B-Instruct-GGUF",
        filename="meta-llama-3-8b-instruct-Q4_K_M.gguf",
        job_key="iid-y-q",
    )
    assert "/workspace/.vastai-app/jobs/iid-y-q.json" in script
    assert "write_state download" in script
    assert "write_state done 100" in script


def test_check_cancel_and_parser():
    assert "RUNNING" in script_check_job("iid-x-q")
    assert "kill" in script_cancel_job("iid-x-q")
    status, state = parse_check_job_output(
        'RUNNING\n{"pid": 123, "stage": "download", "percent": 43}\n'
    )
    assert status == "RUNNING"
    assert state["percent"] == 43
    assert parse_check_job_output("garbage\n") == ("MISSING", {})
