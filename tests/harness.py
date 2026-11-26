"""Test harness: a fully fake-backed API context (fake embedder and LLMs, temp data dir)."""

import threading
from datetime import date
from pathlib import Path

from personal_rag.api.main import ApiContext
from personal_rag.ingestion.service import IngestionService
from personal_rag.query.pipeline import QueryPipeline
from personal_rag.store.vector_store import VectorStore
from tests.fakes import FakeClassifier, FakeEmbedder, FakeGenerator, FakeWebSearcher

MAX_BYTES = 200_000


class Harness:
    """Holds the fakes so tests can tweak them after the app is built."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.embedder = FakeEmbedder()
        self.classifier = FakeClassifier("personal")
        self.generator = FakeGenerator()
        self.web_searcher = FakeWebSearcher()
        self.store = VectorStore(tmp_path / "chroma", "fake-embedding-model")
        self.ingestion = IngestionService(
            embedder=self.embedder,
            store=self.store,
            uploads_dir=tmp_path / "uploads",
            max_bytes=MAX_BYTES,
            chunk_size=400,
            overlap=60,
        )
        self.pipeline = QueryPipeline(
            classifier=self.classifier,
            embedder=self.embedder,
            store=self.store,
            generator=self.generator,
            web_searcher=self.web_searcher,
            top_k=5,
            similarity_threshold=0.2,
            max_question_chars=300,
            today=lambda: date(2026, 6, 1),
        )

    def context(self) -> ApiContext:
        return ApiContext(
            max_upload_bytes=MAX_BYTES,
            embedding_model="fake-embedding-model",
            store=self.store,
            ingestion=self.ingestion,
            pipeline=self.pipeline,
            write_lock=threading.Lock(),
        )
