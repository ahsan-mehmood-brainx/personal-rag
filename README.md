# Personal RAG Assistant

A local, single-user web app that answers questions about its owner using only the documents
the owner uploads (CV, project notes, certifications). Anything outside that scope gets a polite,
fixed refusal. It is a learning project, so every stage of the retrieval-augmented generation
pipeline lives in plain code in this repository, with no LangChain or LlamaIndex.

> Status: Phase 0 (scaffold). Most sections below are placeholders filled in by later phases.

## Requirements

- macOS, Linux, or Windows with [uv](https://docs.astral.sh/uv/) installed
- Python 3.11 or newer (uv can install it for you)
- An OpenAI API key

## Setup

```bash
uv sync
cp .env.example .env
# then edit .env: set OPENAI_API_KEY, OWNER_NAME, CLASSIFIER_MODEL, GENERATION_MODEL
```

`.env` is gitignored. Never commit it, and never commit anything under `data/`, which holds your
documents and the vector index.

## Running

_To be written in Phase 4 (API) and Phase 5 (UI)._

## Architecture

_To be written in Phase 7: Mermaid diagram, what each module does, how each gate works._

## Testing

```bash
uv run pytest        # offline, never calls OpenAI
uv run ruff check .
```

## Evaluation and tuning

_To be written in Phase 6._

## Known limitations

_To be written in Phase 7._
