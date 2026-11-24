"""Pipeline decisions with fakes: every status, every gate, and the fail-closed paths."""

from datetime import date
from pathlib import Path

import pytest

from personal_rag import messages
from personal_rag.llm.client import UpstreamError
from personal_rag.query.pipeline import InvalidQuestionError, QueryPipeline
from personal_rag.schemas import Chunk, GroundedAnswer
from personal_rag.store.vector_store import IndexMismatchError, VectorStore
from tests.fakes import FakeClassifier, FakeEmbedder, FakeGenerator, FakeGroundednessChecker

TODAY = date(2026, 6, 1)
CV_TEXT = "I worked at Northwind Analytics as a software engineer on the forecasting pipeline."
OTHER_TEXT = "Trail running and bouldering are my hobbies outside work."


def chunk(doc: str, index: int, text: str, name: str = "cv.md", page: int | None = None) -> Chunk:
    return Chunk(
        chunk_id=f"{doc}:{index}", doc_id=doc, filename=name, section="Experience", page=page,
        chunk_index=index, token_count=10, ingested_at="2026-01-01T00:00:00+00:00",
        embedding_model="fake-embedding-model", text=text, embed_text=text,
    )


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def store(tmp_path: Path, embedder: FakeEmbedder) -> VectorStore:
    store = VectorStore(tmp_path / "chroma", "fake-embedding-model")
    chunks = [chunk("d1", 0, CV_TEXT, page=2), chunk("d2", 0, OTHER_TEXT, name="pdf.pdf")]
    store.add_chunks(chunks, embedder.embed_documents([c.embed_text for c in chunks]))
    embedder.document_calls.clear()
    return store


def make(store, embedder, classifier=None, generator=None, threshold=0.2, **kwargs):
    classifier = classifier or FakeClassifier("personal")
    generator = generator or FakeGenerator()
    pipeline = QueryPipeline(
        classifier=classifier, embedder=embedder, store=store, generator=generator,
        top_k=5, similarity_threshold=threshold, max_question_chars=200, today=lambda: TODAY,
        **kwargs,
    )
    return pipeline, classifier, generator


QUESTION = "Where did I work as a software engineer on the forecasting pipeline?"


def test_answered_with_sources_only_for_cited_chunks(store, embedder) -> None:
    pipeline, _, generator = make(store, embedder)
    response = pipeline.ask(QUESTION)
    assert response.status == "answered"
    assert response.answer == "Fake answer."
    assert [s.label for s in response.sources] == ["S1"]
    source = response.sources[0]
    assert (source.filename, source.page) == ("cv.md", 2)
    assert source.excerpt == CV_TEXT[:300]
    assert generator.calls[0][2] == TODAY
    assert response.debug is None


def test_generator_never_sees_internal_chunk_ids(store, embedder) -> None:
    pipeline, _, generator = make(store, embedder)
    pipeline.ask(QUESTION)
    labels = [item.label for item in generator.calls[0][1]]
    assert labels[0] == "S1" and all(label.startswith("S") for label in labels)


def test_out_of_scope_skips_embedder_and_generator(store, embedder) -> None:
    pipeline, _, generator = make(store, embedder, classifier=FakeClassifier("out_of_scope"))
    response = pipeline.ask("What is the capital of France?")
    assert response.status == "out_of_scope"
    assert response.answer == messages.OUT_OF_SCOPE
    assert embedder.query_calls == []
    assert generator.calls == []


def test_meta_returns_help_with_document_count_and_no_retrieval(store, embedder) -> None:
    pipeline, _, generator = make(store, embedder, classifier=FakeClassifier("meta"))
    response = pipeline.ask("What can you do?")
    assert response.status == "meta"
    assert response.answer == messages.meta_message(2)
    assert "2 document(s)" in response.answer
    assert embedder.query_calls == []
    assert generator.calls == []


def test_all_scores_below_threshold_is_not_found_without_generator(store, embedder) -> None:
    pipeline, _, generator = make(store, embedder, threshold=0.99)
    response = pipeline.ask("completely unrelated zebra quantum words")
    assert response.status == "not_found"
    assert response.answer == messages.NOT_FOUND
    assert generator.calls == []


def test_answered_with_invalid_citations_becomes_not_found(store, embedder) -> None:
    bad = GroundedAnswer(status="answered", answer="Made up.", citations=["S9"])
    pipeline, _, _ = make(store, embedder, generator=FakeGenerator(bad))
    response = pipeline.ask(QUESTION)
    assert response.status == "not_found"
    assert response.answer == messages.NOT_FOUND
    assert response.sources == []


def test_answered_with_no_citations_becomes_not_found(store, embedder) -> None:
    bad = GroundedAnswer(status="answered", answer="Made up.", citations=[])
    pipeline, _, _ = make(store, embedder, generator=FakeGenerator(bad))
    assert pipeline.ask(QUESTION).status == "not_found"


def test_model_not_found_returns_fixed_message_and_discards_model_text(store, embedder) -> None:
    said = GroundedAnswer(status="not_found", answer="Probably 1990, I think.", citations=["S1"])
    pipeline, _, _ = make(store, embedder, generator=FakeGenerator(said))
    response = pipeline.ask(QUESTION)
    assert response.status == "not_found"
    assert response.answer == messages.NOT_FOUND
    assert "1990" not in response.answer


def test_classifier_error_is_error_and_generator_never_called(store, embedder) -> None:
    pipeline, _, generator = make(
        store, embedder, classifier=FakeClassifier(raises=UpstreamError("down"))
    )
    response = pipeline.ask(QUESTION)
    assert response.status == "error"
    assert response.answer == messages.ERROR
    assert generator.calls == []


def test_unexpected_classifier_exception_fails_closed(store, embedder) -> None:
    pipeline, _, generator = make(
        store, embedder, classifier=FakeClassifier(raises=RuntimeError("boom"))
    )
    response = pipeline.ask(QUESTION)
    assert response.status == "error"
    assert "boom" not in response.answer
    assert generator.calls == []


def test_generator_error_is_error_not_a_fallback_answer(store, embedder) -> None:
    pipeline, _, _ = make(store, embedder, generator=FakeGenerator(raises=UpstreamError("x")))
    response = pipeline.ask(QUESTION)
    assert response.status == "error"
    assert response.sources == []


def test_embedder_error_is_error(store, embedder) -> None:
    def boom(text: str) -> list[float]:
        raise UpstreamError("embedding down")

    embedder.embed_query = boom  # type: ignore[method-assign]
    pipeline, _, generator = make(store, embedder)
    assert pipeline.ask(QUESTION).status == "error"
    assert generator.calls == []


def test_empty_knowledge_base_returns_no_documents_without_any_openai_call(
    tmp_path, embedder
) -> None:
    empty = VectorStore(tmp_path / "empty", "fake-embedding-model")
    pipeline, classifier, generator = make(empty, embedder)
    response = pipeline.ask(QUESTION)
    assert response.status == "no_documents"
    assert response.answer == messages.NO_DOCUMENTS
    assert classifier.calls == [] and generator.calls == [] and embedder.query_calls == []


@pytest.mark.parametrize("question", ["", "   \n\t ", "x" * 201])
def test_invalid_questions_are_rejected_before_any_call(store, embedder, question) -> None:
    pipeline, classifier, _ = make(store, embedder)
    with pytest.raises(InvalidQuestionError):
        pipeline.ask(question)
    assert classifier.calls == []


def test_question_is_stripped(store, embedder) -> None:
    pipeline, classifier, _ = make(store, embedder)
    pipeline.ask("   " + QUESTION + "  \n")
    assert classifier.calls == [QUESTION]


def test_mismatched_index_refuses_to_answer(tmp_path, embedder) -> None:
    store = VectorStore(tmp_path / "c", "old-model")
    store.add_chunks([chunk("d1", 0, CV_TEXT)], embedder.embed_documents([CV_TEXT]))
    mismatched = VectorStore(tmp_path / "c", "fake-embedding-model")
    pipeline, classifier, _ = make(mismatched, embedder)
    with pytest.raises(IndexMismatchError):
        pipeline.ask(QUESTION)
    assert classifier.calls == []


def test_debug_info_includes_all_hits_scores_latency_and_tokens(store, embedder) -> None:
    pipeline, _, _ = make(store, embedder, threshold=0.5)
    response = pipeline.ask(QUESTION, debug=True)
    debug = response.debug
    assert debug is not None
    assert debug.classifier_category == "personal"
    assert debug.classifier_reason == "fake reason"
    assert debug.threshold == 0.5
    assert len(debug.retrieved) == 2, "below-threshold chunks must be listed too"
    assert [h.kept for h in debug.retrieved] == [True, False]
    assert set(debug.latency_ms) >= {"scope", "retrieve", "generate", "validate"}
    assert debug.token_usage["scope"].input_tokens == 10
    assert debug.token_usage["generate"].reasoning_tokens == 2


def test_debug_is_available_on_refusals(store, embedder) -> None:
    pipeline, _, _ = make(store, embedder, classifier=FakeClassifier("out_of_scope"))
    debug = pipeline.ask("capital of France?", debug=True).debug
    assert debug is not None
    assert debug.classifier_category == "out_of_scope"
    assert debug.retrieved == []


def test_groundedness_check_off_by_default(store, embedder) -> None:
    checker = FakeGroundednessChecker(supported=False)
    pipeline, _, _ = make(store, embedder)  # checker not injected
    assert pipeline.ask(QUESTION).status == "answered"
    assert checker.calls == 0


def test_unsupported_groundedness_verdict_becomes_not_found(store, embedder) -> None:
    pipeline, _, _ = make(store, embedder, groundedness_checker=FakeGroundednessChecker(False))
    response = pipeline.ask(QUESTION)
    assert response.status == "not_found"
    assert response.sources == []


def test_supported_groundedness_verdict_keeps_answer(store, embedder) -> None:
    checker = FakeGroundednessChecker(True)
    pipeline, _, _ = make(store, embedder, groundedness_checker=checker)
    assert pipeline.ask(QUESTION).status == "answered"
    assert checker.calls == 1


def test_groundedness_failure_fails_closed(store, embedder) -> None:
    checker = FakeGroundednessChecker(raises=UpstreamError("down"))
    pipeline, _, _ = make(store, embedder, groundedness_checker=checker)
    assert pipeline.ask(QUESTION).status == "error"
