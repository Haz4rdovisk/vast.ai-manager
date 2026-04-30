"""Worker for fetching Hugging Face models asynchronously."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.lab.services.huggingface import HuggingFaceClient


class HFSearchWorker(QThread):
    finished = Signal(list, object) # list[HFModel], str | None
    error = Signal(str)

    def __init__(
        self,
        query: str = "",
        limit: int = 100,
        pipeline_tag: str | None = None,
        cursor: str | None = None,
        sort_by: str = "downloads",
        parent=None,
    ):
        super().__init__(parent)
        self.query = query
        self.limit = limit
        self.pipeline_tag = pipeline_tag
        self.cursor = cursor
        self.sort_by = sort_by
        self.client = HuggingFaceClient()

    def run(self):
        try:
            models, next_cursor = self.client.search_gguf_models(
                query=self.query,
                limit=self.limit,
                pipeline_tag=self.pipeline_tag,
                cursor=self.cursor,
                sort_by=self.sort_by,
            )
            self.finished.emit(models, next_cursor)
        except Exception as e:
            self.error.emit(str(e))


class HFModelDetailWorker(QThread):
    finished = Signal(list) # list[HFModelFile]
    error = Signal(str)

    def __init__(self, model_id: str, parent=None):
        super().__init__(parent)
        self.model_id = model_id
        self.client = HuggingFaceClient()

    def run(self):
        try:
            files = self.client.get_model_files(self.model_id)
            self.finished.emit(files)
        except Exception as e:
            self.error.emit(str(e))
