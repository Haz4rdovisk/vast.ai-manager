"""Local model library. Scans a directory for .gguf files, reads their
headers, and returns ModelFile records."""
from __future__ import annotations
import os
from app.lab.services.gguf import parse_gguf_header
from app.lab.state.models import ModelFile


def scan_directory(path: str) -> list[ModelFile]:
    if not path or not os.path.isdir(path):
        return []
    out: list[ModelFile] = []
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        return []
    for name in entries:
        if not name.lower().endswith(".gguf"):
            continue
        full = os.path.join(path, name)
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        display = os.path.splitext(name)[0]
        meta = parse_gguf_header(full)
        if meta is None:
            out.append(ModelFile(
                path=full, name=display, size_bytes=size,
                valid=False, error="invalid or unreadable GGUF header",
            ))
            continue
        out.append(ModelFile(
            path=full, name=display, size_bytes=size,
            architecture=meta.get("architecture", ""),
            param_count_b=float(meta.get("param_count_b", 0.0) or 0.0),
            context_length=int(meta.get("context_length", 0) or 0),
            quant=meta.get("quant", ""),
            valid=True,
        ))
    return out
