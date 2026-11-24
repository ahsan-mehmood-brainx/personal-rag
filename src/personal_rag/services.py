"""Wiring: build the real (OpenAI + Chroma) services from settings.

Pipeline position: the composition root. The CLI, the API and the eval harness all call
`build_services` so they assemble exactly the same objects. Tests skip this module and build
the pieces with fakes instead.
"""

from dataclasses import dataclass

from personal_rag.config import Settings
from personal_rag.ingestion.service import IngestionService
from personal_rag.llm.client import make_client
from personal_rag.llm.embeddings import OpenAIEmbedder
from personal_rag.query.generator import OpenAIAnswerGenerator, OpenAIGroundednessChecker
from personal_rag.query.pipeline import QueryPipeline
from personal_rag.query.scope_guard import OpenAIScopeClassifier
from personal_rag.store.vector_store import VectorStore


@dataclass
class Services:
    embedder: OpenAIEmbedder
    store: VectorStore
    ingestion: IngestionService
    pipeline: QueryPipeline


def build_services(settings: Settings) -> Services:
    client = make_client(settings)
    embedder = OpenAIEmbedder(client, settings.embedding_model)
    store = VectorStore(settings.chroma_dir, settings.embedding_model)
    ingestion = IngestionService(
        embedder=embedder,
        store=store,
        uploads_dir=settings.uploads_dir,
        max_bytes=settings.max_upload_bytes,
        chunk_size=settings.chunk_size_tokens,
        overlap=settings.chunk_overlap_tokens,
    )
    classifier = OpenAIScopeClassifier(
        client,
        model=settings.classifier_model,
        owner_name=settings.owner_name,
        temperature=settings.llm_temperature,
        reasoning_effort=settings.classifier_reasoning_effort,
    )
    generator = OpenAIAnswerGenerator(
        client,
        model=settings.generation_model,
        owner_name=settings.owner_name,
        temperature=settings.llm_temperature,
        reasoning_effort=settings.generation_reasoning_effort,
    )
    groundedness = (
        OpenAIGroundednessChecker(
            client,
            model=settings.generation_model,
            temperature=settings.llm_temperature,
            reasoning_effort=settings.generation_reasoning_effort,
        )
        if settings.enable_groundedness_check
        else None
    )
    pipeline = QueryPipeline(
        classifier=classifier,
        embedder=embedder,
        store=store,
        generator=generator,
        top_k=settings.top_k,
        similarity_threshold=settings.similarity_threshold,
        max_question_chars=settings.max_question_chars,
        groundedness_checker=groundedness,
    )
    return Services(embedder=embedder, store=store, ingestion=ingestion, pipeline=pipeline)
