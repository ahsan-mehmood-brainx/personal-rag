"""Ingestion service with a fake embedder: ingest, duplicate, replace, delete, reindex."""

from pathlib import Path

import pytest

from personal_rag.ingestion.service import EmptyDocumentError, IngestionService
from personal_rag.ingestion.validation import UnsupportedFileTypeError
from personal_rag.store.vector_store import IndexMismatchError, VectorStore
from tests.fakes import FakeEmbedder


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    return VectorStore(tmp_path / "chroma", "fake-embedding-model")


@pytest.fixture
def service(tmp_path: Path, embedder: FakeEmbedder, store: VectorStore) -> IngestionService:
    return IngestionService(
        embedder=embedder, store=store, uploads_dir=tmp_path / "uploads",
        max_bytes=1024 * 1024, chunk_size=400, overlap=60,
    )


def persona(persona_dir: Path, name: str) -> bytes:
    return (persona_dir / name).read_bytes()


def test_ingest_stores_chunks_and_original(
    service: IngestionService, store: VectorStore, persona_dir: Path, tmp_path: Path
) -> None:
    result = service.ingest("cv.md", persona(persona_dir, "cv.md"))
    assert result.status == "ingested"
    assert result.chunk_count == store.chunk_count() > 0
    assert result.embedded_tokens > 0
    assert (tmp_path / "uploads" / f"{result.doc_id}_cv.md").exists()


def test_embeds_the_contextual_header_text(
    service: IngestionService, embedder: FakeEmbedder, persona_dir: Path
) -> None:
    service.ingest("cv.md", persona(persona_dir, "cv.md"))
    assert all(t.startswith("Document: cv.md | Section: ") for t in embedder.document_calls[0])


def test_identical_content_is_a_duplicate_and_changes_nothing(
    service: IngestionService, embedder: FakeEmbedder, store: VectorStore, persona_dir: Path
) -> None:
    first = service.ingest("cv.md", persona(persona_dir, "cv.md"))
    count = store.chunk_count()
    calls = len(embedder.document_calls)
    second = service.ingest("renamed.md", persona(persona_dir, "cv.md"))
    assert second.status == "duplicate"
    assert second.doc_id == first.doc_id
    assert second.chunk_count == first.chunk_count
    assert store.chunk_count() == count
    assert len(embedder.document_calls) == calls  # no re-embedding


def test_same_filename_new_content_replaces_old_version(
    service: IngestionService, store: VectorStore, persona_dir: Path, tmp_path: Path
) -> None:
    old = service.ingest("cv.md", persona(persona_dir, "cv.md"))
    new = service.ingest("cv.md", persona(persona_dir, "cv.md") + b"\n\n## Extra\nNew fact here.\n")
    assert new.status == "replaced"
    assert new.doc_id != old.doc_id
    docs = store.list_documents()
    assert [d.doc_id for d in docs] == [new.doc_id]
    uploads = [p.name for p in (tmp_path / "uploads").iterdir()]
    assert uploads == [f"{new.doc_id}_cv.md"]


def test_failed_embedding_keeps_old_version(
    service: IngestionService, embedder: FakeEmbedder, store: VectorStore, persona_dir: Path
) -> None:
    old = service.ingest("cv.md", persona(persona_dir, "cv.md"))

    def boom(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("upstream down")

    embedder.embed_documents = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        service.ingest("cv.md", persona(persona_dir, "cv.md") + b"\n\nmore text\n")
    assert [d.doc_id for d in store.list_documents()] == [old.doc_id]


def test_delete_removes_chunks_and_file(
    service: IngestionService, store: VectorStore, persona_dir: Path, tmp_path: Path
) -> None:
    result = service.ingest("cv.md", persona(persona_dir, "cv.md"))
    assert service.delete(result.doc_id) is True
    assert store.is_empty()
    assert list((tmp_path / "uploads").iterdir()) == []
    assert service.delete(result.doc_id) is False


@pytest.mark.parametrize("bad_id", ["../../etc", "*", "", "ZZZZ", "abc"])
def test_delete_rejects_malformed_ids(service: IngestionService, bad_id: str) -> None:
    assert service.delete(bad_id) is False


def test_ingest_all_persona_formats(service: IngestionService, persona_dir: Path) -> None:
    for name in ("cv.md", "projects.txt", "certifications.docx", "cv_onepage.pdf"):
        assert service.ingest(name, persona(persona_dir, name)).status == "ingested"


def test_empty_document_is_rejected(service: IngestionService) -> None:
    with pytest.raises(EmptyDocumentError):
        service.ingest("blank.txt", b"   \n\n  ")


def test_unsupported_type_is_rejected(service: IngestionService) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        service.ingest("x.exe", b"MZ")


def test_ingest_refused_when_index_built_with_other_model(
    tmp_path: Path, persona_dir: Path
) -> None:
    VectorStore(tmp_path / "chroma", "old-model").add_chunks([], [])
    seed = IngestionService(
        embedder=FakeEmbedder("old-model"), store=VectorStore(tmp_path / "chroma", "old-model"),
        uploads_dir=tmp_path / "uploads", max_bytes=10**6, chunk_size=400, overlap=60,
    )
    seed.ingest("cv.md", persona(persona_dir, "cv.md"))
    mismatched = IngestionService(
        embedder=FakeEmbedder("new-model"), store=VectorStore(tmp_path / "chroma", "new-model"),
        uploads_dir=tmp_path / "uploads", max_bytes=10**6, chunk_size=400, overlap=60,
    )
    with pytest.raises(IndexMismatchError):
        mismatched.ingest("projects.txt", persona(persona_dir, "projects.txt"))


def test_reindex_rebuilds_with_new_model(tmp_path: Path, persona_dir: Path) -> None:
    uploads = tmp_path / "uploads"
    old_store = VectorStore(tmp_path / "chroma", "old-model")
    old = IngestionService(
        embedder=FakeEmbedder("old-model"), store=old_store, uploads_dir=uploads,
        max_bytes=10**6, chunk_size=400, overlap=60,
    )
    for name in ("cv.md", "projects.txt"):
        old.ingest(name, persona(persona_dir, name))
    chunks_before = old_store.chunk_count()

    new_embedder = FakeEmbedder("new-model")
    new_store = VectorStore(tmp_path / "chroma", "new-model")
    assert not new_store.usable
    new = IngestionService(
        embedder=new_embedder, store=new_store, uploads_dir=uploads,
        max_bytes=10**6, chunk_size=400, overlap=60,
    )
    result = new.reindex()
    assert result.documents == 2
    assert result.chunks == chunks_before
    assert result.failed == []
    assert new_store.usable
    assert {d.filename for d in new_store.list_documents()} == {"cv.md", "projects.txt"}
    assert new_embedder.document_calls, "reindex must re-embed"


def test_reindex_with_no_originals_keeps_existing_index(
    service: IngestionService, store: VectorStore, persona_dir: Path, tmp_path: Path
) -> None:
    service.ingest("cv.md", persona(persona_dir, "cv.md"))
    for stored in (tmp_path / "uploads").iterdir():
        stored.unlink()
    before = store.chunk_count()
    result = service.reindex()
    assert result.skipped_reset is True
    assert store.chunk_count() == before


def test_reindex_embedding_failure_leaves_index_untouched(
    service: IngestionService, embedder: FakeEmbedder, store: VectorStore, persona_dir: Path
) -> None:
    service.ingest("cv.md", persona(persona_dir, "cv.md"))
    before = store.chunk_count()

    def boom(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("upstream down")

    embedder.embed_documents = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        service.reindex()
    assert store.chunk_count() == before
