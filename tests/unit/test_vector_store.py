"""Vector store: cosine similarity, metadata round-trip, listing, deletion, model guard."""

from pathlib import Path

import pytest

from personal_rag.schemas import Chunk
from personal_rag.store.vector_store import IndexMismatchError, VectorStore
from tests.fakes import FakeEmbedder


def make_chunk(doc: str, index: int, text: str, page: int | None = None, name: str = "a.md"):
    return Chunk(
        chunk_id=f"{doc}:{index}", doc_id=doc, filename=name, section="Sec", page=page,
        chunk_index=index, token_count=5, ingested_at="2026-01-01T00:00:00+00:00",
        embedding_model="fake-embedding-model", text=text, embed_text=text,
    )


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    return VectorStore(tmp_path / "chroma", "fake-embedding-model")


def add(store: VectorStore, chunks: list[Chunk]) -> None:
    store.add_chunks(chunks, FakeEmbedder().embed_documents([c.embed_text for c in chunks]))


def test_empty_store(store: VectorStore) -> None:
    assert store.is_empty()
    assert store.query(FakeEmbedder().embed_query("anything"), 5) == []
    assert store.list_documents() == []


def test_query_ranks_by_cosine_similarity(store: VectorStore) -> None:
    add(store, [make_chunk("d1", 0, "python airflow pipeline"),
                make_chunk("d1", 1, "kubernetes deployment platform"),
                make_chunk("d2", 0, "hiking and trail running")])
    hits = store.query(FakeEmbedder().embed_query("python airflow pipeline"), 3)
    assert hits[0].chunk_id == "d1:0"
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-4)
    assert [h.similarity for h in hits] == sorted((h.similarity for h in hits), reverse=True)
    assert hits[-1].similarity < 0.2


def test_top_k_is_capped_by_collection_size(store: VectorStore) -> None:
    add(store, [make_chunk("d1", 0, "one"), make_chunk("d1", 1, "two")])
    assert len(store.query(FakeEmbedder().embed_query("one"), 50)) == 2


def test_page_none_round_trips_through_minus_one(store: VectorStore) -> None:
    add(store, [make_chunk("d1", 0, "with page", page=3), make_chunk("d1", 1, "no page")])
    by_id = {h.chunk_id: h for h in store.query(FakeEmbedder().embed_query("page"), 5)}
    assert by_id["d1:0"].page == 3
    assert by_id["d1:1"].page is None


def test_list_documents_counts_chunks(store: VectorStore) -> None:
    add(store, [make_chunk("d1", 0, "a"), make_chunk("d1", 1, "b"),
                make_chunk("d2", 0, "c", name="b.md")])
    docs = {d.doc_id: d for d in store.list_documents()}
    assert docs["d1"].chunk_count == 2
    assert docs["d2"].filename == "b.md"
    assert store.find_by_filename("b.md")[0].doc_id == "d2"
    assert store.get_document("nope") is None


def test_delete_document(store: VectorStore) -> None:
    add(store, [make_chunk("d1", 0, "a"), make_chunk("d2", 0, "b", name="b.md")])
    assert store.delete_document("d1") == 1
    assert store.delete_document("d1") == 0
    assert [d.doc_id for d in store.list_documents()] == ["d2"]


def test_persists_across_instances(tmp_path: Path) -> None:
    first = VectorStore(tmp_path / "c", "fake-embedding-model")
    add(first, [make_chunk("d1", 0, "persisted")])
    second = VectorStore(tmp_path / "c", "fake-embedding-model")
    assert second.chunk_count() == 1
    assert second.usable


def test_embedding_model_mismatch_blocks_use(tmp_path: Path) -> None:
    original = VectorStore(tmp_path / "c", "fake-embedding-model")
    add(original, [make_chunk("d1", 0, "text")])
    other = VectorStore(tmp_path / "c", "different-model")
    assert not other.usable
    with pytest.raises(IndexMismatchError, match="reindex"):
        other.require_usable()


def test_empty_index_adopts_new_model_silently(tmp_path: Path) -> None:
    VectorStore(tmp_path / "c", "old-model")
    assert VectorStore(tmp_path / "c", "new-model").usable


def test_reset_clears_and_adopts_configured_model(tmp_path: Path) -> None:
    original = VectorStore(tmp_path / "c", "fake-embedding-model")
    add(original, [make_chunk("d1", 0, "text")])
    other = VectorStore(tmp_path / "c", "different-model")
    other.reset()
    assert other.usable
    assert other.is_empty()


def test_add_chunks_splits_writes_larger_than_chroma_batch_limit(
    store: VectorStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store._client, "get_max_batch_size", lambda: 2)
    add(store, [make_chunk("d1", i, f"text {i}") for i in range(5)])
    assert store.chunk_count() == 5
