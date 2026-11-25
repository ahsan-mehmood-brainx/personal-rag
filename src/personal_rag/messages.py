"""Fixed user-facing messages for every non-answer status.

Pipeline position: the final step of the query pipeline. Whenever a gate stops a
question (out of scope, not found, no documents, error) or the user sends a meta
message, the response text comes from this module. The LLM never writes a refusal,
so refusals cannot be talked into leaking content and stay consistent across runs.
"""

OUT_OF_SCOPE = (
    "I can only help with questions about your own background, such as your experience, "
    "education, skills, and projects, based on the documents you've uploaded. That question "
    "is outside what I can answer here. If your message combined a personal question with "
    "something else, try asking the personal part on its own."
)

NOT_FOUND = (
    "I couldn't find that in your uploaded documents, so I won't guess. If it should be "
    "there, try rephrasing the question or upload a document that covers it."
)

NO_DOCUMENTS = (
    "No documents have been uploaded yet. Upload your CV or other personal documents "
    "to get started."
)

META = (
    "I'm your personal knowledge assistant. I answer questions about your experience, "
    "education, skills, projects, and other details from the {count} document(s) you've "
    "uploaded, and I show which document each answer came from. I don't answer general "
    "questions."
)

ERROR = (
    "Something went wrong while processing your question, so I didn't answer it. Please try again."
)


def meta_message(count: int) -> str:
    """Return the help message with the number of indexed documents filled in."""
    return META.format(count=count)
