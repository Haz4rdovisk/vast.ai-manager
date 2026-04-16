from app.lab.services.downloader import build_hf_url, humanize_speed


def test_build_hf_url_default():
    url = build_hf_url("bartowski/Qwen2.5-7B-Instruct-GGUF",
                       "Qwen2.5-7B-Instruct-Q4_K_M.gguf")
    assert url == ("https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
                   "/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf")


def test_build_hf_url_with_revision():
    url = build_hf_url("foo/bar", "x.gguf", revision="v1")
    assert "/resolve/v1/" in url


def test_humanize_speed():
    assert humanize_speed(0) == "0 B/s"
    assert humanize_speed(2048).endswith("KB/s")
    assert humanize_speed(10 * 1024 * 1024).endswith("MB/s")
