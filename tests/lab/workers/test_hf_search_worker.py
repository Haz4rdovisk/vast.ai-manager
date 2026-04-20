from unittest.mock import patch

from PySide6.QtTest import QSignalSpy

from app.lab.workers.huggingface_worker import HFSearchWorker


def test_worker_forwards_pipeline_tag_and_cursor(qt_app):
    with patch("app.lab.workers.huggingface_worker.HuggingFaceClient") as mock_client:
        instance = mock_client.return_value
        instance.search_gguf_models.return_value = ([], "NEXTCURSOR")
        worker = HFSearchWorker(
            query="qwen",
            limit=100,
            pipeline_tag="text-generation",
            cursor="PREV",
        )
        spy = QSignalSpy(worker.finished)
        worker.run()
        instance.search_gguf_models.assert_called_once_with(
            query="qwen",
            limit=100,
            pipeline_tag="text-generation",
            cursor="PREV",
        )
        assert spy.count() == 1
        assert spy.at(0)[0] == []
        assert spy.at(0)[1] == "NEXTCURSOR"
