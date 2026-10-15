from pathlib import Path

import pytest

from projeto_dvd.config import Settings


def test_defaults_point_to_the_container_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIA_DIR", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings()

    assert settings.media_dir == Path("/media")
    assert settings.database_url == "sqlite:////data/projeto_dvd.db"


def test_environment_variables_override_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", "/tmp/entrada")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/test.db")

    settings = Settings()

    assert settings.media_dir == Path("/tmp/entrada")
    assert settings.database_url == "sqlite:////tmp/test.db"
