"""Fake-backed API server for the frontend's end-to-end tests.

Runs the real FastAPI app (`personal_rag.api.main.create_app`) with the backend's own test
harness: real validation, parsing, chunking and ChromaDB, but a deterministic fake embedder,
classifier and generator, and a throwaway data directory. No OpenAI calls, no API key, and
the real `data/` index is never opened.

Test-only routing in the fake classifier (so e2e tests can reach every status):
    "hello" / "what can you do"   -> meta
    starts with "what is", "explain", "search the web", "latest" -> out_of_scope
    out_of_scope with allow_external_search -> fake web answer citing https://example.com/
    contains "trigger upstream error" -> classifier raises UpstreamError (HTTP 502, status error)
    anything else                 -> personal

Run from the repository root:
    uv run python web/e2e/fake_api_server.py --port 8765
"""

import argparse
import sys
import tempfile
import threading
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import uvicorn  # noqa: E402
from tests.fakes import FAKE_USAGE, FakeEmbedder  # noqa: E402

from personal_rag.api.main import ApiContext, create_app  # noqa: E402
from personal_rag.ingestion.service import IngestionService  # noqa: E402
from personal_rag.llm.client import UpstreamError  # noqa: E402
from personal_rag.query.pipeline import QueryPipeline  # noqa: E402
from personal_rag.schemas import (  # noqa: E402
    GroundedAnswer,
    LabeledChunk,
    ScopeDecision,
    TokenUsage,
    WebAnswer,
    WebSource,
)
from personal_rag.store.vector_store import VectorStore  # noqa: E402

# Same defaults as the real app (MAX_UPLOAD_MB=10, MAX_QUESTION_CHARS=1000).
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_QUESTION_CHARS = 1000

OUT_OF_SCOPE_PREFIXES = ("what is", "explain", "search the web", "latest")


class RoutingClassifier:
    def classify(self, question: str) -> tuple[ScopeDecision, TokenUsage]:
        text = question.strip().lower()
        if "trigger upstream error" in text:
            raise UpstreamError("simulated upstream failure")
        if text.startswith(("hello", "hi ")) or "what can you do" in text:
            return ScopeDecision(category="meta", reason="greeting"), FAKE_USAGE
        if text.startswith(OUT_OF_SCOPE_PREFIXES):
            return ScopeDecision(category="out_of_scope", reason="general knowledge"), FAKE_USAGE
        return ScopeDecision(category="personal", reason="about the owner"), FAKE_USAGE


class ExcerptGenerator:
    """Answers with the first line of the top excerpt, cited, so answers depend on uploads."""

    def generate(
        self, question: str, excerpts: list[LabeledChunk], today: date
    ) -> tuple[GroundedAnswer, TokenUsage]:
        top = excerpts[0]
        first_line = next((ln.strip() for ln in top.chunk.text.splitlines() if ln.strip()), "")
        answer = (
            f"From your documents ({top.chunk.filename}):\n\n"
            f"- {first_line[:160]}\n- Section: {top.chunk.section}"
        )
        return GroundedAnswer(status="answered", answer=answer, citations=[top.label]), FAKE_USAGE


class EchoWebSearcher:
    """Stands in for the real web search: no network, one fixed source."""

    def search(self, question: str) -> tuple[WebAnswer, TokenUsage]:
        answer = f'From the web: a general answer to "{question.strip()[:80]}".'
        source = WebSource(title="Example source", url="https://example.com/")
        return WebAnswer(answer=answer, sources=[source]), FAKE_USAGE


def build_context(data_dir: Path) -> ApiContext:
    embedder = FakeEmbedder()
    store = VectorStore(data_dir / "chroma", embedder.model)
    ingestion = IngestionService(
        embedder=embedder,
        store=store,
        uploads_dir=data_dir / "uploads",
        max_bytes=MAX_UPLOAD_BYTES,
        chunk_size=400,
        overlap=60,
    )
    pipeline = QueryPipeline(
        classifier=RoutingClassifier(),
        embedder=embedder,
        store=store,
        generator=ExcerptGenerator(),
        web_searcher=EchoWebSearcher(),
        top_k=5,
        similarity_threshold=0.05,
        max_question_chars=MAX_QUESTION_CHARS,
    )
    return ApiContext(
        max_upload_bytes=MAX_UPLOAD_BYTES,
        embedding_model=embedder.model,
        store=store,
        ingestion=ingestion,
        pipeline=pipeline,
        write_lock=threading.Lock(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="prag-e2e-") as tmp:
        app = create_app(context_factory=lambda: build_context(Path(tmp)))
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
