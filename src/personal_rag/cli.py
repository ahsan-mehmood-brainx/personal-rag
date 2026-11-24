"""Command-line interface: preview, ingest, search, reindex (and `ask` from Phase 3).

Pipeline position: a thin developer front end over the same services the API uses. Output
here is printed on purpose (this is a CLI); library modules log instead.
"""

import argparse
import sys
from pathlib import Path

from personal_rag.config import ConfigError, Settings, load_settings
from personal_rag.ingestion.service import IngestionService, build_chunks
from personal_rag.ingestion.validation import UploadError
from personal_rag.llm.client import UpstreamError, make_client
from personal_rag.llm.embeddings import OpenAIEmbedder
from personal_rag.store.vector_store import IndexMismatchError, VectorStore

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 400
DEFAULT_OVERLAP = 60
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _chunking_params() -> tuple[int, int, int, str]:
    """Chunking settings from `.env` if it is complete, otherwise the spec defaults.

    `preview` must work without an API key, so a settings failure is not fatal here.
    """
    try:
        s = load_settings()
    except ConfigError:
        print(
            "Note: settings are incomplete, so spec-default chunking (400/60) is used.",
            file=sys.stderr,
        )
        return DEFAULT_MAX_BYTES, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, DEFAULT_EMBEDDING_MODEL
    return s.max_upload_bytes, s.chunk_size_tokens, s.chunk_overlap_tokens, s.embedding_model


def cmd_preview(args: argparse.Namespace) -> int:
    """Print every chunk of a file with metadata. Makes no network calls."""
    path = Path(args.path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"Cannot read {path}: {exc.strerror}", file=sys.stderr)
        return 1

    max_bytes, size, overlap, model = _chunking_params()
    size = args.chunk_size if args.chunk_size is not None else size
    overlap = args.overlap if args.overlap is not None else overlap
    if size < 1 or overlap < 0 or overlap >= size:
        print("Chunk size must be positive and larger than the overlap.", file=sys.stderr)
        return 2
    try:
        upload, chunks = build_chunks(
            path.name,
            data,
            max_bytes=max_bytes,
            chunk_size=size,
            overlap=overlap,
            embedding_model=model,
        )
    except UploadError as exc:
        print(f"Rejected: {exc}", file=sys.stderr)
        return 1

    print(f"{upload.safe_name}  doc_id={upload.doc_id}  chunks={len(chunks)}")
    total = 0
    for chunk in chunks:
        total += chunk.token_count
        page = chunk.page if chunk.page is not None else "n/a"
        print("-" * 72)
        print(
            f"[{chunk.chunk_index}] id={chunk.chunk_id} section={chunk.section!r} "
            f"page={page} tokens={chunk.token_count}"
        )
        print(chunk.text)
    print("-" * 72)
    print(f"Total: {len(chunks)} chunks, {total} tokens (text only, without headers).")
    return 0


def _load_settings_or_exit() -> Settings | None:
    try:
        return load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return None


def _make_embedder(settings: Settings) -> OpenAIEmbedder:
    return OpenAIEmbedder(make_client(settings), settings.embedding_model)


def _make_service(settings: Settings, embedder: OpenAIEmbedder, store: VectorStore):
    return IngestionService(
        embedder=embedder,
        store=store,
        uploads_dir=settings.uploads_dir,
        max_bytes=settings.max_upload_bytes,
        chunk_size=settings.chunk_size_tokens,
        overlap=settings.chunk_overlap_tokens,
    )


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest files into the knowledge base under DATA_DIR. Calls the embeddings API."""
    settings = _load_settings_or_exit()
    if settings is None:
        return 1
    embedder = _make_embedder(settings)
    store = VectorStore(settings.chroma_dir, settings.embedding_model)
    service = _make_service(settings, embedder, store)
    exit_code = 0
    for raw in args.paths:
        path = Path(raw)
        try:
            if path.stat().st_size > settings.max_upload_bytes:
                print(f"{path.name}: larger than MAX_UPLOAD_MB", file=sys.stderr)
                exit_code = 1
                continue
            result = service.ingest(path.name, path.read_bytes())
        except OSError as exc:
            print(f"{path}: cannot read ({exc.strerror})", file=sys.stderr)
            exit_code = 1
        except (UploadError, IndexMismatchError, UpstreamError) as exc:
            print(f"{path.name}: {exc}", file=sys.stderr)
            exit_code = 1
        else:
            print(
                f"{result.filename}: {result.status}, {result.chunk_count} chunks, "
                f"~{result.embedded_tokens} tokens embedded"
            )
    print(f"Embedding API tokens reported: {embedder.tokens_used}")
    return exit_code


def cmd_search(args: argparse.Namespace) -> int:
    """Print the top-k chunks for a query with similarity scores. The threshold is not applied."""
    settings = _load_settings_or_exit()
    if settings is None:
        return 1
    store = VectorStore(settings.chroma_dir, settings.embedding_model)
    try:
        store.require_usable()
        if store.is_empty():
            print("The knowledge base is empty. Ingest documents first.", file=sys.stderr)
            return 1
        embedder = _make_embedder(settings)
        top_k = args.top_k if args.top_k is not None else settings.top_k
        hits = store.query(embedder.embed_query(args.query), top_k)
    except (IndexMismatchError, UpstreamError) as exc:
        print(exc, file=sys.stderr)
        return 1
    threshold = settings.similarity_threshold
    for rank, hit in enumerate(hits, start=1):
        marker = "keep" if hit.similarity >= threshold else "below threshold"
        page = hit.page if hit.page is not None else "n/a"
        print("-" * 72)
        print(
            f"#{rank} similarity={hit.similarity:.4f} ({marker})  {hit.filename} | "
            f"{hit.section} | page {page}"
        )
        print(hit.text[:300] + ("..." if len(hit.text) > 300 else ""))
    print("-" * 72)
    print(f"Threshold: {threshold}. Query tokens reported by API: {embedder.tokens_used}.")
    return 0


def cmd_reindex(_: argparse.Namespace) -> int:
    """Rebuild the whole index from stored originals using the configured embedding model."""
    settings = _load_settings_or_exit()
    if settings is None:
        return 1
    embedder = _make_embedder(settings)
    store = VectorStore(settings.chroma_dir, settings.embedding_model)
    service = _make_service(settings, embedder, store)
    try:
        result = service.reindex()
    except UpstreamError as exc:
        print(exc, file=sys.stderr)
        return 1
    if result.skipped_reset:
        print("No usable stored originals found; the existing index was left unchanged.")
        return 1 if result.failed else 0
    print(
        f"Reindexed {result.documents} document(s), {result.chunks} chunks, "
        f"~{result.embedded_tokens} tokens embedded."
    )
    for name in result.failed:
        print(f"Failed: {name}", file=sys.stderr)
    return 1 if result.failed else 0


def _top_k(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 50:
        raise argparse.ArgumentTypeError("must be between 1 and 50")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal_rag.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    preview = commands.add_parser("preview", help="Show the chunks a file produces (no OpenAI).")
    preview.add_argument("path", help="Path to a .pdf, .docx, .txt or .md file.")
    preview.add_argument("--chunk-size", type=int, default=None, help="Override CHUNK_SIZE_TOKENS.")
    preview.add_argument("--overlap", type=int, default=None, help="Override CHUNK_OVERLAP_TOKENS.")
    preview.set_defaults(func=cmd_preview)

    ingest = commands.add_parser("ingest", help="Embed files into the knowledge base (OpenAI).")
    ingest.add_argument("paths", nargs="+", help="One or more .pdf, .docx, .txt or .md files.")
    ingest.set_defaults(func=cmd_ingest)

    search = commands.add_parser("search", help="Show the top-k chunks and scores for a query.")
    search.add_argument("query")
    search.add_argument(
        "--top-k", type=_top_k, default=None, help="Override TOP_K (1 to 50)."
    )
    search.set_defaults(func=cmd_search)

    reindex = commands.add_parser("reindex", help="Re-embed all stored originals.")
    reindex.set_defaults(func=cmd_reindex)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
