"""Query pipeline: orchestrates the gates for one question.

Pipeline position: the heart of the app. Every question ends in exactly one status:

    validate input -> no-documents check -> [gate 1] scope -> [gate 2] evidence ->
    generate -> [gate 3] citation validation -> (optional) groundedness check -> response

External search is opt-in per request (`allow_external_search`). It only changes what happens
to a question gate 1 classifies as out of scope: it is answered by a web search instead of the
fixed refusal. Personal questions take the same document-only path either way.

The system fails closed: any gate that cannot reach a valid decision (exception, timeout,
unparseable output) produces `error`, never an unguarded answer. Refusal text is fixed
(`messages.py`); the LLM never writes one.
"""

import logging
import time
from collections.abc import Callable
from datetime import date

from personal_rag import messages
from personal_rag.ingestion.chunking import count_tokens
from personal_rag.llm.client import UpstreamError
from personal_rag.llm.embeddings import Embedder
from personal_rag.query.generator import AnswerGenerator, GroundednessChecker
from personal_rag.query.retriever import RetrievalResult, retrieve
from personal_rag.query.scope_guard import ScopeClassifier
from personal_rag.query.validator import validate_answer
from personal_rag.query.web_search import WebSearcher
from personal_rag.schemas import (
    AskResponse,
    DebugChunk,
    DebugInfo,
    LabeledChunk,
    Source,
    Status,
    TokenUsage,
    WebSource,
)
from personal_rag.store.vector_store import VectorStore

logger = logging.getLogger(__name__)

EXCERPT_CHARS = 300


class InvalidQuestionError(ValueError):
    """The question is empty or too long. The API maps this to HTTP 400."""


class QueryPipeline:
    def __init__(
        self,
        *,
        classifier: ScopeClassifier,
        embedder: Embedder,
        store: VectorStore,
        generator: AnswerGenerator,
        top_k: int,
        similarity_threshold: float,
        max_question_chars: int,
        groundedness_checker: GroundednessChecker | None = None,
        web_searcher: WebSearcher | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._classifier = classifier
        self._embedder = embedder
        self._store = store
        self._generator = generator
        self._top_k = top_k
        self._threshold = similarity_threshold
        self._max_chars = max_question_chars
        self._groundedness = groundedness_checker
        self._web_searcher = web_searcher
        self._today = today

    # --- public API -------------------------------------------------------------------

    def ask(
        self, question: str, debug: bool = False, allow_external_search: bool = False
    ) -> AskResponse:
        """Answer one question. Raises InvalidQuestionError or IndexMismatchError for bad
        input or an unusable index; every other outcome is a response with a status.

        `allow_external_search` lets an out-of-scope question be answered by a web search.
        It has no effect when no web searcher is configured."""
        question = question.strip()
        if not question:
            raise InvalidQuestionError("The question is empty.")
        if len(question) > self._max_chars:
            raise InvalidQuestionError(f"The question is longer than {self._max_chars} characters.")
        logger.debug("question=%r", question)

        trace = _Trace(self._threshold)
        self._store.require_usable()
        if self._store.is_empty():
            return self._finish("no_documents", messages.NO_DOCUMENTS, trace, debug)

        try:
            return self._run(question, trace, debug, allow_external_search)
        except UpstreamError:
            return self._finish("error", messages.ERROR, trace, debug)
        except Exception:
            # Fail closed on anything unexpected, without leaking details to the caller.
            logger.exception("unexpected failure in query pipeline")
            return self._finish("error", messages.ERROR, trace, debug)

    # --- steps ------------------------------------------------------------------------

    def _run(
        self, question: str, trace: "_Trace", debug: bool, allow_external_search: bool
    ) -> AskResponse:
        # Gate 1: scope
        with trace.step("scope"):
            decision, usage = self._classifier.classify(question)
        trace.add_usage("scope", usage)
        trace.category, trace.reason = decision.category, decision.reason
        logger.info("step=scope category=%s ms=%.0f", decision.category, trace.ms["scope"])
        if decision.category == "out_of_scope":
            if allow_external_search and self._web_searcher is not None:
                return self._search_web(self._web_searcher, question, trace, debug)
            return self._finish("out_of_scope", messages.OUT_OF_SCOPE, trace, debug)
        if decision.category == "meta":
            count = len(self._store.list_documents())
            return self._finish("meta", messages.meta_message(count), trace, debug)

        # Gate 2: evidence
        with trace.step("retrieve"):
            retrieval = retrieve(
                question,
                embedder=self._embedder,
                store=self._store,
                top_k=self._top_k,
                threshold=self._threshold,
            )
        # Estimated with tiktoken: the shared embedder counter would mix in concurrent requests.
        trace.add_usage("embedding", TokenUsage(input_tokens=count_tokens(question)))
        trace.set_retrieval(retrieval)
        logger.info(
            "step=retrieve kept=%d top_score=%s ms=%.0f",
            len(retrieval.kept),
            f"{retrieval.top_score:.3f}" if retrieval.top_score is not None else "none",
            trace.ms["retrieve"],
        )
        if not retrieval.kept:
            return self._finish("not_found", messages.NOT_FOUND, trace, debug)

        # Step 3: grounded generation
        with trace.step("generate"):
            generated, usage = self._generator.generate(question, retrieval.kept, self._today())
        trace.add_usage("generate", usage)

        # Gate 3: validation in code
        with trace.step("validate"):
            validated = validate_answer(generated, {item.label for item in retrieval.kept})
        logger.info("step=validate status=%s citations=%d", validated.status, len(validated.labels))
        if validated.status == "not_found":
            return self._finish("not_found", messages.NOT_FOUND, trace, debug)

        cited = [item for item in retrieval.kept if item.label in validated.labels]
        if self._groundedness is not None:
            with trace.step("groundedness"):
                verdict, usage = self._groundedness.check(validated.text, cited)
            trace.add_usage("groundedness", usage)
            if not verdict.supported:
                logger.warning("groundedness check rejected the answer")
                return self._finish("not_found", messages.NOT_FOUND, trace, debug)

        return self._finish("answered", validated.text, trace, debug, sources=_sources(cited))

    def _search_web(
        self, searcher: WebSearcher, question: str, trace: "_Trace", debug: bool
    ) -> AskResponse:
        with trace.step("web_search"):
            result, usage = searcher.search(question)
        trace.add_usage("web_search", usage)
        logger.info(
            "step=web_search sources=%d ms=%.0f", len(result.sources), trace.ms["web_search"]
        )
        return self._finish("web_answered", result.answer, trace, debug, web_sources=result.sources)

    def _finish(
        self,
        status: Status,
        answer: str,
        trace: "_Trace",
        debug: bool,
        sources: list[Source] | None = None,
        web_sources: list[WebSource] | None = None,
    ) -> AskResponse:
        logger.info("result status=%s total_ms=%.0f", status, sum(trace.ms.values()))
        return AskResponse(
            status=status,
            answer=answer,
            sources=sources or [],
            web_sources=web_sources or [],
            debug=trace.to_debug() if debug else None,
        )


def _sources(cited: list[LabeledChunk]) -> list[Source]:
    return [
        Source(
            label=item.label,
            filename=item.chunk.filename,
            section=item.chunk.section,
            page=item.chunk.page,
            similarity=item.chunk.similarity,
            excerpt=item.chunk.text[:EXCERPT_CHARS],
        )
        for item in cited
    ]


class _Trace:
    """Collects what the debug view shows: decision, scores, latency and token usage."""

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self.category: str | None = None
        self.reason: str | None = None
        self.retrieved: list[DebugChunk] = []
        self.ms: dict[str, float] = {}
        self.usage: dict[str, TokenUsage] = {}

    def step(self, name: str) -> "_StepTimer":
        return _StepTimer(self, name)

    def add_usage(self, name: str, usage: TokenUsage) -> None:
        self.usage[name] = usage

    def set_retrieval(self, retrieval: RetrievalResult) -> None:
        self.retrieved = [
            DebugChunk(
                chunk_id=hit.chunk_id,
                filename=hit.filename,
                section=hit.section,
                page=hit.page,
                similarity=hit.similarity,
                kept=hit.similarity >= self.threshold,
            )
            for hit in retrieval.all_hits
        ]

    def to_debug(self) -> DebugInfo:
        return DebugInfo(
            classifier_category=self.category,
            classifier_reason=self.reason,
            retrieved=self.retrieved,
            threshold=self.threshold,
            latency_ms={name: round(value, 1) for name, value in self.ms.items()},
            token_usage=self.usage,
        )


class _StepTimer:
    def __init__(self, trace: _Trace, name: str) -> None:
        self._trace, self._name = trace, name
        self._start = 0.0

    def __enter__(self) -> None:
        self._start = time.perf_counter()

    def __exit__(self, *_: object) -> None:
        # Recorded even when the step raises, so a failed call still shows its latency.
        self._trace.ms[self._name] = (time.perf_counter() - self._start) * 1000
