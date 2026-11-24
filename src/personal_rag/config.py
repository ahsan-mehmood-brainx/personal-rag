"""Application settings loaded from environment variables and `.env`.

Pipeline position: shared by every stage. Ingestion reads chunk sizes, upload limits and
paths; the LLM layer reads model IDs, the API key and temperature; the query pipeline reads
TOP_K and the similarity threshold. Everything is validated once, at startup, so a bad value
fails fast instead of surfacing halfway through a request.

Secrets: the API key is held as a `SecretStr`, so it prints as `**********`. Validation errors
are re-raised as `ConfigError` naming only the variable, never its value.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = Path(".env")

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
# Values accepted by the installed openai SDK (`openai.types.shared.ReasoningEffort`). Not every
# model supports every value; the API reports an error for unsupported combinations.
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]


class ConfigError(RuntimeError):
    """Raised when settings are missing or invalid. The message never contains values."""


class Settings(BaseSettings):
    """Validated settings. Field names map to upper-case environment variables."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        # `.env.example` ships with blank values such as `OPENAI_API_KEY=`. Treating blanks as
        # unset makes them fail the "required" check, and lets `LLM_TEMPERATURE=` mean "omit".
        env_ignore_empty=True,
        extra="ignore",
        str_strip_whitespace=True,
        # Pydantic's default error text includes the offending input, which for a missing field
        # is the whole settings dict, including the API key.
        hide_input_in_errors=True,
    )

    # Required
    openai_api_key: SecretStr = Field(min_length=1)
    owner_name: str = Field(min_length=1)
    classifier_model: str = Field(min_length=1)
    generation_model: str = Field(min_length=1)

    # Models
    embedding_model: str = Field(default="text-embedding-3-small", min_length=1)
    # None means "do not send temperature": some models reject the parameter entirely.
    llm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    # Reasoning models spend hidden tokens thinking; "low" keeps latency and cost modest. Sent to
    # the Responses API only when not None. A blank variable falls back to "low", so set the
    # variable to "off" to omit the parameter (needed for models that are not reasoning models).
    classifier_reasoning_effort: ReasoningEffort | None = "low"
    generation_reasoning_effort: ReasoningEffort | None = "low"

    # Retrieval. Similarity is 1 - cosine distance, so its theoretical range is [-1, 1].
    top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.30, ge=-1.0, le=1.0)

    # Chunking
    chunk_size_tokens: int = Field(default=400, ge=50)
    chunk_overlap_tokens: int = Field(default=60, ge=0)

    # Limits, paths, features
    max_upload_mb: int = Field(default=10, ge=1)
    max_question_chars: int = Field(default=1000, ge=1)
    data_dir: Path = Path("./data")
    api_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000")
    enable_groundedness_check: bool = False
    log_level: LogLevel = "INFO"

    @field_validator("classifier_reasoning_effort", "generation_reasoning_effort", mode="before")
    @classmethod
    def _off_means_omit(cls, value: object) -> object:
        return None if isinstance(value, str) and value.strip().lower() == "off" else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> "Settings":
        # Overlap >= size would make the chunker re-emit the same window forever.
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")
        return self

    @property
    def uploads_dir(self) -> Path:
        """Where original uploaded files are stored."""
        return self.data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        """Where the ChromaDB persistent client keeps its files."""
        return self.data_dir / "chroma"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def _describe(error: ValidationError) -> str:
    """Turn a ValidationError into a message that names variables but never shows values."""
    missing: list[str] = []
    invalid: list[str] = []
    for item in error.errors(include_input=False, include_url=False):
        name = ".".join(str(part) for part in item["loc"]).upper()
        if item["type"] == "missing":
            missing.append(name)
        else:
            # Model-level validators have an empty loc; their message already names the vars.
            invalid.append(f"{name}: {item['msg']}" if name else item["msg"])

    lines = ["Invalid configuration."]
    if missing:
        lines.append("Missing required setting(s): " + ", ".join(missing) + ".")
    if invalid:
        lines.append("Invalid setting(s): " + "; ".join(invalid) + ".")
    lines.append("Copy .env.example to .env and fill in the values.")
    return " ".join(lines)


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
    """Load and validate settings, raising ConfigError with a value-free message on failure.

    Pass `env_file=None` to read only the process environment (used by tests so a developer's
    real `.env` never leaks into them).
    """
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        # `from None` drops the original traceback, which could otherwise be logged with inputs.
        raise ConfigError(_describe(exc)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, loaded once. Tests should call `load_settings` directly."""
    return load_settings()
