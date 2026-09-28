"""Fixtures compartilhadas."""

from __future__ import annotations

from pathlib import Path

import pytest

from pencil_tip_gen.config import TipParams

# Fontes comuns em distribuicoes Linux; a primeira que existir e usada.
FONT_CANDIDATES = (
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
)


@pytest.fixture(scope="session")
def font_path() -> Path:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    pytest.skip("nenhuma fonte de teste encontrada no sistema")


@pytest.fixture
def params(font_path: Path) -> TipParams:
    return TipParams(font_path=font_path)


@pytest.fixture
def make_params(font_path: Path):
    def factory(**kwargs) -> TipParams:
        return TipParams(font_path=font_path, **kwargs)

    return factory
