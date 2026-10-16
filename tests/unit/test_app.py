from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from projeto_dvd.api import health
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from tests.client import client_for

ALL_FOUND: dict[str, str | None] = {
    "ffmpeg": "7.1.5-0+deb13u1",
    "ffprobe": "7.1.5-0+deb13u1",
    "dvdauthor": "0.7.2",
    "spumux": "0.7.2",
    "xorriso": "1.5.6",
    "genisoimage": "1.1.11",
    "tsMuxeR": "2.7.0",
}


@pytest.fixture
def client(tmp_path: Path, database_url: str) -> TestClient:
    return client_for(create_app(Settings(media_dir=tmp_path, database_url=database_url)))


def fake_versions(monkeypatch: pytest.MonkeyPatch, versions: dict[str, str | None]) -> None:
    monkeypatch.setattr(health, "detect_versions", lambda: versions)


def test_startup_migrates_an_empty_database(tmp_path: Path, database_url: str) -> None:
    app = create_app(Settings(media_dir=tmp_path, database_url=database_url))

    with client_for(app):
        assert "media_file" in inspect(app.state.engine).get_table_names()


def test_default_settings_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))

    assert create_app().state.settings.media_dir == tmp_path


def test_health_returns_200_when_all_tools_are_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_versions(monkeypatch, ALL_FOUND)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "tools": ALL_FOUND}


def test_health_returns_503_with_null_for_a_missing_tool(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = {**ALL_FOUND, "tsMuxeR": None}
    fake_versions(monkeypatch, versions)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "missing", "tools": versions}


def test_health_returns_503_when_nothing_is_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions: dict[str, str | None] = dict.fromkeys(ALL_FOUND)
    fake_versions(monkeypatch, versions)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "missing", "tools": versions}


@pytest.mark.parametrize(
    ("path", "content"), [("/static/app.css", "--accent"), ("/static/htmx.min.js", "htmx")]
)
def test_static_files_are_served(client: TestClient, path: str, content: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert content in response.text
