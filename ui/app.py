"""Streamlit UI for the Personal RAG Assistant.

Pipeline position: a thin client. It sends files and questions to the FastAPI backend and
renders what comes back; it has no business logic, no OpenAI access and no secrets. Chat
history is display-only: version 1 is stateless, so only the latest question is sent.

Run with: uv run streamlit run ui/app.py
"""

import os
import re

import streamlit as st

from personal_rag import api_client
from personal_rag.api_client import ApiClient, ApiError, ApiUnavailableError
from personal_rag.schemas import AskResponse

DEFAULT_API_URL = "http://127.0.0.1:8000"

# status -> (badge label, badge color)
STATUS_BADGES = {
    "answered": ("Answered", "green"),
    "not_found": ("Not in your documents", "orange"),
    "out_of_scope": ("Out of scope", "red"),
    "meta": ("Info", "blue"),
    "no_documents": ("No documents", "gray"),
    "error": ("Error", "red"),
}


def _md(text: str) -> str:
    """Escape Markdown syntax in user-controlled text (file names, headings)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$])", r"\\\1", text)


def _flash(kind: str, message: str) -> None:
    """Queue a sidebar message that survives the `st.rerun()` that refreshes the page."""
    st.session_state.setdefault("flash", []).append((kind, message))


def _show_flash() -> None:
    for kind, message in st.session_state.pop("flash", []):
        getattr(st.sidebar, kind)(message)


def _api_url() -> str:
    return os.environ.get("API_BASE_URL", DEFAULT_API_URL)


def _client() -> ApiClient:
    return ApiClient(api_client.make_http_client(_api_url()))


def render_sidebar(client: ApiClient) -> bool:
    """Health, upload and document list. Returns the state of the 'Show internals' toggle."""
    st.sidebar.title("Knowledge base")

    try:
        health = client.health()
    except (ApiUnavailableError, ApiError) as exc:
        st.sidebar.error(f"API offline. {exc}")
        return st.sidebar.toggle("Show internals", value=False)

    if health.index_usable:
        st.sidebar.success(
            f"API online · {health.documents} document(s) · {health.embedding_model}"
        )
    else:
        st.sidebar.warning(
            "The index was built with a different embedding model. Run "
            "`uv run python -m personal_rag.cli reindex`, then reload."
        )

    _show_flash()
    upload_key = st.session_state.setdefault("upload_key", 0)
    files = st.sidebar.file_uploader(
        "Upload documents",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploader-{upload_key}",
    )
    if files and st.sidebar.button("Add to knowledge base", type="primary"):
        for file in files:
            try:
                result = client.upload(file.name, file.getvalue(), file.type)
                _flash(
                    "success",
                    f"{result['filename']}: {result['status']} ({result['chunk_count']} chunks)",
                )
            except (ApiError, ApiUnavailableError) as exc:
                _flash("error", f"{file.name}: {exc}")
        st.session_state["upload_key"] = upload_key + 1  # resets the uploader widget
        st.rerun()

    try:
        documents = client.list_documents()
    except (ApiError, ApiUnavailableError):
        documents = []
    st.sidebar.subheader("Documents")
    if not documents:
        st.sidebar.caption("No documents yet.")
    for doc in documents:
        name_col, button_col = st.sidebar.columns([4, 1])
        name_col.markdown(f"**{_md(doc.filename)}**  \n{doc.chunk_count} chunks")
        if button_col.button("🗑", key=f"delete-{doc.doc_id}", help=f"Delete {doc.filename}"):
            try:
                client.delete(doc.doc_id)
            except (ApiError, ApiUnavailableError) as exc:
                _flash("error", f"Delete failed: {exc}")
            st.rerun()

    st.sidebar.divider()
    return st.sidebar.toggle(
        "Show internals", value=False, help="Show the classifier decision, scores and latency."
    )


def render_response(response: AskResponse) -> None:
    label, color = STATUS_BADGES[response.status]
    st.badge(label, color=color)
    st.write(response.answer)

    if response.sources:
        with st.expander(f"Sources ({len(response.sources)})"):
            for source in response.sources:
                page = source.page if source.page is not None else "n/a"
                st.markdown(
                    f"**{source.label}** · {_md(source.filename)} · {_md(source.section)} · "
                    f"page {page} · similarity {source.similarity:.3f}"
                )
                st.caption(source.excerpt)

    if response.debug is not None:
        debug = response.debug
        with st.expander("Internals"):
            st.markdown(
                f"**Classifier:** `{debug.classifier_category}`: {debug.classifier_reason}"
            )
            if debug.retrieved:
                st.markdown(f"**Retrieved chunks** (threshold {debug.threshold:.2f})")
                st.table(
                    [
                        {
                            "similarity": round(hit.similarity, 4),
                            "vs threshold": "kept" if hit.kept else "below",
                            "document": hit.filename,
                            "section": hit.section,
                        }
                        for hit in debug.retrieved
                    ]
                )
            st.markdown("**Latency (ms):** " + ", ".join(
                f"{step} {ms:.0f}" for step, ms in debug.latency_ms.items()
            ))
            if debug.token_usage:
                st.markdown("**Tokens:** " + ", ".join(
                    f"{step} {usage.input_tokens}+{usage.output_tokens}"
                    for step, usage in debug.token_usage.items()
                ))


def main() -> None:
    st.set_page_config(page_title="Personal RAG Assistant", page_icon="📚")
    st.title("Personal RAG Assistant")
    st.caption("Ask questions about yourself. Answers come only from your uploaded documents.")

    client = _client()
    show_internals = render_sidebar(client)

    history: list[dict] = st.session_state.setdefault("messages", [])
    for message in history:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.write(message["content"])
            else:
                render_response(message["response"])

    question = st.chat_input("Ask about your experience, skills, projects...")
    if not question:
        return

    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                response = client.ask(question, debug=show_internals)
        except (ApiError, ApiUnavailableError) as exc:
            st.error(str(exc))
            return
        render_response(response)
    history.append({"role": "assistant", "response": response})


main()
