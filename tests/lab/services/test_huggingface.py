import sqlite3
import time
from pathlib import Path
from unittest.mock import Mock, patch

from app.lab.services.huggingface import (
    HFModel,
    HFModelFile,
    HuggingFaceClient,
    _normalize_cursor,
    has_complete_file_metadata,
    model_requires_detail_fetch,
)


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
        client.search_gguf_models(query="llama", limit=100, pipeline_tag="text-generation", sort_by="trendingScore")
        params = mock_get.call_args.kwargs["params"]
        assert params["pipeline_tag"] == "text-generation"
        assert params["limit"] == 100
        assert params["search"] == "llama"
        assert params["filter"] == "gguf"
        assert params["sort"] == "trendingScore"


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


def test_cursor_is_normalized_before_reuse():
    client = HuggingFaceClient()
    encoded_cursor = "abc%253D%253D"
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response([])
        client.search_gguf_models(cursor=encoded_cursor)
        params = mock_get.call_args.kwargs["params"]

    assert params["cursor"] == "abc=="


def test_normalize_cursor_decodes_until_stable():
    assert _normalize_cursor("abc%253D%253D") == "abc=="
    assert _normalize_cursor("abc%3D%3D") == "abc=="
    assert _normalize_cursor("abc==") == "abc=="


def test_detail_fetch_helpers_require_non_zero_sizes():
    complete = [HFModelFile("model-Q4_K_M.gguf", 4_700_000_000, "Q4_K_M")]
    partial = [HFModelFile("model-Q4_K_M.gguf", 0, "Q4_K_M")]

    assert has_complete_file_metadata(complete) is True
    assert has_complete_file_metadata(partial) is False
    assert model_requires_detail_fetch(
        HFModel(
            id="org/model",
            author="org",
            name="model",
            downloads=1,
            likes=1,
            files=partial,
        )
    ) is True


def test_get_model_files_walks_nested_gguf_directory():
    client = HuggingFaceClient()
    root_payload = [
        {"type": "directory", "path": "gguf"},
        {"type": "file", "path": "README.md", "size": 100},
    ]
    gguf_payload = [
        {"type": "file", "path": "gguf/model-f16.gguf", "size": 123456789},
    ]

    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.side_effect = [
            _fake_response(root_payload),
            _fake_response(gguf_payload),
        ]
        files = client.get_model_files("org/model")

    assert len(files) == 1
    assert files[0].filename == "gguf/model-f16.gguf"
    assert files[0].quantization == "F16"
    assert files[0].size_bytes == 123456789


def _seed_hf_cache(db_path: Path, model_id: str, files_json: str, fetched_at: float) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hf_model_files_cache (
                model_id TEXT PRIMARY KEY,
                files_json TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                last_error TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO hf_model_files_cache (model_id, files_json, fetched_at, last_error)
            VALUES (?, ?, ?, NULL)
            """,
            (model_id, files_json, fetched_at),
        )
        conn.commit()
    finally:
        conn.close()


def test_get_model_files_uses_fresh_sqlite_cache(tmp_path):
    db_path = tmp_path / "app.db"
    _seed_hf_cache(
        db_path,
        "org/model",
        '[{"filename":"cached/model-q4.gguf","size_bytes":42,"quantization":"Q4_K_M"}]',
        time.time(),
    )
    client = HuggingFaceClient(cache_db_path=db_path)

    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        files = client.get_model_files("org/model")

    assert mock_get.called is False
    assert len(files) == 1
    assert files[0].filename == "cached/model-q4.gguf"
    assert files[0].size_bytes == 42
    assert files[0].quantization == "Q4_K_M"


def test_get_model_files_refreshes_stale_sqlite_cache(tmp_path):
    db_path = tmp_path / "app.db"
    _seed_hf_cache(
        db_path,
        "org/model",
        '[{"filename":"cached/model-q4.gguf","size_bytes":42,"quantization":"Q4_K_M"}]',
        time.time() - (60 * 60 * 48),
    )
    client = HuggingFaceClient(cache_db_path=db_path, cache_ttl_seconds=60)

    payload = [{"type": "file", "path": "fresh/model-f16.gguf", "size": 123456789}]
    with patch("app.lab.services.huggingface.requests.get") as mock_get:
        mock_get.return_value = _fake_response(payload)
        files = client.get_model_files("org/model")

    assert mock_get.called is True
    assert len(files) == 1
    assert files[0].filename == "fresh/model-f16.gguf"
    assert files[0].quantization == "F16"

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT files_json FROM hf_model_files_cache WHERE model_id = ?",
            ("org/model",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert "fresh/model-f16.gguf" in row[0]


def test_get_model_files_returns_stale_sqlite_cache_on_refresh_error(tmp_path):
    db_path = tmp_path / "app.db"
    _seed_hf_cache(
        db_path,
        "org/model",
        '[{"filename":"cached/model-q4.gguf","size_bytes":42,"quantization":"Q4_K_M"}]',
        time.time() - (60 * 60 * 48),
    )
    client = HuggingFaceClient(cache_db_path=db_path, cache_ttl_seconds=60)

    with patch("app.lab.services.huggingface.requests.get", side_effect=RuntimeError("boom")) as mock_get:
        files = client.get_model_files("org/model")

    assert mock_get.called is True
    assert len(files) == 1
    assert files[0].filename == "cached/model-q4.gguf"
    assert files[0].size_bytes == 42
