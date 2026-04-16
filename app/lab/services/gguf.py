"""Bounded GGUF v3 header reader. Reads only enough to extract architecture,
context length, and param count. Safe against arbitrary files \u2014 bails out on
bad magic, unknown types, or an unreasonable KV count."""
from __future__ import annotations
import os
import re
import struct


_T_UINT8, _T_INT8 = 0, 1
_T_UINT16, _T_INT16 = 2, 3
_T_UINT32, _T_INT32 = 4, 5
_T_FLOAT32, _T_BOOL = 6, 7
_T_STRING, _T_ARRAY = 8, 9
_T_UINT64, _T_INT64 = 10, 11
_T_FLOAT64 = 12

_SCALAR_FMT = {
    _T_UINT8: "<B", _T_INT8: "<b",
    _T_UINT16: "<H", _T_INT16: "<h",
    _T_UINT32: "<I", _T_INT32: "<i",
    _T_FLOAT32: "<f", _T_BOOL: "<?",
    _T_UINT64: "<Q", _T_INT64: "<q",
    _T_FLOAT64: "<d",
}

_MAX_KVS = 4096
_MAX_BYTES = 2 * 1024 * 1024


def _infer_quant_from_name(filename: str) -> str:
    m = re.search(r"[.\-_]([QIq]\d[a-zA-Z0-9_]+|BF16|F16|F32|bf16|f16|f32)", filename)
    return m.group(1).upper() if m else ""


def _read_string(buf: memoryview, off: int) -> tuple[str, int]:
    (ln,) = struct.unpack_from("<Q", buf, off); off += 8
    s = bytes(buf[off:off + ln]).decode("utf-8", errors="replace")
    return s, off + ln


def _skip_value(buf: memoryview, off: int, type_id: int) -> int:
    if type_id in _SCALAR_FMT:
        return off + struct.calcsize(_SCALAR_FMT[type_id])
    if type_id == _T_STRING:
        _, off = _read_string(buf, off)
        return off
    if type_id == _T_ARRAY:
        (inner,) = struct.unpack_from("<I", buf, off); off += 4
        (count,) = struct.unpack_from("<Q", buf, off); off += 8
        for _ in range(count):
            off = _skip_value(buf, off, inner)
        return off
    raise ValueError(f"unknown gguf type id {type_id}")


def _read_value(buf: memoryview, off: int, type_id: int):
    if type_id in _SCALAR_FMT:
        fmt = _SCALAR_FMT[type_id]
        (v,) = struct.unpack_from(fmt, buf, off)
        return v, off + struct.calcsize(fmt)
    if type_id == _T_STRING:
        return _read_string(buf, off)
    return None, _skip_value(buf, off, type_id)


def parse_gguf_header(path: str) -> dict | None:
    """Return a dict with any of: architecture, context_length, param_count_b,
    block_count, embedding_length, quant. None on invalid/unreadable files."""
    try:
        size = os.path.getsize(path)
        read_n = min(_MAX_BYTES, size)
        with open(path, "rb") as f:
            raw = f.read(read_n)
    except OSError:
        return None
    if len(raw) < 24 or raw[:4] != b"GGUF":
        return None
    buf = memoryview(raw)
    (version,) = struct.unpack_from("<I", buf, 4)
    (kv_count,) = struct.unpack_from("<Q", buf, 16)
    if kv_count > _MAX_KVS:
        return None
    off = 24

    meta: dict = {"_version": version}
    for _ in range(kv_count):
        try:
            key, off = _read_string(buf, off)
            (type_id,) = struct.unpack_from("<I", buf, off); off += 4
            val, off = _read_value(buf, off, type_id)
        except (struct.error, ValueError, UnicodeDecodeError):
            break
        if key == "general.architecture":
            meta["architecture"] = val
        elif key.endswith(".context_length"):
            meta["context_length"] = int(val) if val is not None else 0
        elif key.endswith(".block_count"):
            meta["block_count"] = int(val) if val is not None else 0
        elif key.endswith(".embedding_length"):
            meta["embedding_length"] = int(val) if val is not None else 0
        elif key == "general.name":
            meta["name"] = val
        elif key == "general.parameter_count":
            try:
                meta["param_count_b"] = int(val) / 1e9
            except (TypeError, ValueError):
                pass

    meta["quant"] = _infer_quant_from_name(os.path.basename(path))
    return meta
