from pathlib import Path

import pytest
from starlette.datastructures import Headers

from projeto_dvd.api.security import same_origin
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from tests.client import client_for
from tests.tree import make_file


@pytest.mark.parametrize(
    ("headers", "allowed"),
    [
        ({}, True),  # not a browser: no CSRF possible
        ({"sec-fetch-site": "same-origin"}, True),
        ({"sec-fetch-site": "none"}, True),
        ({"sec-fetch-site": "same-site"}, False),  # another port of localhost
        ({"sec-fetch-site": "cross-site"}, False),
        ({"origin": "http://localhost:8000", "host": "localhost:8000"}, True),
        ({"origin": "http://evil.example", "host": "localhost:8000"}, False),
    ],
)
def test_same_origin(headers: dict[str, str], allowed: bool) -> None:
    assert same_origin(Headers(headers)) is allowed


def test_cross_site_post_is_refused_and_get_is_not(tmp_path: Path, database_url: str) -> None:
    make_file(tmp_path / "Disco" / "a.mkv")
    with client_for(create_app(Settings(media_dir=tmp_path, database_url=database_url))) as client:
        refused = client.post("/folders/Disco/scan", headers={"Sec-Fetch-Site": "cross-site"})
        page = client.get("/folders/Disco", headers={"Sec-Fetch-Site": "cross-site"})

    assert refused.status_code == 403
    assert page.status_code == 200


def test_unknown_host_is_refused(tmp_path: Path, database_url: str) -> None:
    app = create_app(Settings(media_dir=tmp_path, database_url=database_url))
    with client_for(app) as client:
        response = client.get("/", headers={"Host": "rebind.example"})

    assert response.status_code == 400
