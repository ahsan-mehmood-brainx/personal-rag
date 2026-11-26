"""FastAPI application: the HTTP face of the pipeline.

Pipeline position: a thin layer over the ingestion service and query pipeline. It validates
HTTP-level input, maps domain errors to status codes, and contains no business logic.

Status codes: 400 invalid input, 404 unknown document, 413 file too large, 415 unsupported
type, 422 unparseable or scanned document, 502 OpenAI upstream error, 503 index built with a
different embedding model. Bodies are `{"detail": ...}` and never include stack traces,
secrets or echoed input.

Dependencies (`get_context`) read from `app.state`, so tests build the app with fakes through
`create_app(context_factory=...)`. Run with:

    uv run uvicorn personal_rag.api.main:app --host 127.0.0.1 --port 8000
"""

import logging
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from personal_rag.config import load_settings
from personal_rag.ingestion.service import IngestionService
from personal_rag.ingestion.validation import UploadError
from personal_rag.llm.client import UpstreamError
from personal_rag.query.pipeline import InvalidQuestionError, QueryPipeline
from personal_rag.schemas import AskResponse, DocumentInfo
from personal_rag.services import build_services
from personal_rag.store.vector_store import IndexMismatchError, VectorStore

logger = logging.getLogger(__name__)

# Allowance for multipart boundaries and headers on top of the file bytes.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


@dataclass
class ApiContext:
    """Everything the endpoints need. Built once at startup (or by a test)."""

    max_upload_bytes: int
    embedding_model: str
    store: VectorStore
    ingestion: IngestionService
    pipeline: QueryPipeline
    # Serializes writes (ingest, delete) so concurrent requests cannot interleave on the index.
    write_lock: threading.Lock


def default_context() -> ApiContext:
    """Build the real context from `.env` and the environment. Fails fast on bad settings."""
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    services = build_services(settings)
    return ApiContext(
        max_upload_bytes=settings.max_upload_bytes,
        embedding_model=settings.embedding_model,
        store=services.store,
        ingestion=services.ingestion,
        pipeline=services.pipeline,
        write_lock=threading.Lock(),
    )


def get_context(request: Request) -> ApiContext:
    return request.app.state.context  # type: ignore[no-any-return]


def get_pipeline(ctx: Annotated[ApiContext, Depends(get_context)]) -> QueryPipeline:
    return ctx.pipeline


def get_ingestion(ctx: Annotated[ApiContext, Depends(get_context)]) -> IngestionService:
    return ctx.ingestion


def get_store(ctx: Annotated[ApiContext, Depends(get_context)]) -> VectorStore:
    return ctx.store


class AskRequest(BaseModel):
    question: str
    debug: bool = False
    # Opt-in: lets an out-of-scope question be answered by a web search instead of refused.
    allow_external_search: bool = False


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    status: str
    chunk_count: int


class HealthResponse(BaseModel):
    status: str
    documents: int
    chunks: int
    embedding_model: str
    index_embedding_model: str | None
    index_usable: bool


def _detail(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


def create_app(context_factory: Callable[[], ApiContext] = default_context) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.context = context_factory()
        yield

    app = FastAPI(title="Personal RAG Assistant", lifespan=lifespan)

    @app.middleware("http")
    async def _reject_oversized_upload(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Reject on the declared Content-Length before the multipart body is buffered. A client
        # that omits or understates it is still caught by the bounded read in the endpoint.
        if request.method == "POST" and request.url.path == "/documents":
            declared = request.headers.get("content-length", "")
            limit = request.app.state.context.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
            if declared.isdigit() and int(declared) > limit:
                return _detail(413, "File is larger than the upload limit.")
        return await call_next(request)

    # --- error mapping: every handler returns a fixed, value-free message ----------------

    @app.exception_handler(UploadError)
    async def _upload_error(_: Request, exc: UploadError) -> JSONResponse:
        return _detail(exc.status_code, str(exc))

    @app.exception_handler(InvalidQuestionError)
    async def _invalid_question(_: Request, exc: InvalidQuestionError) -> JSONResponse:
        return _detail(400, str(exc))

    @app.exception_handler(IndexMismatchError)
    async def _index_mismatch(_: Request, exc: IndexMismatchError) -> JSONResponse:
        return _detail(503, str(exc))

    @app.exception_handler(UpstreamError)
    async def _upstream(_: Request, __: UpstreamError) -> JSONResponse:
        return _detail(502, "The upstream language model service failed. Please try again.")

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # Default FastAPI text echoes the offending input; keep the body generic instead.
        return _detail(400, "Invalid request.")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error: %s", type(exc).__name__, exc_info=exc)
        return _detail(500, "Internal server error.")

    # --- endpoints ------------------------------------------------------------------------

    @app.get("/health")
    def health(ctx: Annotated[ApiContext, Depends(get_context)]) -> HealthResponse:
        return HealthResponse(
            status="ok",
            documents=len(ctx.store.list_documents()),
            chunks=ctx.store.chunk_count(),
            embedding_model=ctx.embedding_model,
            index_embedding_model=ctx.store.stored_embedding_model,
            index_usable=ctx.store.usable,
        )

    @app.post("/documents")
    def upload_document(
        ctx: Annotated[ApiContext, Depends(get_context)],
        file: Annotated[UploadFile | None, File()] = None,
    ) -> UploadResponse:
        if file is None:
            raise HTTPException(status_code=400, detail="Missing multipart field 'file'.")
        # Read one byte past the limit: enough to detect oversize without loading more.
        data = file.file.read(ctx.max_upload_bytes + 1)
        with ctx.write_lock:
            result = ctx.ingestion.ingest(file.filename or "upload", data)
        return UploadResponse(**result.model_dump(exclude={"embedded_tokens"}))

    @app.get("/documents")
    def list_documents(store: Annotated[VectorStore, Depends(get_store)]) -> list[DocumentInfo]:
        return store.list_documents()

    @app.delete("/documents/{doc_id}")
    def delete_document(
        doc_id: str, ctx: Annotated[ApiContext, Depends(get_context)]
    ) -> dict[str, str]:
        with ctx.write_lock:
            deleted = ctx.ingestion.delete(doc_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"deleted": doc_id}

    @app.post("/ask")
    def ask(
        body: AskRequest, pipeline: Annotated[QueryPipeline, Depends(get_pipeline)]
    ) -> JSONResponse:
        response: AskResponse = pipeline.ask(
            body.question, debug=body.debug, allow_external_search=body.allow_external_search
        )
        # An upstream failure is HTTP 502, but the body is still the fixed-message AskResponse
        # so clients can show it without special handling.
        code = 502 if response.status == "error" else 200
        return JSONResponse(status_code=code, content=response.model_dump(mode="json"))

    return app


app = create_app()
