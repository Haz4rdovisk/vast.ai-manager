"""Client for the LLMfit REST API running on a remote Vast.ai instance.
Queries are piped through SSH run_script to avoid needing a second tunnel."""
from __future__ import annotations
import json
from app.lab.state.models import RemoteSystem, RemoteModel, RemoteGPU


def parse_system(raw: dict) -> RemoteSystem:
    """Parse /api/v1/system JSON into RemoteSystem."""
    s = raw.get("system", {})
    gpus = [RemoteGPU(name=g.get("name", ""), vram_gb=g.get("vram_gb"))
            for g in s.get("gpus", [])]
    return RemoteSystem(
        cpu_name=s.get("cpu_name", ""),
        cpu_cores=s.get("cpu_cores", 0),
        ram_total_gb=s.get("total_ram_gb", 0.0),
        ram_available_gb=s.get("available_ram_gb", 0.0),
        has_gpu=s.get("has_gpu", False),
        gpu_name=s.get("gpu_name"),
        gpu_vram_gb=s.get("gpu_vram_gb"),
        gpu_count=s.get("gpu_count", 0),
        backend=s.get("backend", ""),
        gpus=gpus,
    )


def parse_models(raw: dict) -> list[RemoteModel]:
    """Parse /api/v1/models JSON into list of RemoteModel."""
    out: list[RemoteModel] = []
    for m in raw.get("models", []):
        out.append(RemoteModel(
            name=m.get("name", ""),
            provider=m.get("provider", ""),
            parameter_count=m.get("parameter_count", ""),
            params_b=m.get("params_b", 0.0),
            context_length=m.get("context_length", 0),
            use_case=m.get("use_case", ""),
            category=m.get("category", ""),
            fit_level=m.get("fit_level", ""),
            fit_label=m.get("fit_label", ""),
            run_mode=m.get("run_mode", ""),
            score=m.get("score", 0.0),
            score_components=m.get("score_components", {}),
            estimated_tps=m.get("estimated_tps", 0.0),
            runtime=m.get("runtime", ""),
            runtime_label=m.get("runtime_label", ""),
            best_quant=m.get("best_quant", ""),
            memory_required_gb=m.get("memory_required_gb", 0.0),
            memory_available_gb=m.get("memory_available_gb", 0.0),
            utilization_pct=m.get("utilization_pct", 0.0),
            notes=m.get("notes", []),
            gguf_sources=m.get("gguf_sources", []),
        ))
    return out


def build_system_query() -> str:
    """SSH script to query LLMfit system endpoint."""
    return "curl -sf http://127.0.0.1:8787/api/v1/system 2>/dev/null"


def build_models_query(use_case: str = "", min_fit: str = "marginal",
                       limit: int = 30, sort: str = "score",
                       search: str = "") -> str:
    """SSH script to query LLMfit models endpoint."""
    params = [f"limit={limit}", f"min_fit={min_fit}", f"sort={sort}",
              "runtime=llamacpp"]
    if use_case and use_case != "all":
        params.append(f"use_case={use_case}")
    if search:
        params.append(f"search={search}")
    qs = "&".join(params)
    return f'curl -sf "http://127.0.0.1:8787/api/v1/models?{qs}" 2>/dev/null'


def build_top_query(limit: int = 5, use_case: str = "") -> str:
    """SSH script to query LLMfit top models."""
    params = [f"limit={limit}", "min_fit=good", "sort=score",
              "runtime=llamacpp"]
    if use_case and use_case != "all":
        params.append(f"use_case={use_case}")
    qs = "&".join(params)
    return f'curl -sf "http://127.0.0.1:8787/api/v1/models/top?{qs}" 2>/dev/null'


def parse_json_output(output: str) -> dict | None:
    """Try to extract JSON from SSH output (may have noise before/after)."""
    # Find first { and last }
    start = output.find("{")
    end = output.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        return json.loads(output[start:end + 1])
    except json.JSONDecodeError:
        return None
