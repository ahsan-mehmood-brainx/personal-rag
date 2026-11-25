"""Gate 1: scope classification.

Pipeline position: the first thing every question meets. A single LLM call decides whether the
question is about the owner (`personal`), a greeting or help request (`meta`), or anything else
(`out_of_scope`). Out-of-scope questions stop here: no retrieval, no generation, so a
refusal can never leak document content.
"""

from typing import Protocol

from openai import OpenAI

from personal_rag.llm.prompts import scope_classifier_instructions
from personal_rag.llm.structured import parse_structured
from personal_rag.schemas import ScopeDecision, TokenUsage


class ScopeClassifier(Protocol):
    def classify(self, question: str) -> tuple[ScopeDecision, TokenUsage]: ...


class OpenAIScopeClassifier:
    def __init__(
        self,
        client: OpenAI,
        *,
        model: str,
        owner_name: str,
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> None:
        self._client = client
        self._model = model
        self._instructions = scope_classifier_instructions(owner_name)
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort

    def classify(self, question: str) -> tuple[ScopeDecision, TokenUsage]:
        return parse_structured(
            self._client,
            model=self._model,
            instructions=self._instructions,
            user_input=question,
            schema=ScopeDecision,
            temperature=self._temperature,
            reasoning_effort=self._reasoning_effort,
        )
