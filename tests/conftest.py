"""Shared pytest fixtures: the synthetic persona, with DOCX/PDF files generated on the fly."""

from pathlib import Path

import pytest

from tests.fixtures.make_fixtures import PERSONA_DIR, make_all


@pytest.fixture(scope="session")
def persona_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory holding all four persona files (text ones copied, binaries generated)."""
    directory = tmp_path_factory.mktemp("persona")
    for name in ("cv.md", "projects.txt"):
        (directory / name).write_bytes((PERSONA_DIR / name).read_bytes())
    make_all(directory)
    return directory
