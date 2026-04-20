from unittest.mock import Mock, patch

from app.lab.services.huggingface import HuggingFaceClient


def _fake_response(payload, link_header=None):
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.headers = {"Link": link_header} if link_header else {}
    resp.raise_for_status = Mock()
    return resp


def test_search_passes_pipeline_tag_and_limit():
    client = HuggingFaceClient()
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response([])
        client.search_gguf_models(query="llama", limit=100, pipeline_tag="text-generation")
        params = mock_get.call_args.kwargs["params"]
        assert params["pipeline_tag"] == "text-generation"
        assert params["limit"] == 100
        assert params["search"] == "llama"
        assert params["filter"] == "gguf"


def test_search_returns_models_and_cursor():
    client = HuggingFaceClient()
    payload = [{
        "id": "bartowski/Meta-Llama-3-8B-Instruct-GGUF",
        "downloads": 12345,
        "likes": 42,
        "tags": ["gguf", "llama"],
        "siblings": [
            {"rfilename": "meta-llama-3-8b-instruct-Q4_K_M.gguf", "size": 4700000000},
        ],
    }]
    link = '<https://huggingface.co/api/models?cursor=XYZ>; rel="next"'
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response(payload, link_header=link)
        models, cursor = client.search_gguf_models(query="llama")
        assert len(models) == 1
        assert models[0].id == "bartowski/Meta-Llama-3-8B-Instruct-GGUF"
        assert models[0].files[0].quantization == "Q4_K_M"
        assert cursor == "XYZ"
