"""Tests for LLMfit JSON parser."""
import json
from app.lab.services.remote_llmfit import (
    parse_system, parse_models, parse_json_output,
    build_models_query, build_top_query,
)


MOCK_SYSTEM = {
    "node": {"name": "test", "os": "linux"},
    "system": {
        "cpu_name": "AMD EPYC 7542",
        "cpu_cores": 32,
        "total_ram_gb": 128.0,
        "available_ram_gb": 100.0,
        "has_gpu": True,
        "gpu_name": "NVIDIA A100-SXM4-80GB",
        "gpu_vram_gb": 80.0,
        "gpu_count": 1,
        "backend": "CUDA",
        "gpus": [{"name": "NVIDIA A100-SXM4-80GB", "vram_gb": 80.0}],
    },
}

MOCK_MODELS = {
    "total_models": 2,
    "returned_models": 2,
    "models": [
        {
            "name": "Qwen/Qwen2.5-72B-Instruct",
            "provider": "Qwen",
            "parameter_count": "72B",
            "params_b": 72.0,
            "context_length": 32768,
            "use_case": "General",
            "fit_level": "good",
            "fit_label": "Good",
            "score": 91.5,
            "estimated_tps": 25.0,
            "runtime": "llamacpp",
            "best_quant": "Q4_K_M",
            "memory_required_gb": 42.0,
            "memory_available_gb": 80.0,
        },
        {
            "name": "meta-llama/Llama-3.3-70B-Instruct",
            "provider": "Meta",
            "params_b": 70.0,
            "fit_level": "marginal",
            "score": 78.0,
        },
    ],
}


def test_parse_system():
    sys = parse_system(MOCK_SYSTEM)
    assert sys.cpu_name == "AMD EPYC 7542"
    assert sys.gpu_vram_gb == 80.0
    assert sys.has_gpu is True
    assert len(sys.gpus) == 1


def test_parse_models():
    models = parse_models(MOCK_MODELS)
    assert len(models) == 2
    assert models[0].name == "Qwen/Qwen2.5-72B-Instruct"
    assert models[0].score == 91.5
    assert models[0].fit_level == "good"
    assert models[1].fit_level == "marginal"


def test_parse_json_extracts_from_noise():
    noisy = 'some ssh banner\n{"key": "value"}\nmore noise'
    result = parse_json_output(noisy)
    assert result == {"key": "value"}


def test_parse_json_returns_none_on_bad_input():
    assert parse_json_output("no json here") is None


def test_build_models_query_includes_params():
    q = build_models_query(use_case="coding", limit=10)
    assert "use_case=coding" in q
    assert "limit=10" in q
    assert "runtime=llamacpp" in q


def test_build_top_query():
    q = build_top_query(limit=3, use_case="chat")
    assert "limit=3" in q
    assert "use_case=chat" in q
