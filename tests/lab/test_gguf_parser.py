import struct
from app.lab.services.gguf import parse_gguf_header, _infer_quant_from_name


def _s(v: str) -> bytes:
    b = v.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def _pack_kv_string(key: str, value: str) -> bytes:
    # type id 8 = STRING
    return _s(key) + struct.pack("<I", 8) + _s(value)


def _pack_kv_u32(key: str, value: int) -> bytes:
    # type id 4 = UINT32
    return _s(key) + struct.pack("<I", 4) + struct.pack("<I", value)


def test_parse_minimal_gguf_header(tmp_path):
    path = tmp_path / "tiny.gguf"
    kvs = _pack_kv_string("general.architecture", "llama")
    kvs += _pack_kv_u32("llama.context_length", 8192)
    header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", 2) + kvs
    path.write_bytes(header + b"\x00" * 64)
    meta = parse_gguf_header(str(path))
    assert meta is not None
    assert meta["architecture"] == "llama"
    assert meta["context_length"] == 8192


def test_parse_rejects_bad_magic(tmp_path):
    path = tmp_path / "bad.gguf"
    path.write_bytes(b"NOPE" + b"\x00" * 128)
    assert parse_gguf_header(str(path)) is None


def test_infer_quant_from_name():
    assert _infer_quant_from_name("Qwen2.5-7B-Instruct-Q4_K_M.gguf") == "Q4_K_M"
    assert _infer_quant_from_name("llama-3-8b.Q8_0.gguf") == "Q8_0"
    assert _infer_quant_from_name("model.bf16.gguf") == "BF16"
    assert _infer_quant_from_name("random.gguf") == ""
