from app.lab.services.runtime import parse_version_output, detect_backend


def test_parse_version_new_format():
    out = "version: 3456 (abcd1234)\nbuilt with MSVC 19"
    assert parse_version_output(out) == "b3456"


def test_parse_version_commit_only():
    out = "version 0 (7f8e9d0)\nbuilt ..."
    assert parse_version_output(out) == "7f8e9d0"


def test_parse_version_missing():
    assert parse_version_output("") is None
    assert parse_version_output("nonsense") is None


def test_detect_backend_cuda_in_help_text():
    assert detect_backend("CUDA: yes\nGPU offload: enabled") == "cuda"


def test_detect_backend_fallback_cpu():
    assert detect_backend("no gpu mentioned") == "cpu"
