"""Grounded generation, plus the optional groundedness check.

Pipeline position: step 3, reached only when the evidence gate found chunks. The model sees
excerpts labeled S1..Sn (never internal chunk IDs) and must answer from them alone, citing the
labels it used. Its output is untrusted until the validator (gate 3) checks it.
"""

from datetime import date
from typing import Protocol

from openai import OpenAI

from personal_rag.llm.prompts import (
    GROUNDEDNESS_SYSTEM,
    build_generator_input,
    build_groundedness_input,
    generator_instructions,
)
from personal_rag.llm.structured import parse_structured
from personal_rag.schemas import GroundedAnswer, GroundednessVerdict, LabeledChunk, TokenUsage


class AnswerGenerator(Protocol):
    def generate(
        self, question: str, excerpts: list[LabeledChunk], today: date
    ) -> tuple[GroundedAnswer, TokenUsage]: ...


class GroundednessChecker(Protocol):
    def check(
        self, answer: str, excerpts: list[LabeledChunk]
    ) -> tuple[GroundednessVerdict, TokenUsage]: ...


class OpenAIAnswerGenerator:
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
        self._instructions = generator_instructions(owner_name)
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort

    def generate(
        self, question: str, excerpts: list[LabeledChunk], today: date
    ) -> tuple[GroundedAnswer, TokenUsage]:
        return parse_structured(
            self._client,
            model=self._model,
            instructions=self._instructions,
            user_input=build_generator_input(question, excerpts, today),
            schema=GroundedAnswer,
            temperature=self._temperature,
            reasoning_effort=self._reasoning_effort,
        )


class OpenAIGroundednessChecker:
    """Second LLM call that verifies every claim against the cited excerpts (experimental)."""

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

    def check(
        self, answer: str, excerpts: list[LabeledChunk]
    ) -> tuple[GroundednessVerdict, TokenUsage]:
        return parse_structured(
            self._client,
            model=self._model,
            instructions=GROUNDEDNESS_SYSTEM,
            user_input=build_groundedness_input(answer, excerpts),
            schema=GroundednessVerdict,
            temperature=self._temperature,
            reasoning_effort=self._reasoning_effort,
        )
