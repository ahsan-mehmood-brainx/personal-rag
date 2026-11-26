"""HTTP client for the FastAPI backend, used by the Streamlit UI.

Pipeline position: the UI's only way to reach the app. It holds no business logic: each method
is one HTTP call plus error translation. Keeping it in the package (not in `ui/`) makes it
importable and testable without Streamlit.
"""

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from personal_rag.schemas import AskResponse, DocumentInfo

REQUEST_TIMEOUT_SECONDS = 120.0  # an answer involves two LLM calls; allow for slow reasoning


class ApiUnavailableError(RuntimeError):
    """The backend could not be reached."""


class ApiError(RuntimeError):
    """The backend answered with an error status. `detail` is safe to show to the user."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class Health:
    documents: int
    chunks: int
    embedding_model: str
    index_usable: bool


def make_http_client(base_url: str) -> httpx.Client:
    """Factory kept separate so tests can swap in a client wired to an in-process app."""
    return httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS)


class ApiClient:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise ApiUnavailableError("Cannot reach the API. Is the server running?") from None

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return f"Request failed (HTTP {response.status_code})."
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, str):
            return detail
        return f"Request failed (HTTP {response.status_code})."

    def _ok_json(self, response: httpx.Response) -> Any:
        """Body of a 200 response, or ApiError for an error status or an unusable body."""
        if response.status_code != 200:
            raise ApiError(response.status_code, self._detail(response))
        try:
            return response.json()
        except ValueError:
            raise ApiError(200, "The API returned an unexpected response.") from None

    def health(self) -> Health:
        body = self._ok_json(self._request("GET", "/health"))
        try:
            return Health(
                documents=body["documents"],
                chunks=body["chunks"],
                embedding_model=body["embedding_model"],
                index_usable=body["index_usable"],
            )
        except (KeyError, TypeError):
            raise ApiError(200, "The API returned an unexpected response.") from None

    def list_documents(self) -> list[DocumentInfo]:
        body = self._ok_json(self._request("GET", "/documents"))
        try:
            return [DocumentInfo(**item) for item in body]
        except (TypeError, ValidationError):
            raise ApiError(200, "The API returned an unexpected response.") from None

    def upload(self, filename: str, data: bytes, content_type: str | None) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/documents",
            files={"file": (filename, data, content_type or "application/octet-stream")},
        )
        body = self._ok_json(response)
        if not isinstance(body, dict):
            raise ApiError(200, "The API returned an unexpected response.")
        return body

    def delete(self, doc_id: str) -> None:
        response = self._request("DELETE", f"/documents/{doc_id}")
        if response.status_code != 200:
            raise ApiError(response.status_code, self._detail(response))

    def ask(
        self, question: str, debug: bool = False, allow_external_search: bool = False
    ) -> AskResponse:
        """Ask a question. A 502 still carries a fixed-message AskResponse (status `error`)."""
        response = self._request(
            "POST",
            "/ask",
            json={
                "question": question,
                "debug": debug,
                "allow_external_search": allow_external_search,
            },
        )
        if response.status_code in (200, 502):
            try:
                return AskResponse(**response.json())
            except (ValueError, ValidationError):
                pass
        raise ApiError(response.status_code, self._detail(response))
