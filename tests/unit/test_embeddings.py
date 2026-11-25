"""OpenAIEmbedder with a stub client: batching, ordering, usage accounting, error wrapping."""

from types import SimpleNamespace

import httpx
import openai
import pytest

from personal_rag.llm.client import UpstreamError
from personal_rag.llm.embeddings import MAX_BATCH_SIZE, OpenAIEmbedder


class StubEmbeddings:
    def __init__(self, shuffle: bool = False, fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.shuffle = shuffle
        self.fail = fail

    def create(self, *, model: str, input: list[str]):  # noqa: A002 - mirrors the SDK
        self.calls.append(list(input))
        if self.fail:
            request = httpx.Request("POST", "https://example.invalid")
            raise openai.APIConnectionError(request=request)
        # Each vector encodes its input's text length so order can be checked.
        data = [SimpleNamespace(index=i, embedding=[float(len(t))]) for i, t in enumerate(input)]
        if self.shuffle:
            data.reverse()
        return SimpleNamespace(data=data, usage=SimpleNamespace(total_tokens=len(input) * 10))


def make(stub: StubEmbeddings) -> OpenAIEmbedder:
    return OpenAIEmbedder(SimpleNamespace(embeddings=stub), "m")  # type: ignore[arg-type]


def test_batches_of_at_most_100_and_preserves_order() -> None:
    stub = StubEmbeddings(shuffle=True)
    texts = ["x" * (i + 1) for i in range(250)]
    vectors = make(stub).embed_documents(texts)
    assert [len(c) for c in stub.calls] == [100, 100, 50]
    assert max(len(c) for c in stub.calls) == MAX_BATCH_SIZE
    assert [v[0] for v in vectors] == [float(len(t)) for t in texts]


def test_tracks_token_usage() -> None:
    embedder = make(StubEmbeddings())
    embedder.embed_documents(["a", "b", "c"])
    embedder.embed_query("q")
    assert embedder.tokens_used == 40


def test_upstream_failures_become_upstream_error() -> None:
    with pytest.raises(UpstreamError):
        make(StubEmbeddings(fail=True)).embed_query("q")


def test_empty_input_makes_no_calls() -> None:
    stub = StubEmbeddings()
    assert make(stub).embed_documents([]) == []
    assert stub.calls == []
