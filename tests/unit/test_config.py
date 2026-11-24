"""Tests for settings loading: required vars, blank handling, validation, and secret hygiene."""

from pathlib import Path

import pytest

from personal_rag.config import ConfigError, Settings, load_settings

FAKE_KEY = "fake-test-key-not-real-0123456789abcdef"

REQUIRED = {
    "OPENAI_API_KEY": FAKE_KEY,
    "OWNER_NAME": "Jordan Avery",
    "CLASSIFIER_MODEL": "classifier-model-id",
    "GENERATION_MODEL": "generation-model-id",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any settings already exported in the developer's shell."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def set_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_loads_required_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, REQUIRED)
    settings = load_settings(env_file=None)

    assert settings.owner_name == "Jordan Avery"
    assert settings.openai_api_key.get_secret_value() == FAKE_KEY
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.top_k == 5
    assert settings.similarity_threshold == pytest.approx(0.30)
    assert settings.chunk_size_tokens == 400
    assert settings.chunk_overlap_tokens == 60
    assert settings.llm_temperature is None
    assert settings.enable_groundedness_check is False
    assert settings.chroma_dir == Path("data/chroma")
    assert settings.uploads_dir == Path("data/uploads")
    assert settings.max_upload_bytes == 10 * 1024 * 1024


def test_missing_required_vars_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {"OPENAI_API_KEY": FAKE_KEY})
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)

    message = str(info.value)
    for name in ("OWNER_NAME", "CLASSIFIER_MODEL", "GENERATION_MODEL"):
        assert name in message
    assert "OPENAI_API_KEY" not in message


def test_error_message_never_contains_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Missing fields plus an invalid one: both paths must stay value-free.
    set_env(monkeypatch, {"OPENAI_API_KEY": FAKE_KEY, "TOP_K": "not-a-number"})
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)

    assert FAKE_KEY not in str(info.value)
    assert "not-a-number" not in str(info.value)
    assert "TOP_K" in str(info.value)
    # No chained exception that a logger could print with the inputs.
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


def test_key_is_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, REQUIRED)
    settings = load_settings(env_file=None)
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings.model_dump())


def test_blank_values_from_env_file_count_as_missing(tmp_path: Path) -> None:
    # Mirrors a freshly copied .env.example where required values are still blank.
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=\nOWNER_NAME=Jordan Avery\nCLASSIFIER_MODEL=\nGENERATION_MODEL=g\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=env_file)

    assert "OPENAI_API_KEY" in str(info.value)
    assert "CLASSIFIER_MODEL" in str(info.value)


def test_env_file_values_load(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    lines = [f"{key}={value}" for key, value in REQUIRED.items()]
    lines += ["TOP_K=8", "LLM_TEMPERATURE=0", "ENABLE_GROUNDEDNESS_CHECK=true", "LOG_LEVEL=debug"]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    settings = load_settings(env_file=env_file)
    assert settings.top_k == 8
    assert settings.llm_temperature == 0.0
    assert settings.enable_groundedness_check is True
    assert settings.log_level == "DEBUG"


def test_blank_temperature_means_omit(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {**REQUIRED, "LLM_TEMPERATURE": ""})
    assert load_settings(env_file=None).llm_temperature is None


def test_overlap_must_be_smaller_than_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {**REQUIRED, "CHUNK_SIZE_TOKENS": "100", "CHUNK_OVERLAP_TOKENS": "100"})
    with pytest.raises(ConfigError, match="CHUNK_OVERLAP_TOKENS"):
        load_settings(env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [("SIMILARITY_THRESHOLD", "1.5"), ("TOP_K", "0"), ("LOG_LEVEL", "VERBOSE")],
)
def test_out_of_range_values_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    set_env(monkeypatch, {**REQUIRED, name: value})
    with pytest.raises(ConfigError, match=name):
        load_settings(env_file=None)


def test_env_example_keys_match_settings() -> None:
    # Keeps .env.example and Settings from drifting apart.
    example = Path(__file__).resolve().parents[2] / ".env.example"
    keys = {
        line.split("=", 1)[0].strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert keys == {name.upper() for name in Settings.model_fields}


def test_reasoning_effort_defaults_to_low_and_is_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch, REQUIRED)
    settings = load_settings(env_file=None)
    assert settings.classifier_reasoning_effort == "low"
    assert settings.generation_reasoning_effort == "low"

    set_env(monkeypatch, {"GENERATION_REASONING_EFFORT": "high", "CLASSIFIER_REASONING_EFFORT": ""})
    settings = load_settings(env_file=None)
    assert settings.generation_reasoning_effort == "high"
    assert settings.classifier_reasoning_effort == "low"  # blank falls back to the default


def test_invalid_reasoning_effort_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {**REQUIRED, "CLASSIFIER_REASONING_EFFORT": "turbo"})
    with pytest.raises(ConfigError, match="CLASSIFIER_REASONING_EFFORT"):
        load_settings(env_file=None)


def test_reasoning_effort_off_means_omit(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {**REQUIRED, "GENERATION_REASONING_EFFORT": "off"})
    assert load_settings(env_file=None).generation_reasoning_effort is None


def test_api_base_url_must_be_http(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {**REQUIRED, "API_BASE_URL": "127.0.0.1:8000"})
    with pytest.raises(ConfigError, match="API_BASE_URL"):
        load_settings(env_file=None)
