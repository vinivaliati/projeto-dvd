import html
import io
import json
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from sqlmodel import Session, select

from projeto_dvd.api import cover as cover_api
from projeto_dvd.api import library
from projeto_dvd.api.curation import DISABLED
from projeto_dvd.api.deps import get_tmdb
from projeto_dvd.api.dvd import load_disc_page
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from projeto_dvd.covers import render
from projeto_dvd.db.models import DiscProject, MediaFile, Title
from projeto_dvd.library.probe import ProbeResult
from projeto_dvd.metadata.curation import title_art_dir
from projeto_dvd.metadata.tmdb import TmdbClient
from projeto_dvd.metadata.tmdb_models import DETAILS, MovieDetails
from projeto_dvd.planner.disc_plan import DiscChoices
from tests.client import client_for
from tests.tmdb_fakes import MOVIE, router
from tests.tree import make_file
from tests.unit.test_dvd_routes import MOVIE as PROBE

SAME = {"Sec-Fetch-Site": "same-origin"}


def jpeg() -> bytes:
    data = io.BytesIO()
    Image.new("RGB", (20, 30), "navy").save(data, "JPEG")
    return data.getvalue()


ROUTES: dict[str, object] = {"/t/p/original/posterpt.jpg": jpeg(),
                             "/t/p/original/backen.jpg": b"not an image"}  # fmt: skip


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    make_file(tmp_path / "media" / "Filme" / "Filme.mkv")
    (tmp_path / "out").mkdir()
    return Settings(media_dir=tmp_path / "media", output_dir=tmp_path / "out",
                    database_url=database_url, tmdb_token=SecretStr("t"),
                    host_output_dir="/mnt/c/Users/v/dvd")  # fmt: skip


def make_client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(library, "run_ffprobe",
                        lambda path: ProbeResult(json=json.dumps(PROBE), error=None))  # fmt: skip
    monkeypatch.setattr(render, "PDF_DPI", 30)  # the real 300 DPI render runs in test_cover_render
    app = create_app(settings)

    def fake_tmdb() -> Iterator[TmdbClient]:
        transport = httpx2.MockTransport(router(ROUTES))
        with TmdbClient("t", "pt-BR", transport=transport) as tmdb:
            yield tmdb

    if settings.tmdb_token:
        app.dependency_overrides[get_tmdb] = fake_tmdb
    with client_for(app) as test_client:
        yield test_client


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from make_client(settings, monkeypatch)


def scan(client: TestClient) -> None:
    client.post("/folders/Filme/scan", headers=SAME)


def confirm(client: TestClient) -> None:
    details = DETAILS.dump_json(MovieDetails.model_validate({"kind": "movie", "movie": MOVIE}))
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        row = session.exec(select(MediaFile)).one()
        row.title = Title(status="confirmed", kind="movie", label="Anel", tmdb_id=101,
                          tmdb_json=details.decode())  # fmt: skip
        session.commit()


def saved(client: TestClient) -> DiscChoices:
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        project = session.get(DiscProject, "Filme")
        assert project is not None
        return DiscChoices.model_validate_json(project.choices_json)


@pytest.fixture
def ready(client: TestClient) -> TestClient:
    scan(client)
    confirm(client)
    return client


def test_the_folder_offers_the_cover(ready: TestClient) -> None:
    assert '/folders/Filme/cover">Capa' in ready.get("/folders/Filme").text


def test_the_page_shows_the_previews_and_the_art(ready: TestClient) -> None:
    page = html.unescape(ready.get("/folders/Filme/cover").text)

    assert "/folders/Filme/cover/preview.png?page=1&v=" in page
    assert "/folders/Filme/cover/preview.png?page=2&v=" in page
    assert "https://image.tmdb.org/t/p/w185/posterpt.jpg" in page
    assert "https://image.tmdb.org/t/p/w300/backnull2.jpg" in page
    assert "/backnull.jpg" not in page  # 1920 px wide: below 150 DPI on the front
    assert "pode ter texto" in page  # the English backdrop
    assert "abaixo de 300 DPI" in page
    assert 'placeholder="2001"' in page  # the automatic front line
    assert "sem match confirmado" not in page


def test_titles_without_a_match_are_pointed_out(client: TestClient) -> None:
    scan(client)

    page = client.get("/folders/Filme/cover").text

    assert "1 vídeo sem match confirmado" in page
    assert '/folders/Filme#tmdb">Confirmar no TMDB' in page


def test_an_unscanned_folder_goes_back(client: TestClient) -> None:
    response = client.get("/folders/Filme/cover", follow_redirects=False)

    assert (response.status_code, response.headers["location"]) == (303, "/folders/Filme")
    assert client.get("/folders/Filme/cover/preview.png?page=1").status_code == 404


def test_saving_the_texts_keeps_the_disc(ready: TestClient) -> None:
    ready.post("/folders/Filme/dvd/choices", headers=SAME, data={
        "kind": "movies", "order": ["Filme/Filme.mkv"], "profile": "dvd5", "audio": ["pt"],
        "first_audio": "pt", "chapters": "file", "minutes": "5", "accent": "auto",
        "side": "right"})  # fmt: skip

    texts = {"front_text": " Edição ", "spine_text": "", "show_name": "no"}
    response = ready.post("/folders/Filme/cover/choices", headers=SAME, data=texts)

    assert 'id="cover-preview"' in response.text and 'hx-swap-oob="true"' in response.text
    choices = saved(ready)
    assert (choices.profile, choices.theme.side) == ("dvd5", "right")
    cover = choices.cover
    assert (cover.front_text, cover.spine_text, cover.show_name) == ("Edição", None, False)


def test_a_text_too_long_is_refused(ready: TestClient) -> None:
    response = ready.post("/folders/Filme/cover/choices", headers=SAME,
                          data={"front_text": "x" * 81, "show_name": "auto"})  # fmt: skip

    assert "Formulário inválido" in response.text
    assert ready.get("/folders/Filme/cover").status_code == 200


def test_choosing_an_art_downloads_it_as_the_front(ready: TestClient, settings: Settings) -> None:
    (settings.output_dir / "covers" / "Filme").mkdir(parents=True)
    old = settings.output_dir / "covers" / "Filme" / "front.png"
    Image.new("RGB", (4, 4)).save(old)

    response = ready.post("/folders/Filme/cover/art", headers=SAME,
                          data={"file_path": "/posterpt.jpg"})  # fmt: skip

    assert response.status_code == 200
    assert (settings.output_dir / "covers" / "Filme" / "front.jpg").is_file()
    assert not old.exists()  # the chosen art is the only front
    cover = saved(ready).cover
    assert (cover.front, cover.front_language) == ("/posterpt.jpg", "pt")
    assert 'value="/posterpt.jpg" checked' in response.text


def test_the_default_front_needs_no_download(ready: TestClient) -> None:
    ready.post("/folders/Filme/cover/art", headers=SAME, data={"file_path": "/posterpt.jpg"})

    response = ready.post("/folders/Filme/cover/art", headers=SAME, data={"file_path": ""})

    assert response.status_code == 200
    assert saved(ready).cover.front is None


def test_an_art_out_of_the_options_is_refused(ready: TestClient) -> None:
    response = ready.post("/folders/Filme/cover/art", headers=SAME,
                          data={"file_path": "/backnull.jpg"})  # fmt: skip

    assert response.status_code == 400


def test_an_art_that_does_not_open_keeps_the_front(ready: TestClient, settings: Settings) -> None:
    response = ready.post("/folders/Filme/cover/art", headers=SAME,
                          data={"file_path": "/backen.jpg"})  # fmt: skip

    assert "A arte não pôde ser usada" in response.text
    assert not (settings.output_dir / "covers" / "Filme" / "front.jpg").exists()
    with Session(ready.app.state.engine) as session:  # type: ignore[attr-defined]
        assert session.get(DiscProject, "Filme") is None


def test_without_a_token_choosing_art_asks_for_it(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    for client in make_client(settings.model_copy(update={"tmdb_token": None}), monkeypatch):
        scan(client)
        confirm(client)
        page = client.get("/folders/Filme/cover").text
        assert "/posterpt.jpg" in page

        response = client.post("/folders/Filme/cover/art", headers=SAME,
                               data={"file_path": "/posterpt.jpg"})  # fmt: skip

        assert DISABLED in html.unescape(response.text)


@pytest.mark.parametrize(("page", "size"), [(1, (585, 413)), (2, (413, 585))])
def test_previews(ready: TestClient, page: int, size: tuple[int, int]) -> None:
    response = ready.get(f"/folders/Filme/cover/preview.png?page={page}")

    assert response.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(response.content)).size == size


def test_a_preview_page_that_does_not_exist(ready: TestClient) -> None:
    assert ready.get("/folders/Filme/cover/preview.png?page=3").status_code == 404


def test_the_pdf_is_written_to_print(ready: TestClient, settings: Settings) -> None:
    response = ready.post("/folders/Filme/cover/pdf", headers=SAME)

    assert (settings.output_dir / "print" / "Filme.pdf").read_bytes().startswith(b"%PDF")
    assert "C:\\Users\\v\\dvd\\print\\Filme.pdf" in html.unescape(response.text)


def test_a_pdf_open_in_windows_asks_to_close_it(
    ready: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: Path, target: Path) -> Path:
        raise PermissionError(13, "in use")

    monkeypatch.setattr(Path, "replace", refuse)

    response = ready.post("/folders/Filme/cover/pdf", headers=SAME)

    assert "Feche o PDF aberto e tente de novo." in response.text
    assert list((settings.output_dir / "print").iterdir()) == []


def test_an_output_folder_that_cannot_be_written(ready: TestClient, settings: Settings) -> None:
    (settings.output_dir / "print").write_text("a file where the folder should be")

    response = ready.post("/folders/Filme/cover/pdf", headers=SAME)

    assert "Não dá para gravar na pasta de saída" in response.text


def test_a_post_from_another_site_is_refused(ready: TestClient) -> None:
    headers = {"Sec-Fetch-Site": "cross-site"}

    assert ready.post("/folders/Filme/cover/pdf", headers=headers).status_code == 403


def test_a_print_folder_without_permission(ready: TestClient, settings: Settings) -> None:
    (settings.output_dir / "print").mkdir()
    (settings.output_dir / "print").chmod(0o555)
    try:
        response = ready.post("/folders/Filme/cover/pdf", headers=SAME)
    finally:
        (settings.output_dir / "print").chmod(0o755)

    assert "Não dá para gravar na pasta de saída" in response.text


def test_a_full_disk_while_writing_the_pdf(
    ready: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(*args: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(render, "write_pdf", full)

    assert "Não dá para gravar" in ready.post("/folders/Filme/cover/pdf", headers=SAME).text


def test_an_art_that_is_not_jpeg_or_png(ready: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    gif = io.BytesIO()
    Image.new("RGB", (4, 4)).save(gif, "GIF")
    monkeypatch.setitem(ROUTES, "/t/p/original/posterpt.jpg", gif.getvalue())

    response = ready.post("/folders/Filme/cover/art", headers=SAME,
                          data={"file_path": "/posterpt.jpg"})  # fmt: skip

    assert "A arte não pôde ser usada" in response.text


def test_an_art_folder_that_cannot_be_written(ready: TestClient, settings: Settings) -> None:
    make_file(settings.output_dir / "covers" / "Filme")  # a file where the folder goes

    response = ready.post("/folders/Filme/cover/art", headers=SAME,
                          data={"file_path": "/posterpt.jpg"})  # fmt: skip

    assert "Não dá para gravar na pasta de saída" in html.unescape(response.text)


def built(client: TestClient, settings: Settings) -> cover_api.Cover:
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        folder = settings.media_dir / "Filme"
        disc = load_disc_page(session, settings.media_dir, settings, "Filme", folder)
        assert disc is not None
        return cover_api.build_cover(session, settings, disc)


def test_the_name_goes_over_the_default_poster_only_without_a_language(
    ready: TestClient, settings: Settings
) -> None:
    assert built(ready, settings).show_name  # no poster yet: the neutral front gets the name
    details = DETAILS.validate_python({"kind": "movie", "movie": MOVIE})
    poster = title_art_dir(settings.output_dir, "Filme", details) / "poster.jpg"
    make_file(poster, jpeg())

    assert not built(ready, settings).show_name  # "/posterpt.jpg" is a "pt" poster
    with Session(ready.app.state.engine) as session:  # type: ignore[attr-defined]
        row = session.exec(select(MediaFile)).one()
        assert row.title is not None
        textless = {**MOVIE, "images": {"posters": [{"file_path": "/posterpt.jpg"}]}}
        row.title.tmdb_json = DETAILS.dump_json(
            MovieDetails.model_validate({"kind": "movie", "movie": textless})).decode()  # fmt: skip
        session.add(row.title)
        session.commit()
    assert built(ready, settings).show_name


def test_a_chosen_backdrop_gets_the_name_and_a_chosen_poster_does_not(
    ready: TestClient, settings: Settings
) -> None:
    ready.post("/folders/Filme/cover/art", headers=SAME, data={"file_path": "/posterpt.jpg"})
    assert not built(ready, settings).show_name

    jpg = settings.output_dir / "covers" / "Filme" / "front.jpg"
    choices = saved(ready).model_copy(update={"cover": saved(ready).cover.model_copy(
        update={"front": "/backen.jpg", "front_language": "en"})})  # fmt: skip
    with Session(ready.app.state.engine) as session:  # type: ignore[attr-defined]
        project = session.get(DiscProject, "Filme")
        assert project is not None and jpg.exists()
        project.choices_json = choices.model_dump_json()
        session.commit()
    assert built(ready, settings).show_name
