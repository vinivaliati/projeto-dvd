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


def test_work_and_output_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORK_DIR", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)

    settings = Settings()

    assert (settings.work_dir, settings.output_dir) == (Path("/work"), Path("/output"))


def test_tmdb_token_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_TOKEN", "abc123")
    monkeypatch.delenv("TMDB_LANGUAGE", raising=False)

    settings = Settings()

    assert settings.tmdb_token is not None
    assert settings.tmdb_token.get_secret_value() == "abc123"
    assert "abc123" not in repr(settings)
    assert settings.tmdb_language == "pt-BR"


def test_tmdb_token_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMDB_TOKEN", raising=False)

    assert Settings().tmdb_token is None
