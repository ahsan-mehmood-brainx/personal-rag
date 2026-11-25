"""API integration tests: FastAPI TestClient with fake embedder/LLMs and a temp data dir.

Covers upload, duplicate, replace, list, ask, delete and every documented error code. No
network is used.
"""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from personal_rag.api.main import ApiContext, create_app
from personal_rag.ingestion.service import IngestionService
from personal_rag.llm.client import UpstreamError
from personal_rag.query.pipeline import QueryPipeline
from personal_rag.schemas import GroundedAnswer
from personal_rag.store.vector_store import VectorStore
from tests.fakes import FakeClassifier, FakeEmbedder, FakeGenerator
from tests.fixtures.make_fixtures import make_scanned_pdf
from tests.harness import MAX_BYTES, Harness


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    with TestClient(create_app(harness.context), raise_server_exceptions=False) as test_client:
        yield test_client


def upload(client: TestClient, name: str, data: bytes, content_type: str = "text/plain"):
    return client.post("/documents", files={"file": (name, data, content_type)})


def persona(persona_dir: Path, name: str) -> bytes:
    return (persona_dir / name).read_bytes()


QUESTION = "Where did I work as a software engineer on the forecasting pipeline Northwind?"


# --- health -------------------------------------------------------------------------------


def test_health_empty_then_populated(client: TestClient, persona_dir: Path) -> None:
    body = client.get("/health").json()
    assert body == {
        "status": "ok",
        "documents": 0,
        "chunks": 0,
        "embedding_model": "fake-embedding-model",
        "index_embedding_model": "fake-embedding-model",
        "index_usable": True,
    }
    upload(client, "cv.md", persona(persona_dir, "cv.md"))
    populated = client.get("/health").json()
    assert populated["documents"] == 1
    assert populated["chunks"] > 0


# --- upload / list / duplicate / replace / delete -------------------------------------------


def test_upload_each_persona_format_and_list(client: TestClient, persona_dir: Path) -> None:
    for name in ("cv.md", "projects.txt", "certifications.docx", "cv_onepage.pdf"):
        response = upload(client, name, persona(persona_dir, name))
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"doc_id", "filename", "status", "chunk_count"}
        assert body["status"] == "ingested"
        assert body["chunk_count"] > 0
    listed = client.get("/documents").json()
    assert {d["filename"] for d in listed} == {
        "cv.md",
        "projects.txt",
        "certifications.docx",
        "cv_onepage.pdf",
    }
    assert all({"doc_id", "filename", "chunk_count", "ingested_at"} <= set(d) for d in listed)


def test_duplicate_upload(client: TestClient, persona_dir: Path) -> None:
    first = upload(client, "cv.md", persona(persona_dir, "cv.md")).json()
    second = upload(client, "copy.md", persona(persona_dir, "cv.md")).json()
    assert second["status"] == "duplicate"
    assert second["doc_id"] == first["doc_id"]
    assert len(client.get("/documents").json()) == 1


def test_replace_upload(client: TestClient, persona_dir: Path) -> None:
    old = upload(client, "cv.md", persona(persona_dir, "cv.md")).json()
    edited = persona(persona_dir, "cv.md") + b"\n\n## More\nNew facts.\n"
    new = upload(client, "cv.md", edited).json()
    assert new["status"] == "replaced"
    assert new["doc_id"] != old["doc_id"]
    assert [d["doc_id"] for d in client.get("/documents").json()] == [new["doc_id"]]


def test_delete_document(client: TestClient, harness: Harness, persona_dir: Path) -> None:
    doc = upload(client, "cv.md", persona(persona_dir, "cv.md")).json()
    response = client.delete(f"/documents/{doc['doc_id']}")
    assert response.status_code == 200
    assert client.get("/documents").json() == []
    assert list((harness.tmp_path / "uploads").iterdir()) == []


@pytest.mark.parametrize("doc_id", ["0123456789abcdef", "nope", "..%2F..%2Fetc"])
def test_delete_unknown_document_is_404(client: TestClient, doc_id: str) -> None:
    assert client.delete(f"/documents/{doc_id}").status_code == 404


def test_path_traversal_filename_is_sanitized(
    client: TestClient, harness: Harness, persona_dir: Path
) -> None:
    response = upload(client, "../../evil name.md", persona(persona_dir, "cv.md"))
    assert response.status_code == 200
    assert response.json()["filename"] == "evil_name.md"
    stored = [p.name for p in (harness.tmp_path / "uploads").iterdir()]
    assert stored == [f"{response.json()['doc_id']}_evil_name.md"]


# --- ask ----------------------------------------------------------------------------------


def test_ask_answered_with_sources_and_debug(client: TestClient, persona_dir: Path) -> None:
    upload(client, "cv.md", persona(persona_dir, "cv.md"))
    response = client.post("/ask", json={"question": QUESTION, "debug": True})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["sources"][0]["label"] == "S1"
    assert body["sources"][0]["filename"] == "cv.md"
    assert body["debug"]["classifier_category"] == "personal"
    assert body["debug"]["retrieved"]


def test_ask_without_debug_has_null_debug(client: TestClient, persona_dir: Path) -> None:
    upload(client, "cv.md", persona(persona_dir, "cv.md"))
    assert client.post("/ask", json={"question": QUESTION}).json()["debug"] is None


def test_ask_no_documents(client: TestClient, harness: Harness) -> None:
    body = client.post("/ask", json={"question": QUESTION}).json()
    assert body["status"] == "no_documents"
    assert harness.classifier.calls == []


def test_ask_out_of_scope(client: TestClient, harness: Harness, persona_dir: Path) -> None:
    upload(client, "cv.md", persona(persona_dir, "cv.md"))
    harness.classifier.category = "out_of_scope"
    body = client.post("/ask", json={"question": "Capital of France?"}).json()
    assert body["status"] == "out_of_scope"
    assert body["sources"] == []


def test_ask_not_found_when_model_says_so(
    client: TestClient, harness: Harness, persona_dir: Path
) -> None:
    upload(client, "cv.md", persona(persona_dir, "cv.md"))
    harness.generator.answer = GroundedAnswer(
        status="not_found", answer="Probably 1990.", citations=[]
    )
    body = client.post("/ask", json={"question": QUESTION}).json()
    assert body["status"] == "not_found"
    assert "1990" not in body["answer"]


@pytest.mark.parametrize(
    "payload", [{"question": ""}, {"question": "   "}, {"question": "x" * 301}]
)
def test_ask_invalid_question_is_400(client: TestClient, payload: dict) -> None:
    assert client.post("/ask", json=payload).status_code == 400


@pytest.mark.parametrize("payload", [{}, {"question": 5}, {"debug": True}])
def test_ask_malformed_body_is_400_without_echoing_input(client: TestClient, payload: dict) -> None:
    response = client.post("/ask", json=payload)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request."}


def test_ask_upstream_failure_is_502_with_fixed_error_body(
    client: TestClient, harness: Harness, persona_dir: Path
) -> None:
    upload(client, "cv.md", persona(persona_dir, "cv.md"))
    harness.classifier.raises = UpstreamError("secret upstream detail")
    response = client.post("/ask", json={"question": QUESTION})
    assert response.status_code == 502
    assert response.json()["status"] == "error"
    assert "secret" not in response.text


# --- upload errors -------------------------------------------------------------------------


def test_upload_unsupported_type_is_415(client: TestClient) -> None:
    assert upload(client, "malware.exe", b"MZ").status_code == 415


def test_upload_too_large_is_413(client: TestClient) -> None:
    assert upload(client, "big.txt", b"a" * (MAX_BYTES + 1)).status_code == 413


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("fake.pdf", b"not a pdf"),
        ("fake.docx", b"not a zip"),
        ("bad.txt", "café".encode("latin-1")),
    ],
)
def test_upload_content_mismatch_is_422(client: TestClient, name: str, data: bytes) -> None:
    assert upload(client, name, data).status_code == 422


def test_upload_scanned_pdf_is_422_with_ocr_message(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    make_scanned_pdf(path)
    response = upload(client, "scan.pdf", path.read_bytes())
    assert response.status_code == 422
    assert "OCR" in response.json()["detail"]


def test_upload_without_file_field_is_400(client: TestClient) -> None:
    assert client.post("/documents").status_code == 400


def test_upload_upstream_failure_is_502_and_stores_nothing(
    client: TestClient, harness: Harness, persona_dir: Path
) -> None:
    def boom(texts: list[str]) -> list[list[float]]:
        raise UpstreamError("down")

    harness.embedder.embed_documents = boom  # type: ignore[method-assign]
    response = upload(client, "cv.md", persona(persona_dir, "cv.md"))
    assert response.status_code == 502
    assert client.get("/documents").json() == []


# --- index mismatch (503) ---------------------------------------------------------------------


def test_mismatched_index_returns_503_for_ask_and_upload(tmp_path: Path, persona_dir: Path) -> None:
    old = Harness(tmp_path)
    old.ingestion.ingest("cv.md", persona(persona_dir, "cv.md"))

    # Same data dir, but the app is now configured with a different embedding model.
    store = VectorStore(tmp_path / "chroma", "other-model")
    embedder = FakeEmbedder("other-model")
    ingestion = IngestionService(
        embedder=embedder,
        store=store,
        uploads_dir=tmp_path / "uploads",
        max_bytes=MAX_BYTES,
        chunk_size=400,
        overlap=60,
    )
    pipeline = QueryPipeline(
        classifier=FakeClassifier(),
        embedder=embedder,
        store=store,
        generator=FakeGenerator(),
        top_k=5,
        similarity_threshold=0.2,
        max_question_chars=300,
    )
    context = ApiContext(
        max_upload_bytes=MAX_BYTES,
        embedding_model="other-model",
        store=store,
        ingestion=ingestion,
        pipeline=pipeline,
        write_lock=threading.Lock(),
    )
    with TestClient(create_app(lambda: context)) as client:
        assert client.get("/health").json()["index_usable"] is False
        ask = client.post("/ask", json={"question": QUESTION})
        assert ask.status_code == 503
        assert "reindex" in ask.json()["detail"]
        blocked = upload(client, "projects.txt", persona(persona_dir, "projects.txt"))
        assert blocked.status_code == 503


# --- unexpected errors never leak ---------------------------------------------------------------


def test_unexpected_error_is_500_without_traceback(client: TestClient, harness: Harness) -> None:
    def boom() -> list:
        raise RuntimeError("secret internal path /Users/x/.env")

    harness.store.list_documents = boom  # type: ignore[method-assign]
    response = client.get("/documents")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}


def test_oversized_upload_is_rejected_before_ingestion(
    client: TestClient, harness: Harness
) -> None:
    response = upload(client, "huge.txt", b"a" * (MAX_BYTES + 200_000))
    assert response.status_code == 413
    assert harness.embedder.document_calls == []
