"""Hugging Face API client for searching and fetching GGUF models."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import unquote

import requests
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.sqlite_store import DEFAULT_DB_PATH, SQLiteStore

@dataclass
class HFModelFile:
    filename: str
    size_bytes: int
    quantization: str = ""

def _extract_quantization(filename: str) -> str:
    """Extract quantization from GGUF filename (e.g., model-Q4_K_M.gguf)."""
    # Robust regex for GGUF quantizations
    pattern = r'[-.]([qi]?q\d[a-z0-9_]*|f\d+|fp\d+|bf\d+)(?:\.gguf|[-.]|$)'
    match = re.search(pattern, filename.lower())
    if match:
        return match.group(1).upper()
    return ""


def estimate_gguf_size_gb(params_b: float, quant: str) -> float:
    """Estimate GGUF file size in GB based on parameters and quantization."""
    if params_b <= 0:
        return 5.0
    q = quant.upper()
    # Average bits per weight for different quants (closer to llama.cpp reality)
    bits = 4.5  # default
    if "BF16" in q or "FP16" in q or "F16" in q: bits = 16.0
    elif "Q8" in q: bits = 8.5
    elif "Q6" in q: bits = 6.6
    elif "Q5" in q: bits = 5.5
    elif "Q4" in q: bits = 4.5
    elif "Q3" in q: bits = 3.5
    elif "Q2" in q: bits = 2.6
    elif "IQ4" in q: bits = 4.5
    elif "IQ3" in q: bits = 3.5
    elif "IQ2" in q: bits = 2.5
    
    # (params * bits) / 8 bits per byte = size in GB (roughly)
    # Plus standard GGUF overhead (tensors/metadata) - usually around 0.2-0.4GB
    return (params_b * bits / 8.0) + 0.3


@dataclass
class HFModel:
    id: str
    author: str
    name: str
    downloads: int
    likes: int
    tags: list[str] = field(default_factory=list)
    files: list[HFModelFile] = field(default_factory=list)
    details_loaded: bool = False
    details_loading: bool = False
    details_error: str = ""
    
    @property
    def params_b(self) -> float:
        """Attempt to extract parameter count from tags or name."""
        for tag in self.tags:
            if tag.endswith("b") and tag[:-1].replace(".", "").isdigit():
                try:
                    return float(tag[:-1])
                except ValueError:
                    pass
        
        # Fallback to name parsing (e.g., "Llama-3-8B")
        import re
        match = re.search(r'(\d+(?:\.\d+)?)b', self.name.lower())
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 0.0

class HuggingFaceClient:
    BASE_URL = "https://huggingface.co/api"

    def __init__(
        self,
        *,
        cache_db_path: Path | str = DEFAULT_DB_PATH,
        cache_ttl_seconds: int = 24 * 60 * 60,
    ):
        self.cache_ttl_seconds = max(1, int(cache_ttl_seconds))
        self._sqlite = SQLiteStore(cache_db_path)

    def search_gguf_models(
        self,
        query: str = "",
        limit: int = 100,
        pipeline_tag: str | None = None,
        cursor: str | None = None,
        sort_by: str = "downloads",
        full: bool = True,
        raise_on_error: bool = False,
    ) -> tuple[list[HFModel], str | None]:
        """Search for GGUF models.

        Returns ``(models, next_cursor)``. ``next_cursor`` is the Hugging Face
        API cursor for the next page, or ``None`` if the response has no next
        page.
        """
        url = f"{self.BASE_URL}/models"
        params: dict[str, Any] = {
            "search": query,
            "filter": "gguf",
            "sort": sort_by,
            "direction": "-1",
            "limit": limit,
            "full": "true" if full else "false", # Get full model info including siblings (files)
        }
        if pipeline_tag:
            params["pipeline_tag"] = pipeline_tag
        if cursor:
            params["cursor"] = _normalize_cursor(cursor)

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            models = []
            for item in data:
                model_id = item.get("id", "")
                parts = model_id.split("/")
                author = parts[0] if len(parts) > 1 else ""
                name = parts[1] if len(parts) > 1 else model_id
                
                files = []
                for sibling in item.get("siblings", []):
                    filename = sibling.get("rfilename", "")
                    if filename.endswith(".gguf"):
                        # Extract quantization from filename
                        quant = _extract_quantization(filename)
                        
                        size = sibling.get("size")
                        if size is None:
                            size = sibling.get("lfs", {}).get("size", 0)
                        
                        files.append(HFModelFile(
                            filename=filename,
                            size_bytes=size,
                            quantization=quant
                        ))
                
                models.append(HFModel(
                    id=model_id,
                    author=author,
                    name=name,
                    downloads=item.get("downloads", 0),
                    likes=item.get("likes", 0),
                    tags=item.get("tags", []),
                    files=files,
                    details_loaded=has_complete_file_metadata(files),
                ))
            next_cursor = _parse_next_cursor(response.headers.get("Link"))
            return models, next_cursor
        except Exception as e:
            if raise_on_error:
                raise
            print(f"Error fetching from Hugging Face: {e}")
            return [], None

    def get_model_files(self, model_id: str) -> list[HFModelFile]:
        """Get GGUF files and sizes by walking the repo tree recursively."""
        cached = self._load_cached_files(model_id)
        if cached is not None and self._cache_is_fresh(cached["fetched_at"]):
            return cached["files"]

        try:
            pending_dirs = [""]
            seen_dirs: set[str] = set()
            files: list[HFModelFile] = []
            while pending_dirs:
                subpath = pending_dirs.pop(0)
                if subpath in seen_dirs:
                    continue
                seen_dirs.add(subpath)

                url = (
                    f"{self.BASE_URL}/models/{model_id}/tree/main/{subpath}"
                    if subpath
                    else f"{self.BASE_URL}/models/{model_id}/tree/main"
                )
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                for item in data:
                    path = item.get("path", "")
                    item_type = item.get("type", "")
                    if item_type == "directory" and path:
                        pending_dirs.append(path)
                        continue
                    if not path.endswith(".gguf"):
                        continue

                    quant = _extract_quantization(path)
                    size = item.get("size")
                    if size is None:
                        size = item.get("lfs", {}).get("size", 0)

                    files.append(HFModelFile(
                        filename=path,
                        size_bytes=size,
                        quantization=quant
                    ))
            if files:
                self._store_cached_files(model_id, files)
            return files
        except Exception as e:
            print(f"Error fetching tree for {model_id}: {e}")
            if cached is not None:
                return cached["files"]
            return []

    def _cache_is_fresh(self, fetched_at: float) -> bool:
        return (time.time() - float(fetched_at)) < self.cache_ttl_seconds

    def _load_cached_files(self, model_id: str) -> dict[str, Any] | None:
        row = self._sqlite.get_hf_model_cache_entry(model_id)
        if not row:
            return None
        try:
            payload = json.loads(row["files_json"])
        except (TypeError, json.JSONDecodeError):
            return None
        files = [
            HFModelFile(
                filename=str(item.get("filename", "")),
                size_bytes=int(item.get("size_bytes", 0) or 0),
                quantization=str(item.get("quantization", "")),
            )
            for item in payload
            if isinstance(item, dict)
        ]
        return {
            "files": files,
            "fetched_at": float(row.get("fetched_at") or 0.0),
        }

    def _store_cached_files(self, model_id: str, files: list[HFModelFile]) -> None:
        payload = [
            {
                "filename": item.filename,
                "size_bytes": item.size_bytes,
                "quantization": item.quantization,
            }
            for item in files
        ]
        self._sqlite.upsert_hf_model_cache_entry(
            model_id,
            json.dumps(payload, separators=(",", ":")),
            time.time(),
        )


def _parse_next_cursor(link_header: str | None) -> str | None:
    """Extract the next cursor from an RFC 5988-style Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        match = re.search(r"cursor=([^&>\s]+)", part)
        if match:
            return _normalize_cursor(match.group(1))
    return None


def _normalize_cursor(cursor: str | None) -> str | None:
    """Decode cursor tokens until stable so requests does not double-encode them."""
    if not cursor:
        return cursor
    normalized = cursor
    for _ in range(4):
        decoded = unquote(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    return normalized


def has_complete_file_metadata(files: list[HFModelFile]) -> bool:
    """Return True only when all GGUF file entries have a usable size."""
    return bool(files) and all((item.size_bytes or 0) > 0 for item in files)


def model_requires_detail_fetch(model: HFModel) -> bool:
    """Search results can include GGUF siblings with missing sizes.

    Those partial rows are good enough to list the repo, but not good enough to
    lock in quant counts or fit scores. Treat them as pending until the detailed
    tree query fills the sizes in.
    """
    if getattr(model, "details_error", ""):
        return False
    return not has_complete_file_metadata(model.files)
