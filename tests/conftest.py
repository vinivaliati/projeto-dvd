import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import ImageFont
from sqlalchemy import Engine
from sqlmodel import Session

from projeto_dvd.db.session import make_engine, migrate
from projeto_dvd.menus import render


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    migrate(database_url)
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def menu_font(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests draw menus with Pillow's own font: the DejaVu files exist only in the image."""
    if os.environ.get("REAL_FONTS") != "1":
        monkeypatch.setattr(render, "dejavu", lambda size, bold: ImageFont.load_default(size=size))
