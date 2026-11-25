"""The eval harness end to end, with fake services (no network, no API key)."""

from pathlib import Path

import pytest
from evals import run_eval
from evals.cases import EvalCase

from personal_rag.config import Settings, load_settings
from personal_rag.ingestion.service import IngestionService
from personal_rag.llm.client import UpstreamError
from personal_rag.query.pipeline import QueryPipeline
from personal_rag.services import Services
from personal_rag.store.vector_store import IndexMismatchError, VectorStore
from tests.fakes import FakeClassifier, FakeEmbedder, FakeGenerator

REQUIRED = {
    "OPENAI_API_KEY": "fake-test-key-not-real-0123456789abcdef",
    "OWNER_NAME": "Jordan Avery",
    "CLASSIFIER_MODEL": "classifier-model-id",
    "GENERATION_MODEL": "generation-model-id",
}


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "real-data"))
    return load_settings(env_file=None)


class Builder:
    """Services factory that records which data dirs it was asked to build for."""

    def __init__(self, category: str = "personal") -> None:
        self.data_dirs: list[Path] = []
        self.category = category

    def __call__(self, settings: Settings) -> Services:
        self.data_dirs.append(settings.data_dir)
        embedder = FakeEmbedder()
        store = VectorStore(settings.chroma_dir, "fake-embedding-model")
        ingestion = IngestionService(
            embedder=embedder,
            store=store,
            uploads_dir=settings.uploads_dir,
            max_bytes=settings.max_upload_bytes,
            chunk_size=400,
            overlap=60,
        )
        pipeline = QueryPipeline(
            classifier=FakeClassifier(self.category),
            embedder=embedder,
            store=store,
            generator=FakeGenerator(),
            top_k=5,
            similarity_threshold=0.1,
            max_question_chars=1000,
        )
        return Services(embedder=embedder, store=store, ingestion=ingestion, pipeline=pipeline)  # type: ignore[arg-type]


def run(settings, builder, tmp_path, *extra, confirm=lambda _: True):
    argv = ["--report-dir", str(tmp_path / "reports"), *extra]
    return run_eval.main(
        argv, settings_loader=lambda: settings, services_builder=builder, confirm=confirm
    )


def test_synthetic_run_writes_report_and_never_touches_real_data_dir(
    settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = Builder()
    assert run(settings, builder, tmp_path, "--yes") == 0

    assert len(builder.data_dirs) == 1
    assert builder.data_dirs[0] != settings.data_dir
    assert not settings.data_dir.exists(), "the real data dir must not even be created"
    out = capsys.readouterr().out
    assert "54 questions x 1 repeat(s)" in out
    assert "Estimated OpenAI calls: 54 to 162" in out
    reports = list((tmp_path / "reports").glob("*.md"))
    assert len(reports) == 1
    text = reports[0].read_text()
    assert "## Failures" in text and "Out-of-scope leak rate" in text
    # Report lists model IDs and tunables but never the API key or owner name.
    assert REQUIRED["OPENAI_API_KEY"] not in text
    assert "Jordan Avery" not in text.split("## Failures")[0]


def test_repeats_multiply_runs_and_report_consistency(settings: Settings, tmp_path: Path) -> None:
    assert run(settings, Builder(), tmp_path, "--yes", "--repeats", "2") == 0
    text = next((tmp_path / "reports").glob("*.md")).read_text()
    assert "108 runs" in text
    assert "All cases returned the same status in every repeat." in text


def test_prompt_is_shown_and_no_answer_aborts_without_spending(
    settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = Builder()
    prompts: list[str] = []

    def decline(prompt: str) -> bool:
        prompts.append(prompt)
        return False

    assert run(settings, builder, tmp_path, confirm=decline) == 1
    assert prompts and "costs money" in prompts[0]
    assert builder.data_dirs == []
    assert "Aborted." in capsys.readouterr().out


def test_real_kb_requires_a_personal_dataset(settings: Settings, tmp_path: Path) -> None:
    builder = Builder()
    assert run(settings, builder, tmp_path, "--yes", "--kb", "real") == 2
    assert builder.data_dirs == []


def test_real_kb_with_empty_index_refuses(
    settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = tmp_path / "personal.yaml"
    dataset.write_text("- id: p1\n  category: meta\n  question: hi\n  expected_status: meta\n")
    assert (
        run(settings, Builder(), tmp_path, "--yes", "--kb", "real", "--dataset", str(dataset)) == 1
    )
    assert "empty" in capsys.readouterr().err


def test_invalid_repeats_and_missing_dataset(settings: Settings, tmp_path: Path) -> None:
    assert run(settings, Builder(), tmp_path, "--yes", "--repeats", "0") == 2
    assert run(settings, Builder(), tmp_path, "--yes", "--dataset", str(tmp_path / "x.yaml")) == 1


def test_pipeline_exceptions_are_recorded_not_raised(settings: Settings, tmp_path: Path) -> None:
    builder = Builder()
    services = builder(settings.model_copy(update={"data_dir": tmp_path / "d"}))
    case = EvalCase(id="x", category="meta", question="   ", expected_status="meta")
    runs = run_eval.run_cases([case], services.pipeline, repeats=1)
    assert runs[0].status == "invalid_input"


def test_estimate_calls_includes_groundedness() -> None:
    assert run_eval.estimate_calls(10, 2, groundedness=False) == (20, 60)
    assert run_eval.estimate_calls(10, 2, groundedness=True) == (20, 80)


def test_errored_runs_are_flagged_and_fail_the_exit_code(
    settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing_builder(cfg: Settings) -> Services:
        services = Builder()(cfg)
        services.pipeline._generator = FakeGenerator(raises=UpstreamError("down"))  # noqa: SLF001
        return services

    assert run(settings, failing_builder, tmp_path, "--yes") == 1
    text = next((tmp_path / "reports").glob("*.md")).read_text()
    assert "WARNING" in text
    assert "Errored runs" in text
    assert "ended in `error`" in capsys.readouterr().err


def test_real_kb_guard_resolves_paths(settings: Settings, tmp_path: Path) -> None:
    builder = Builder()
    absolute = str(run_eval.DEFAULT_DATASET.resolve())
    assert run(settings, builder, tmp_path, "--yes", "--kb", "real", "--dataset", absolute) == 2
    assert builder.data_dirs == []
    roundabout = "evals/../evals/dataset.yaml"
    assert run(settings, builder, tmp_path, "--yes", "--kb", "real", "--dataset", roundabout) == 2


def test_aborts_when_the_index_is_unusable(settings: Settings, tmp_path: Path) -> None:
    dataset = tmp_path / "personal.yaml"
    dataset.write_text("- id: p1\n  category: meta\n  question: hi\n  expected_status: meta\n")

    def seeded_but_mismatched(cfg: Settings) -> Services:
        services = Builder()(cfg)
        for path in run_eval.prepare_persona(tmp_path / "persona"):
            services.ingestion.ingest(path.name, path.read_bytes())

        def refuse() -> None:
            raise IndexMismatchError("rebuild needed")

        services.pipeline._store.require_usable = refuse  # type: ignore[method-assign]  # noqa: SLF001
        return services

    code = run(
        settings,
        seeded_but_mismatched,
        tmp_path,
        "--yes",
        "--kb",
        "real",
        "--dataset",
        str(dataset),
    )
    assert code == 1
    assert not (tmp_path / "reports").exists() or not list((tmp_path / "reports").glob("*.md"))
