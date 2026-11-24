"""Text cleaning applied to every section before chunking.

Pipeline position: between loaders and chunker. Loaders return text as the file stores it
(odd bullets, line-wrapped hyphenation, stray control characters). Cleaning makes that text
uniform so chunk sizes and embeddings are not distorted by formatting noise.
"""

import re
import unicodedata

from personal_rag.schemas import Section

# Characters that PDFs and word processors use as list markers.
_BULLET_RE = re.compile(r"^[ \t]*[•●▪■◦‣∙·–—*][ \t]+", re.MULTILINE)
# "devel-\nopment" -> "development". Only joins when the next word starts lowercase, so a
# deliberate hyphen before a proper noun ("Python-\nBased" is rare, "Berlin-\nBased") survives.
_HYPHEN_BREAK_RE = re.compile(r"(\w)-[ \t]*\n[ \t]*(?=[a-z])")


def clean_text(text: str) -> str:
    """Normalize one block of text. Idempotent."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text)
    # Drop control (Cc) and invisible formatting (Cf: zero-width space, soft hyphen, BOM)
    # characters, but keep newlines. Tabs become spaces.
    text = text.replace("\t", " ")
    text = "".join(
        ch for ch in text if ch == "\n" or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    text = _HYPHEN_BREAK_RE.sub(r"\1", text)
    text = _BULLET_RE.sub("- ", text)
    text = re.sub(r" {2,}", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_sections(sections: list[Section]) -> list[Section]:
    """Clean every section and drop the ones left empty."""
    cleaned: list[Section] = []
    for section in sections:
        text = clean_text(section.text)
        if not text:
            continue
        heading = clean_text(section.heading) if section.heading else None
        cleaned.append(Section(text=text, heading=heading or None, page=section.page))
    return cleaned
