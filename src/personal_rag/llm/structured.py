"""One helper for every structured-output call to the Responses API.

Pipeline position: used by the scope classifier, the generator and the groundedness checker.
Centralizing the call means temperature and reasoning effort are applied identically and only
when configured, errors are mapped to `UpstreamError`, and token usage is reported uniformly.
"""

import logging
from typing import TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from personal_rag.llm.client import UpstreamError
from personal_rag.schemas import TokenUsage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def parse_structured(
    client: OpenAI,
    *,
    model: str,
    instructions: str,
    user_input: str,
    schema: type[T],
    temperature: float | None,
    reasoning_effort: str | None,
) -> tuple[T, TokenUsage]:
    """Call `responses.parse` and return the validated model plus token usage.

    Raises UpstreamError on API failure, a refusal, or output that does not match the schema,
    so callers can fail closed.
    """
    options: dict[str, object] = {}
    if temperature is not None:  # some models reject the parameter, so omit unless set
        options["temperature"] = temperature
    if reasoning_effort is not None:
        options["reasoning"] = {"effort": reasoning_effort}

    try:
        response = client.responses.parse(
            model=model,
            instructions=instructions,
            input=user_input,
            text_format=schema,
            # Do not ask OpenAI to retain these requests: they contain personal documents.
            store=False,
            **options,  # type: ignore[arg-type]
        )
    except OpenAIError as exc:
        logger.error("LLM request failed: %s", type(exc).__name__)
        raise UpstreamError("The language model request failed.") from None

    parsed = response.output_parsed
    if parsed is None:
        logger.error("LLM returned no parseable output (status=%s)", response.status)
        raise UpstreamError("The language model returned no valid output.")

    usage = TokenUsage()
    if response.usage is not None:
        details = response.usage.output_tokens_details
        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            reasoning_tokens=details.reasoning_tokens if details else 0,
        )
    return parsed, usage
