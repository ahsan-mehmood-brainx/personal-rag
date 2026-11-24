"""UI tests: Streamlit AppTest runs ui/app.py against the real API app wired to fakes.

The UI's httpx client is swapped for a Starlette TestClient (an httpx.Client), so the whole
UI -> HTTP -> API -> pipeline path runs in-process with no network.
"""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from personal_rag import api_client
from personal_rag.api.main import create_app
from personal_rag.api_client import ApiClient, ApiError, ApiUnavailableError
from tests.harness import Harness

APP_PATH = str(Path(__file__).parents[2] / "ui" / "app.py")
QUESTION = "Where did I work as a software engineer on the forecasting pipeline Northwind?"


@pytest.fixture
def backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Harness, TestClient]]:
    harness = Harness(tmp_path)
    with TestClient(create_app(harness.context), base_url="http://127.0.0.1:8000") as client:
        monkeypatch.setattr(api_client, "make_http_client", lambda _url: client)
        yield harness, client


def seed(harness: Harness, persona_dir: Path) -> None:
    harness.ingestion.ingest("cv.md", (persona_dir / "cv.md").read_bytes())


def run_app() -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def test_sidebar_shows_health_and_documents(backend, persona_dir: Path) -> None:
    harness, _ = backend
    seed(harness, persona_dir)
    app = run_app()
    assert any("API online" in s.value and "1 document" in s.value for s in app.sidebar.success)
    assert any("cv\\.md" in m.value for m in app.sidebar.markdown)  # Markdown-escaped name
    assert any(b.key and b.key.startswith("delete-") for b in app.sidebar.button)


def test_empty_knowledge_base_message(backend) -> None:
    app = run_app()
    assert any("No documents yet" in c.value for c in app.sidebar.caption)


def test_delete_button_removes_document(backend, persona_dir: Path) -> None:
    harness, client = backend
    seed(harness, persona_dir)
    app = run_app()
    next(b for b in app.sidebar.button if b.key.startswith("delete-")).click().run()
    assert client.get("/documents").json() == []


def test_question_shows_badge_answer_and_sources(backend, persona_dir: Path) -> None:
    harness, _ = backend
    seed(harness, persona_dir)
    app = run_app()
    app.chat_input[0].set_value(QUESTION).run()
    assert not app.exception, app.exception
    assert ":green-badge[Answered]" in [m.value for m in app.markdown]
    assert any("Fake answer." in m.value for m in app.chat_message[1].markdown)
    assert any("Sources" in e.label for e in app.expander)


def test_show_internals_toggle_sends_debug(backend, persona_dir: Path) -> None:
    harness, _ = backend
    seed(harness, persona_dir)
    app = run_app()
    app.sidebar.toggle[0].set_value(True).run()
    app.chat_input[0].set_value(QUESTION).run()
    assert any(e.label == "Internals" for e in app.expander)
    assert any("Classifier" in m.value for e in app.expander for m in e.markdown)


def test_refusal_has_out_of_scope_badge_and_fixed_message(backend, persona_dir: Path) -> None:
    harness, _ = backend
    seed(harness, persona_dir)
    harness.classifier.category = "out_of_scope"
    app = run_app()
    app.chat_input[0].set_value("What is the capital of France?").run()
    assert ":red-badge[Out of scope]" in [m.value for m in app.markdown]
    assert any("only help with questions about your own" in m.value for m in app.markdown)
    assert not any(e.label.startswith("Sources") for e in app.expander)


def test_invalid_question_shows_error_not_crash(backend, persona_dir: Path) -> None:
    harness, _ = backend
    seed(harness, persona_dir)
    app = run_app()
    app.chat_input[0].set_value("x" * 400).run()
    assert not app.exception
    assert any("longer than" in e.value for e in app.error)


def test_api_offline_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def dead(_url: str) -> httpx.Client:
        return httpx.Client(
            base_url="http://127.0.0.1:1", transport=httpx.MockTransport(_refuse)
        )

    monkeypatch.setattr(api_client, "make_http_client", dead)
    app = run_app()
    assert any("API offline" in e.value for e in app.sidebar.error)


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


# --- ApiClient ----------------------------------------------------------------------------


def make_client(handler) -> ApiClient:
    return ApiClient(httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler)))


def test_client_translates_connection_errors() -> None:
    with pytest.raises(ApiUnavailableError):
        make_client(_refuse).health()


def test_client_surfaces_error_detail_only() -> None:
    client = make_client(lambda r: httpx.Response(415, json={"detail": "Unsupported file type."}))
    with pytest.raises(ApiError) as info:
        client.upload("a.exe", b"x", None)
    assert (info.value.status_code, info.value.detail) == (415, "Unsupported file type.")


def test_client_ask_returns_error_body_on_502() -> None:
    body = {"status": "error", "answer": "fixed message", "sources": [], "debug": None}
    response = make_client(lambda r: httpx.Response(502, json=body)).ask("q")
    assert response.status == "error"
    assert response.answer == "fixed message"


def test_client_ask_rejects_unexpected_body() -> None:
    client = make_client(lambda r: httpx.Response(500, text="<html>boom</html>"))
    with pytest.raises(ApiError) as info:
        client.ask("q")
    assert "boom" not in info.value.detail


@pytest.mark.parametrize("call", [
    lambda c: c.health(),
    lambda c: c.list_documents(),
    lambda c: c.upload("a.md", b"x", None),
])
@pytest.mark.parametrize("body", [httpx.Response(200, text="not json")])
def test_client_wraps_non_json_200_bodies_in_api_error(call, body: httpx.Response) -> None:
    with pytest.raises(ApiError):
        call(make_client(lambda r: body))


@pytest.mark.parametrize("call", [lambda c: c.health(), lambda c: c.list_documents()])
def test_client_wraps_wrong_shape_200_bodies_in_api_error(call) -> None:
    with pytest.raises(ApiError):
        call(make_client(lambda r: httpx.Response(200, json=[{"unexpected": 1}])))


def test_upload_error_message_survives_rerun(backend) -> None:
    app = run_app()
    app.session_state["flash"] = [("error", "bad.exe: Unsupported file type.")]
    app.run()
    assert any("Unsupported file type." in e.value for e in app.sidebar.error)
    assert "flash" not in app.session_state  # shown once, then cleared
