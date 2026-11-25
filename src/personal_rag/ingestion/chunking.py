"""Section-aware chunking.

Pipeline position: after cleaning, before embedding. Chunks are what the vector store holds
and what the generator quotes, so their quality decides retrieval quality.

Rules (from the spec):
1. A chunk never spans two sections. The one exception is deliberate: a section under 50
   tokens is merged forward into the next section, keeping both headings.
2. Text is split on paragraph boundaries first. A paragraph that is too long is split on
   lines (CV bullets), then sentences, then, as a last resort, raw token windows.
3. Chunks hold up to `chunk_size` tokens; consecutive chunks of one section share up to
   `overlap` tokens, made of whole trailing pieces so the overlap never cuts a sentence.
4. Each chunk carries `text` (shown to people) and `embed_text` (contextual header + text,
   what actually gets embedded). The header helps short CV bullets match questions.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from personal_rag.ingestion.loaders import HEADING_SEPARATOR
from personal_rag.schemas import Chunk, Section

MIN_SECTION_TOKENS = 50
# text-embedding-3-* models use cl100k_base. Counting with it is exact for them and a close
# approximation for generation models, which is all chunk sizing needs.
ENCODING_NAME = "cl100k_base"
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


@dataclass(frozen=True)
class _Piece:
    """A unit of text that is never split further when packing, with the joiner before it."""

    text: str
    joiner: str
    tokens: int


def _hard_split(text: str, limit: int) -> list[str]:
    """Last resort for a single run of text with no separators: cut by token windows."""
    encoding = _encoding()
    tokens = encoding.encode(text)
    return [encoding.decode(tokens[i : i + limit]) for i in range(0, len(tokens), limit)]


def _split_block(text: str, limit: int, levels: list[tuple[str, str]]) -> list[_Piece]:
    """Recursively split `text` until every piece fits in `limit` tokens."""
    tokens = count_tokens(text)
    if tokens <= limit:
        return [_Piece(text, "", tokens)]
    if not levels:
        return [_Piece(part, "", count_tokens(part)) for part in _hard_split(text, limit)]

    joiner, pattern = levels[0]
    parts = [p for p in re.split(pattern, text) if p.strip()]
    if len(parts) <= 1:
        return _split_block(text, limit, levels[1:])
    pieces: list[_Piece] = []
    for index, part in enumerate(parts):
        for inner_index, piece in enumerate(_split_block(part.strip(), limit, levels[1:])):
            pieces.append(
                _Piece(piece.text, joiner if index and inner_index == 0 else piece.joiner,
                       piece.tokens)
            )
    return pieces


def _section_pieces(text: str, limit: int) -> list[_Piece]:
    """Paragraphs, falling back to lines, then sentences, then token windows."""
    levels = [("\n", r"\n"), (" ", _SENTENCE_RE.pattern)]
    pieces: list[_Piece] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for p_index, paragraph in enumerate(paragraphs):
        for i_index, piece in enumerate(_split_block(paragraph, limit, levels)):
            joiner = "\n\n" if p_index and i_index == 0 else piece.joiner
            pieces.append(_Piece(piece.text, joiner, piece.tokens))
    return pieces


def _join(pieces: list[_Piece]) -> str:
    out = ""
    for index, piece in enumerate(pieces):
        out += (piece.joiner if index else "") + piece.text
    return out


def _pack(pieces: list[_Piece], size: int, overlap: int) -> list[list[_Piece]]:
    """Greedily pack pieces into groups of at most `size` tokens, with trailing overlap."""
    groups: list[list[_Piece]] = []
    current: list[_Piece] = []
    for piece in pieces:
        candidate = count_tokens(_join([*current, piece])) if current else piece.tokens
        if current and candidate > size:
            groups.append(current)
            current = _overlap_tail(current, overlap)
            # If the tail plus the new piece would overflow, drop the tail rather than overflow.
            if current and count_tokens(_join([*current, piece])) > size:
                current = []
        current.append(piece)
    if current:
        groups.append(current)
    return groups


def _overlap_tail(group: list[_Piece], overlap: int) -> list[_Piece]:
    tail: list[_Piece] = []
    total = 0
    for piece in reversed(group[1:]):  # never carry the whole group; guarantees progress
        if total + piece.tokens > overlap:
            break
        tail.insert(0, piece)
        total += piece.tokens
    return tail


def _merge_headings(first: str | None, second: str | None) -> str | None:
    """Keep both headings, unless one is just the parent path of the other."""
    if not first or not second:
        return first or second
    if second.startswith(first + HEADING_SEPARATOR):
        return second  # "Jordan Avery" + "Jordan Avery > Summary"
    return f"{first} / {second}"


def merge_small_sections(sections: list[Section]) -> list[Section]:
    """Merge sections under MIN_SECTION_TOKENS into the next one, keeping both headings."""
    merged: list[Section] = []
    pending: Section | None = None
    for section in sections:
        if pending is not None:
            heading = _merge_headings(pending.heading, section.heading)
            section = Section(
                text=pending.text + "\n\n" + section.text,
                heading=heading,
                page=pending.page if pending.page is not None else section.page,
            )
            pending = None
        if count_tokens(section.text) < MIN_SECTION_TOKENS:
            pending = section
        else:
            merged.append(section)
    if pending is not None:
        merged.append(pending)  # a small final section has no next section; keep it alone
    return merged


def build_embed_text(filename: str, heading: str | None, text: str) -> str:
    return f"Document: {filename} | Section: {heading or 'General'}\n\n{text}"


def chunk_document(
    *,
    doc_id: str,
    filename: str,
    sections: list[Section],
    chunk_size: int,
    overlap: int,
    embedding_model: str,
    ingested_at: str,
) -> list[Chunk]:
    """Turn cleaned sections into chunks with full metadata."""
    chunks: list[Chunk] = []
    for section in merge_small_sections(sections):
        pieces = _section_pieces(section.text, chunk_size)
        for group in _pack(pieces, chunk_size, overlap):
            text = _join(group)
            index = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{index}",
                    doc_id=doc_id,
                    filename=filename,
                    section=section.heading or "General",
                    page=section.page,
                    chunk_index=index,
                    token_count=count_tokens(text),
                    ingested_at=ingested_at,
                    embedding_model=embedding_model,
                    text=text,
                    embed_text=build_embed_text(filename, section.heading, text),
                )
            )
    return chunks
