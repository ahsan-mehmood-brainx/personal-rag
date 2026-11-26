"""External web search, used only when the caller allows it.

Pipeline position: an alternative to the out-of-scope refusal. When a request sets
`allow_external_search` and the scope gate classifies the question as `out_of_scope`, the
pipeline asks this searcher instead of refusing. Personal questions never come here: they still
go through retrieval and the grounded generator, so a personal fact is never looked up online.

The web model sees only the question, never document excerpts, so nothing from the personal
documents can leak into a web answer.
"""

import logging
from typing import Any, Protocol

from openai import OpenAI, OpenAIError

from personal_rag.llm.client import UpstreamError
from personal_rag.llm.prompts import WEB_SEARCH_SYSTEM
from personal_rag.schemas import TokenUsage, WebAnswer, WebSource

logger = logging.getLogger(__name__)

MAX_WEB_SOURCES = 8

# A tool-using web search runs much longer than the short structured calls the shared client's
# 30 s / 3-retry budget was sized for. Worst case here is 2 x 45 s, which keeps the whole
# request (scope call included) inside the web client's 120 s ask timeout.
WEB_SEARCH_TIMEOUT_SECONDS = 45.0
WEB_SEARCH_MAX_RETRIES = 1


class WebSearcher(Protocol):
    def search(self, question: str) -> tuple[WebAnswer, TokenUsage]: ...


class OpenAIWebSearcher:
    """Answers with the Responses API's built-in `web_search` tool."""

    def __init__(
        self,
        client: OpenAI,
        *,
        model: str,
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort

    def search(self, question: str) -> tuple[WebAnswer, TokenUsage]:
        options: dict[str, object] = {}
        if self._temperature is not None:
            options["temperature"] = self._temperature
        if self._reasoning_effort is not None:
            options["reasoning"] = {"effort": self._reasoning_effort}
        try:
            client = self._client.with_options(
                timeout=WEB_SEARCH_TIMEOUT_SECONDS, max_retries=WEB_SEARCH_MAX_RETRIES
            )
            response = client.responses.create(
                model=self._model,
                instructions=WEB_SEARCH_SYSTEM,
                input=question,
                tools=[{"type": "web_search"}],
                store=False,
                **options,  # type: ignore[arg-type]
            )
        except OpenAIError as exc:
            logger.error("web search request failed: %s", type(exc).__name__)
            raise UpstreamError("The web search request failed.") from None

        if response.status != "completed":
            # Truncated (for example by the content filter): fail closed, never show a partial.
            logger.error("web search did not complete (status=%s)", response.status)
            raise UpstreamError("The web search returned an incomplete answer.")
        text, sources = extract_answer(response)
        if not text:
            logger.error("web search returned no text (status=%s)", response.status)
            raise UpstreamError("The web search returned no answer.")

        usage = TokenUsage()
        if response.usage is not None:
            details = response.usage.output_tokens_details
            usage = TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                reasoning_tokens=details.reasoning_tokens if details else 0,
            )
        return WebAnswer(answer=text, sources=sources), usage


def extract_answer(response: Any) -> tuple[str, list[WebSource]]:
    """Join the output text, drop inline citation markup, and collect cited http(s) URLs."""
    parts: list[str] = []
    sources: list[WebSource] = []
    seen: set[str] = set()
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", None) or []:
            if getattr(content, "type", None) != "output_text":
                continue
            text: str = content.text or ""
            citations = [
                a for a in (content.annotations or []) if getattr(a, "type", None) == "url_citation"
            ]
            for annotation in citations:
                url = annotation.url
                if url.startswith(("https://", "http://")) and url not in seen:
                    seen.add(url)
                    sources.append(WebSource(title=annotation.title or url, url=url))
            parts.append(_strip_spans(text, [(a.start_index, a.end_index) for a in citations]))
    return "\n\n".join(p for p in parts if p).strip(), sources[:MAX_WEB_SOURCES]


def _strip_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Remove inline citation markup (for example `([site](url))`); sources are listed apart.

    Duplicate and overlapping spans are merged first, so every removal indexes the original
    text and never cuts into the answer itself."""
    merged: list[list[int]] = []
    for start, end in sorted(span for span in spans if 0 <= span[0] < span[1] <= len(text)):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in reversed(merged):
        text = text[:start].rstrip(" ") + text[end:]
    return text.strip()
