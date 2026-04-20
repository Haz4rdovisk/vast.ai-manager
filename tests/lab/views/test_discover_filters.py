from app.lab.services.huggingface import HFModel
from app.lab.views.discover_view import CATEGORY_MAP, apply_category_heuristic


def _m(name, tags=None):
    return HFModel(
        id=f"author/{name}",
        author="author",
        name=name,
        downloads=0,
        likes=0,
        tags=tags or [],
        files=[],
    )


def test_category_map_has_required_entries():
    assert set(CATEGORY_MAP) == {
        "All",
        "General",
        "Coding",
        "Reasoning",
        "Chat",
        "Multimodal",
        "Embedding",
    }
    assert CATEGORY_MAP["Multimodal"]["pipeline"] == "image-text-to-text"
    assert CATEGORY_MAP["Embedding"]["pipeline"] == "feature-extraction"
    assert CATEGORY_MAP["All"]["pipeline"] is None


def test_heuristic_coding_matches_common_coder_names():
    models = [
        _m("Qwen2.5-Coder-14B-Instruct-GGUF"),
        _m("deepseek-coder-v2-lite-gguf"),
        _m("Meta-Llama-3-8B-Instruct-GGUF"),
        _m("starcoder2-15b-gguf"),
    ]
    names = [model.name for model in apply_category_heuristic("Coding", models)]
    assert "Qwen2.5-Coder-14B-Instruct-GGUF" in names
    assert "deepseek-coder-v2-lite-gguf" in names
    assert "starcoder2-15b-gguf" in names
    assert "Meta-Llama-3-8B-Instruct-GGUF" not in names


def test_heuristic_all_passes_everything_through():
    models = [_m("A"), _m("B")]
    assert apply_category_heuristic("All", models) == models
