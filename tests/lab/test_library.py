import struct
from app.lab.services.library import scan_directory


def _write_fake_gguf(path, arch="llama", ctx=8192):
    def s(v):
        b = v.encode("utf-8")
        return struct.pack("<Q", len(b)) + b
    kvs = s("general.architecture") + struct.pack("<I", 8) + s(arch)
    kvs += s("llama.context_length") + struct.pack("<I", 4) + struct.pack("<I", ctx)
    header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 2) + kvs
    path.write_bytes(header + b"\x00" * 1024)


def test_scan_empty_dir(tmp_path):
    assert scan_directory(str(tmp_path)) == []


def test_scan_finds_gguf_only(tmp_path):
    (tmp_path / "readme.txt").write_text("hi")
    a = tmp_path / "Qwen2.5-7B-Q4_K_M.gguf"
    _write_fake_gguf(a, "qwen2", 32768)
    items = scan_directory(str(tmp_path))
    assert len(items) == 1
    m = items[0]
    assert m.name == "Qwen2.5-7B-Q4_K_M"
    assert m.architecture == "qwen2"
    assert m.context_length == 32768
    assert m.quant == "Q4_K_M"
    assert m.size_bytes > 0
    assert m.valid is True


def test_scan_marks_invalid_gguf(tmp_path):
    bad = tmp_path / "broken.gguf"
    bad.write_bytes(b"NOPE" + b"\x00" * 128)
    items = scan_directory(str(tmp_path))
    assert len(items) == 1
    assert items[0].valid is False
    assert items[0].error is not None


def test_scan_handles_missing_dir():
    assert scan_directory("/nonexistent/path/xyz") == []
