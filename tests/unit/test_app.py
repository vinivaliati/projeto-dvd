import pytest
from fastapi.testclient import TestClient

from projeto_dvd import app as app_module

ALL_FOUND: dict[str, str | None] = {
    "ffmpeg": "7.1.5-0+deb13u1",
    "ffprobe": "7.1.5-0+deb13u1",
    "dvdauthor": "0.7.2",
    "spumux": "0.7.2",
    "xorriso": "1.5.6",
    "tsMuxeR": "2.7.0",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_module.app)


def fake_versions(monkeypatch: pytest.MonkeyPatch, versions: dict[str, str | None]) -> None:
    monkeypatch.setattr(app_module, "detect_versions", lambda: versions)


def test_index_renders_hello_page(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>projeto-dvd</h1>" in response.text


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
