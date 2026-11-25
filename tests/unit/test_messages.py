"""Tests for the fixed user-facing messages."""

from personal_rag import messages


def test_meta_message_includes_count() -> None:
    text = messages.meta_message(3)
    assert "3 document(s)" in text
    assert "{count}" not in text


def test_fixed_messages_are_non_empty_and_have_no_placeholders() -> None:
    for text in (messages.OUT_OF_SCOPE, messages.NOT_FOUND, messages.NO_DOCUMENTS, messages.ERROR):
        assert text.strip()
        assert "{" not in text
