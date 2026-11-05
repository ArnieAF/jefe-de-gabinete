"""Fixtures compartidas de pytest."""
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Raíz del repositorio (la carpeta que contiene `fixtures/` y `packages/`)."""
    return Path(__file__).resolve().parents[1]
