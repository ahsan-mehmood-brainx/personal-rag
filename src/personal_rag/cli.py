"""Command-line interface. Phase 1 provides `preview`; later phases add more commands.

Pipeline position: a thin developer front end over the same services the API uses. Output
here is printed on purpose (this is a CLI); library modules log instead.
"""

import argparse
import sys
from pathlib import Path

from personal_rag.config import ConfigError, load_settings
from personal_rag.ingestion.service import build_chunks
from personal_rag.ingestion.validation import UploadError

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal_rag.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    preview = commands.add_parser("preview", help="Show the chunks a file produces (no OpenAI).")
    preview.add_argument("path", help="Path to a .pdf, .docx, .txt or .md file.")
    preview.add_argument("--chunk-size", type=int, default=None, help="Override CHUNK_SIZE_TOKENS.")
    preview.add_argument("--overlap", type=int, default=None, help="Override CHUNK_OVERLAP_TOKENS.")
    preview.set_defaults(func=cmd_preview)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
