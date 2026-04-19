from app.config import ConfigStore
from app.models import AppConfig


def test_load_returns_default_when_missing(tmp_path):
    store = ConfigStore(tmp_path / "c.json")
    cfg = store.load()
    assert cfg.api_key == ""
    assert cfg.refresh_interval_seconds == 30


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "c.json"
    store = ConfigStore(path)
    original = AppConfig(
        api_key="abc123",
        default_tunnel_port=8080,
        start_requested_ids=[2, 1],
    )
    store.save(original)
    loaded = store.load()
    assert loaded.api_key == "abc123"
    assert loaded.default_tunnel_port == 8080
    assert loaded.start_requested_ids == [1, 2]


def test_load_corrupted_file_returns_default(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("{not valid json")
    store = ConfigStore(path)
    cfg = store.load()
    assert cfg.api_key == ""


def test_save_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "c.json"
    store = ConfigStore(path)
    store.save(AppConfig(api_key="x"))
    assert path.exists()


def test_load_ignores_unknown_fields(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"api_key": "k", "unknown_field": true}')
    store = ConfigStore(path)
    cfg = store.load()
    assert cfg.api_key == "k"


def test_start_requested_ids_are_coerced(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(
        '{"api_key": "k", "start_requested_ids": ["2", 1, "bad", 2]}',
        encoding="utf-8",
    )
    store = ConfigStore(path)
    cfg = store.load()
    assert cfg.api_key == "k"
    assert cfg.start_requested_ids == [1, 2]
