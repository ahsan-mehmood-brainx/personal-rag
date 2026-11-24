"""The preview command: runs offline over every persona file type and rejects bad input."""

from pathlib import Path

import pytest

from personal_rag.cli import main


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Run from an empty directory so a developer's real .env is never read.
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("name", ["cv.md", "projects.txt", "certifications.docx", "cv_onepage.pdf"])
def test_preview_each_persona_file(
    name: str, persona_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["preview", str(persona_dir / name)]) == 0
    out = capsys.readouterr().out
    assert "chunks=" in out
    assert "tokens=" in out
    assert "Total:" in out


def test_preview_rejects_unsupported_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"MZ")
    assert main(["preview", str(bad)]) == 1
    assert "Rejected" in capsys.readouterr().err


def test_preview_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["preview", str(tmp_path / "nope.md")]) == 1
    assert "Cannot read" in capsys.readouterr().err


@pytest.mark.parametrize(
    "flags", [["--chunk-size", "0"], ["--chunk-size", "50", "--overlap", "50"]]
)
def test_preview_rejects_bad_chunk_settings(
    flags: list[str], persona_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["preview", str(persona_dir / "cv.md"), *flags]) == 2
    assert "overlap" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["ingest", "x.md"], ["search", "q"], ["reindex"]])
def test_live_commands_report_missing_settings_without_values(
    command: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("OPENAI_API_KEY", "OWNER_NAME", "CLASSIFIER_MODEL", "GENERATION_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert main(command) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err
