"""Hugging Face API client for searching and fetching GGUF models."""
from __future__ import annotations

import re

import requests
from dataclasses import dataclass, field
from typing import Any

@dataclass
class HFModelFile:
    filename: str
    size_bytes: int
    quantization: str = ""

def _extract_quantization(filename: str) -> str:
    """Extract quantization from GGUF filename (e.g., model-Q4_K_M.gguf)."""
    # Robust regex for GGUF quantizations
    # Handles:
    # - Delimiters: - or .
    # - Standard quants: Q4_K_M, Q8_0, etc.
    # - I-quants: IQ2_XXS, IQ4_NL, etc.
    # - Floating point: FP16, BF16, F16, etc.
    # [qi]?q\d matches q4, iq4, etc.
    pattern = r'[-.]([qi]?q\d[a-z0-9_]*|f\d+|fp\d+|bf\d+)(?:\.gguf|[-.]|$)'
    match = re.search(pattern, filename.lower())
    if match:
        return match.group(1).upper()
    return ""


@dataclass
class HFModel:
    id: str
    author: str
    name: str
    downloads: int
    likes: int
    tags: list[str] = field(default_factory=list)
    files: list[HFModelFile] = field(default_factory=list)
    
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

    def search_gguf_models(
        self,
        query: str = "",
        limit: int = 100,
        pipeline_tag: str | None = None,
        cursor: str | None = None,
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
            "sort": "downloads",
            "direction": "-1",
            "limit": limit,
            "full": "True", # Get full model info including siblings (files)
        }
        if pipeline_tag:
            params["pipeline_tag"] = pipeline_tag
        if cursor:
            params["cursor"] = cursor
        
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
                        
                        files.append(HFModelFile(
                            filename=filename,
                            size_bytes=sibling.get("size") or sibling.get("lfs", {}).get("size", 0),
                            quantization=quant
                        ))
                
                models.append(HFModel(
                    id=model_id,
                    author=author,
                    name=name,
                    downloads=item.get("downloads", 0),
                    likes=item.get("likes", 0),
                    tags=item.get("tags", []),
                    files=files
                ))
            next_cursor = _parse_next_cursor(response.headers.get("Link"))
            return models, next_cursor
        except Exception as e:
            print(f"Error fetching from Hugging Face: {e}")
            return [], None

    def get_model_files(self, model_id: str) -> list[HFModelFile]:
        """Get specific files and sizes by querying the repo tree."""
        # /tree/main gives us accurate sizes that /api/models/{id} lacks for siblings
        url = f"{self.BASE_URL}/models/{model_id}/tree/main"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            files = []
            for item in data:
                path = item.get("path", "")
                if path.endswith(".gguf"):
                    # Extract quantization from filename
                    quant = _extract_quantization(path)
                    
                    files.append(HFModelFile(
                        filename=path,
                        size_bytes=item.get("size") or item.get("lfs", {}).get("size", 0),
                        quantization=quant
                    ))
            return files
        except Exception as e:
            print(f"Error fetching tree for {model_id}: {e}")
            return []


def _parse_next_cursor(link_header: str | None) -> str | None:
    """Extract the next cursor from an RFC 5988-style Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        match = re.search(r"cursor=([^&>\s]+)", part)
        if match:
            return match.group(1)
    return None
