"""Tests for remote setup script builders."""
from app.lab.services.remote_setup import (
    script_check_setup, parse_probe_output,
    script_list_models, parse_model_list,
    script_download_model, script_install_llmfit,
    script_install_llamacpp, script_stop_llama_server,
)


def test_parse_probe_output():
    output = """
===PROBE_START===
LLMFIT_INSTALLED=yes
LLMFIT_VERSION=0.15.0
LLMFIT_SERVING=yes
LLAMACPP_INSTALLED=yes
LLAMACPP_PATH=/opt/llama.cpp/build/bin/llama-server
LLAMA_RUNNING=no
LLAMA_MODEL=
MODEL_COUNT=3
===PROBE_END===
"""
    result = parse_probe_output(output)
    assert result["LLMFIT_INSTALLED"] == "yes"
    assert result["LLMFIT_SERVING"] == "yes"
    assert result["LLAMACPP_PATH"] == "/opt/llama.cpp/build/bin/llama-server"
    assert result["MODEL_COUNT"] == "3"
    assert result["LLAMA_RUNNING"] == "no"


def test_parse_model_list():
    output = """
===MODELS_START===
GGUF|/workspace/qwen2.5-7b-q4_k_m.gguf|4500000000
GGUF|/models/llama3-8b-q5.gguf|6200000000
===MODELS_END===
"""
    models = parse_model_list(output)
    assert len(models) == 2
    assert models[0]["filename"] == "qwen2.5-7b-q4_k_m.gguf"
    assert models[0]["size_bytes"] == 4500000000
    assert "4.2 GB" in models[0]["size_display"]
    assert models[1]["path"] == "/models/llama3-8b-q5.gguf"


def test_parse_empty_model_list():
    output = """
===MODELS_START===
===MODELS_END===
"""
    models = parse_model_list(output)
    assert models == []


def test_download_script_contains_url():
    script = script_download_model("TheBloke/model", "model.Q4.gguf")
    assert "TheBloke/model" in script
    assert "model.Q4.gguf" in script
    assert "huggingface.co" in script


def test_install_scripts_exist():
    assert "llmfit" in script_install_llmfit()
    assert "llama.cpp" in script_install_llamacpp()
    assert "pkill" in script_stop_llama_server()


def test_check_setup_script_has_markers():
    script = script_check_setup()
    assert "===PROBE_START===" in script
    assert "LLMFIT_INSTALLED" in script
    assert "LLAMACPP_INSTALLED" in script
    assert "MODEL_COUNT" in script
