import html
import json
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session, select

from projeto_dvd.api import curation, library
from projeto_dvd.api.deps import get_tmdb
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from projeto_dvd.db.models import MediaFile
from projeto_dvd.library.probe import ProbeResult
from projeto_dvd.metadata.tmdb import TmdbClient
from tests.client import client_for
from tests.tmdb_fakes import MOVIE, router, search_page
from tests.tree import make_file

SAME = {"Sec-Fetch-Site": "same-origin"}
RING = {"id": 101, "title": "Anel Mágico", "original_title": "The Magic Ring",
        "release_date": "2001-12-19", "poster_path": "/posterpt.jpg",
        "overview": "x" * 300}  # fmt: skip
ROUTES: dict[str, object] = {
    "/3/search/movie": search_page(RING),
    "/3/movie/101": MOVIE,
    **{f"/t/p/original{p}": b"img" for p in ("/posterpt.jpg", "/backnull2.jpg", "/logoen.png")},
}
PROBE = json.dumps({"streams": [], "format": {"duration": "10680"}})


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    media = tmp_path / "media"
    make_file(media / "Anel" / "Anel Mágico (2001).mkv")
    (tmp_path / "out").mkdir()
    return Settings(media_dir=media, output_dir=tmp_path / "out", database_url=database_url,
                    tmdb_token=SecretStr("t"))  # fmt: skip


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(library, "run_ffprobe", lambda path: ProbeResult(json=PROBE, error=None))
    app = create_app(settings)

    def fake_tmdb() -> Iterator[TmdbClient]:
        transport = httpx2.MockTransport(router(ROUTES))
        with TmdbClient("t", "pt-BR", transport=transport) as tmdb:
            yield tmdb

    app.dependency_overrides[get_tmdb] = fake_tmdb
    with client_for(app) as test_client:
        test_client.post("/folders/Anel/scan", headers=SAME)
        yield test_client


def file_id(client: TestClient) -> int:
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        row = session.exec(select(MediaFile)).one()
        assert row.id is not None
        return row.id


def test_without_token_shows_how_to_configure(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"tmdb_token": None}))
    with client_for(app) as test_client:
        page = test_client.get("/folders/Anel").text

    assert "Curadoria desligada" in page
    assert "TMDB_TOKEN" in page
    assert "Buscar no TMDB" not in page


def test_empty_token_counts_as_none(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"tmdb_token": SecretStr("")}))
    with client_for(app) as test_client:
        assert "Curadoria desligada" in test_client.get("/folders/Anel").text


def test_folder_page_order_and_button(client: TestClient) -> None:
    page = client.get("/folders/Anel").text

    assert "Buscar no TMDB" in page
    assert page.index("Match no TMDB") < page.index('<table class="files">')
    assert "Ainda não buscado" in page


def test_search_suggests_and_confirm_all(client: TestClient, settings: Settings) -> None:
    found = client.post("/folders/Anel/match", headers=SAME).text

    assert "Sugestão" in found
    assert "Anel Mágico (2001)" in found
    assert "https://image.tmdb.org/t/p/w92/posterpt.jpg" in found
    done = client.post("/folders/Anel/confirm", headers=SAME).text
    assert "1 título confirmado" in done
    assert "Confirmado" in done
    assert (settings.output_dir / "covers" / "Anel" / "Anel Mágico (2001)" / "poster.jpg").exists()


def test_tmdb_error_is_shown_with_200(client: TestClient) -> None:
    ROUTES_BACKUP = dict(ROUTES)
    ROUTES["/3/search/movie"] = 401
    try:
        response = client.post("/folders/Anel/match", headers=SAME)
    finally:
        ROUTES.clear()
        ROUTES.update(ROUTES_BACKUP)

    assert response.status_code == 200
    assert "O TMDB recusou o token" in response.text


def test_correct_opens_the_search_with_the_guess(client: TestClient) -> None:
    response = client.post(f"/files/{file_id(client)}/search", headers=SAME)

    assert response.status_code == 200
    assert 'value="Anel Mágico"' in response.text
    assert "The Magic Ring" in response.text
    assert "x" * 121 not in response.text


def test_choose_confirms_and_returns_the_card(client: TestClient) -> None:
    fid = file_id(client)
    card = client.post(f"/files/{fid}/choose", headers=SAME,
                       data={"kind": "movie", "tmdb_id": "101"}).text  # fmt: skip

    assert f'id="title-{fid}"' in card
    assert "Confirmado" in card
    assert "<section" not in card


def test_choose_with_a_bad_form_shows_the_error(client: TestClient) -> None:
    card = client.post(f"/files/{file_id(client)}/choose", headers=SAME,
                       data={"kind": "movie", "tmdb_id": "abc"}).text  # fmt: skip

    assert "Formulário inválido" in card


def test_cancel_returns_the_card(client: TestClient) -> None:
    assert "Ainda não buscado" in client.get(f"/files/{file_id(client)}/card").text


def test_unknown_file_is_404(client: TestClient) -> None:
    assert client.get("/files/999/card").status_code == 404


def test_cross_site_post_is_refused(client: TestClient) -> None:
    response = client.post("/folders/Anel/match", headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403


def test_second_search_is_refused(client: TestClient) -> None:
    curation._tmdb_lock.acquire()
    try:
        response = client.post("/folders/Anel/match", headers=SAME)
    finally:
        curation._tmdb_lock.release()

    assert curation.BUSY in html.unescape(response.text)


def test_art_again_route(client: TestClient, settings: Settings) -> None:
    fid = file_id(client)
    client.post(f"/files/{fid}/choose", headers=SAME, data={"kind": "movie", "tmdb_id": "101"})

    card = client.post(f"/files/{fid}/art", headers=SAME).text

    assert "Confirmado" in card


def test_search_a_show_with_season_and_episode(client: TestClient) -> None:
    ROUTES["/3/search/tv"] = search_page({"id": 202, "name": "Amigos de Sempre"})
    try:
        page = client.post(f"/files/{file_id(client)}/search", headers=SAME,
                           data={"kind": "episode", "q": "Amigos", "year": "",
                                 "season": "2", "episode": "5"}).text  # fmt: skip
    finally:
        del ROUTES["/3/search/tv"]

    assert "Amigos de Sempre" in page
    assert 'name="season" inputmode="numeric" size="2" value="2"' in page
    assert 'value="episode" checked' in page


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "movie", "q": ""},
        {"kind": "movie", "q": "x", "year": "abc"},
        {"kind": "x", "q": "a"},
    ],
)
def test_search_with_a_bad_form(client: TestClient, data: dict[str, str]) -> None:
    page = client.post(f"/files/{file_id(client)}/search", headers=SAME, data=data).text

    assert "Formulário inválido" in page


def test_search_error_from_tmdb(client: TestClient) -> None:
    ROUTES_BACKUP = dict(ROUTES)
    ROUTES["/3/search/movie"] = 429
    try:
        page = client.post(f"/files/{file_id(client)}/search", headers=SAME).text
    finally:
        ROUTES.clear()
        ROUTES.update(ROUTES_BACKUP)

    assert "O TMDB pediu para esperar" in page


def test_routes_without_token_explain(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(library, "run_ffprobe", lambda path: ProbeResult(json=PROBE, error=None))
    app = create_app(settings.model_copy(update={"tmdb_token": None}))
    with client_for(app) as test_client:
        test_client.post("/folders/Anel/scan", headers=SAME)
        fid = file_id(test_client)
        match = test_client.post("/folders/Anel/match", headers=SAME).text
        search = test_client.post(f"/files/{fid}/search", headers=SAME).text
        card = test_client.get(f"/files/{fid}/card").text

    assert curation.DISABLED in html.unescape(match)
    assert curation.DISABLED in html.unescape(search)
    assert "Corrigir" not in card


def test_get_tmdb_gives_a_client_only_with_a_token(settings: Settings) -> None:
    with_token = get_tmdb(settings)
    without = get_tmdb(settings.model_copy(update={"tmdb_token": None}))

    assert isinstance(next(with_token), TmdbClient)
    assert next(without) is None
    for generator in (with_token, without):
        with pytest.raises(StopIteration):
            next(generator)


def test_library_line_counts_confirmed(client: TestClient) -> None:
    fid = file_id(client)
    assert "TMDB:" not in client.get("/").text
    client.post(f"/files/{fid}/choose", headers=SAME, data={"kind": "movie", "tmdb_id": "101"})

    assert "TMDB: todos confirmados" in client.get("/").text


def test_library_line_partial(client: TestClient, settings: Settings) -> None:
    make_file(settings.media_dir / "Anel" / "Outro.mkv")
    client.post("/folders/Anel/scan", headers=SAME)
    client.post(f"/files/{file_id_of(client, 'Anel/Anel Mágico (2001).mkv')}/choose",
                headers=SAME, data={"kind": "movie", "tmdb_id": "101"})  # fmt: skip

    assert "TMDB: 1 de 2 confirmados" in client.get("/").text


def test_footer_attribution(client: TestClient) -> None:
    page = client.get("/").text

    assert "Este produto usa a API do TMDB" in page
    assert "/static/tmdb.svg" in page


def file_id_of(client: TestClient, path: str) -> int:
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        row = session.exec(select(MediaFile).where(MediaFile.path == path)).one()
        assert row.id is not None
        return row.id
