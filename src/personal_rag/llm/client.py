"""OpenAI client factory and the shared upstream error type.

Pipeline position: every OpenAI call (embeddings, classifier, generator) goes through a
client built here, so timeout and retry behavior is defined in exactly one place. The SDK's own
`timeout` and `max_retries` are used instead of a retry library.
"""

from openai import OpenAI

from personal_rag.config import Settings

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3


class UpstreamError(RuntimeError):
    """An OpenAI call failed or returned unusable output. The API maps this to HTTP 502."""


def make_client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )
