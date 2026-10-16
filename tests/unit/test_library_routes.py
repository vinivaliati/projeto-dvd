import html
import json
import re
import shutil
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from projeto_dvd.api import library
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from projeto_dvd.db.models import MediaFile
from projeto_dvd.library.probe import ABOVE_1080P, HDR, FfprobeMissingError, ProbeResult
from tests.client import client_for
from tests.tree import make_file, snapshot

MOVIE_JSON = json.dumps(
    {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 800,
                "avg_frame_rate": "24000/1001",
                "display_aspect_ratio": "12:5",
            },
            {
                "codec_type": "audio",
                "codec_name": "ac3",
                "channel_layout": "5.1(side)",
                "tags": {"language": "por"},
            },
            {"codec_type": "audio", "codec_name": "aac", "channel_layout": "stereo"},
            {
                "codec_type": "subtitle",
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "por"},
                "disposition": {"forced": 1},
            },
        ],
        "format": {"duration": "10680.0"},
        "chapters": [{}, {}, {}],
    }
)

UHD_HDR_JSON = json.dumps(
    {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "avg_frame_rate": "24000/1001",
                "color_transfer": "smpte2084",
            }
        ],
        "format": {"duration": "7200.0"},
    }
)


@pytest.fixture
def media(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    make_file(root / "Senhor dos Aneis" / "A Sociedade do Anel.mkv", b"x" * 2000)
    make_file(root / "Senhor dos Aneis" / "A Sociedade do Anel.pt-BR.srt")
    return root


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake(path: Path) -> ProbeResult:
        calls.append(path.name)
        if path.name.startswith("ruim"):
            error = (
                f"[matroska,webm @ 0x5945] EBML header parsing failed\n{path}: Invalid data found"
            )
            return ProbeResult(json=None, error=error)
        if path.name.startswith("uhd"):
            return ProbeResult(json=UHD_HDR_JSON, error=None)
        return ProbeResult(json=MOVIE_JSON, error=None)

    monkeypatch.setattr(library, "run_ffprobe", fake)
    return calls


@pytest.fixture
def client(media: Path, database_url: str) -> Iterator[TestClient]:
    with client_for(create_app(Settings(media_dir=media, database_url=database_url))) as client:
        yield client


def folder_url(name: str) -> str:
    return f"/folders/{quote(name)}"


# Library page


def test_library_lists_disc_folders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Senhor dos Aneis" in response.text
    assert "1 vídeo" in response.text
    assert "2 KB" in response.text
    assert "não escaneada" in response.text
    assert "escaneie para ver" in response.text


def test_library_shows_duration_after_scan(client: TestClient, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")

    response = client.get("/")

    assert "2h58" in response.text
    assert "escaneie para ver" not in response.text


def test_library_without_folders_shows_help(tmp_path: Path, database_url: str) -> None:
    app = create_app(Settings(media_dir=tmp_path / "vazio", database_url=database_url))
    with client_for(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "HOST_MEDIA_DIR" in response.text
    assert "HD externo" in response.text  # a drive connected late is a common cause
    assert "VIDEO_TS" in response.text  # disc folders are not read: one video file per title


def test_empty_folder_card_does_not_ask_for_a_scan(tmp_path: Path, database_url: str) -> None:
    (tmp_path / "Vazia").mkdir()
    with client_for(create_app(Settings(media_dir=tmp_path, database_url=database_url))) as client:
        response = client.get("/")

    assert "vazia" in response.text
    assert "escaneie para ver" not in response.text


def test_library_purges_rows_of_removed_folders(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    make_file(media / "Outra" / "a.mkv")  # with no folder at all, nothing is purged
    for file in (media / "Senhor dos Aneis").iterdir():
        file.unlink()
    (media / "Senhor dos Aneis").rmdir()
    client.get("/")
    make_file(media / "Senhor dos Aneis" / "A Sociedade do Anel.mkv", b"x" * 2000)

    response = client.get("/")

    assert "não escaneada" in response.text  # the old row is gone, not "mudou"


def test_folder_with_special_characters_opens_from_library_link(
    client: TestClient, media: Path
) -> None:
    make_file(media / "Ação #1? 100%" / "Filme.mkv")

    library_page = client.get("/").text
    links = re.findall(r'href="([^"]*/folders/[^"]*)"', library_page)
    link = next(link for link in links if "A%C3%A7%C3%A3o" in link)
    response = client.get(link)

    assert response.status_code == 200
    assert "Ação #1? 100%" in response.text
    scan_url = html.unescape(re.search(r'hx-post="([^"]*)"', response.text).group(1))  # type: ignore[union-attr]
    assert client.post(scan_url).status_code == 200


# Folder page


def test_folder_page_before_scan(client: TestClient) -> None:
    response = client.get(folder_url("Senhor dos Aneis"))

    assert response.status_code == 200
    assert "ainda não foi escaneada" in response.text
    assert 'hx-post="' in response.text
    assert 'hx-disabled-elt="this"' in response.text
    assert 'hx-sync="this:drop"' in response.text
    assert 'hx-target="#folder-body"' in response.text
    assert 'hx-swap="innerHTML"' in response.text
    assert '<div id="folder-body">' in response.text


def test_folder_created_in_nfd_opens_by_its_nfc_url(client: TestClient, media: Path) -> None:
    make_file(media / unicodedata.normalize("NFD", "Coração") / "a.mkv")

    response = client.get(folder_url("Coração"))

    assert response.status_code == 200


def test_scan_returns_the_table_fragment(client: TestClient, probes: list[str]) -> None:
    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert response.status_code == 200
    assert "<html" not in response.text
    assert probes == ["A Sociedade do Anel.mkv"]
    text = response.text
    assert "Scan concluído: 1 arquivo lido pelo ffprobe." in text
    assert "1080p · H.264 · 23,976" in text
    assert "2,40:1" in text
    assert "por 5.1" in text and "não definido estéreo" in text
    assert "2 (1 imagem)" in text  # PGS inside + external .srt
    assert "pt-BR" in text  # external subtitle in the details
    assert "hdmv_pgs_subtitle" in text and "forçada" in text  # track details
    assert "2h58" in text


def test_second_scan_reports_nothing_read(client: TestClient, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert "Scan concluído: 0 arquivos lidos pelo ffprobe." in response.text
    assert probes == ["A Sociedade do Anel.mkv"]


def test_folder_page_after_scan_shows_the_table(client: TestClient, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")

    response = client.get(folder_url("Senhor dos Aneis"))

    assert "1080p · H.264 · 23,976" in response.text
    assert "Scan concluído" not in response.text


def test_unreadable_file_is_shown_with_its_error(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    make_file(media / "Senhor dos Aneis" / "ruim.mkv")

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert "Não foi possível ler o arquivo" in response.text
    assert "Invalid data found" in response.text
    assert str(media) not in response.text  # the name is in the first column already
    assert "0x5945" not in response.text  # only the last line of stderr
    assert "1 arquivo com aviso" in response.text


def test_changed_files_are_announced(client: TestClient, media: Path, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    make_file(media / "Senhor dos Aneis" / "As Duas Torres.mkv")

    response = client.get(folder_url("Senhor dos Aneis"))

    assert "Arquivos mudaram desde o último scan" in response.text
    assert "ainda não escaneado" in response.text
    assert "1080p · H.264" in response.text  # the old file keeps its data
    # The size of the new file sits under "Tamanho", not under "Duração".
    assert re.search(r"As Duas Torres.mkv</td>\s*<td></td>\s*<td class=\"numbers\">", response.text)


def test_missing_ffprobe_shows_one_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(path: Path) -> ProbeResult:
        raise FfprobeMissingError

    monkeypatch.setattr(library, "run_ffprobe", missing)

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert response.status_code == 200
    assert "ffprobe não foi encontrado" in response.text
    assert "Não foi possível ler o arquivo" not in response.text
    assert "Scan concluído" not in response.text


def test_scan_while_another_is_running_reports_it(client: TestClient, probes: list[str]) -> None:
    assert library._scan_lock.acquire(blocking=False)
    try:
        response = client.post(folder_url("Senhor dos Aneis") + "/scan")
    finally:
        library._scan_lock.release()

    assert "Já existe um scan em andamento" in response.text
    assert "Scan concluído" not in response.text
    assert probes == []


def test_lock_is_released_after_an_unexpected_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(path: Path) -> ProbeResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(library, "run_ffprobe", boom)
    with pytest.raises(RuntimeError):
        client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert not library._scan_lock.locked()


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "name",
    ["%2E%2E", "a%2Fb", "nao-existe", "solto.mkv", "link", "Senhor%20dos%20aneis"],
)
def test_unknown_folders_are_404(
    client: TestClient, media: Path, tmp_path: Path, method: str, name: str
) -> None:
    make_file(media / "solto.mkv")
    (tmp_path / "fora").mkdir()
    (media / "link").symlink_to(tmp_path / "fora", target_is_directory=True)
    url = f"/folders/{name}" + ("/scan" if method == "POST" else "")

    assert client.request(method, url).status_code == 404


def test_routes_never_write_to_the_media_folder(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    before = snapshot(media)

    client.get("/")
    client.get(folder_url("Senhor dos Aneis"))
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    client.get(folder_url("Senhor dos Aneis"))

    assert snapshot(media) == before


def test_image_subtitles_are_counted_in_the_plural(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    make_file(media / "Senhor dos Aneis" / "A Sociedade do Anel.en.sup")

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert "3 (2 imagens)" in response.text


def test_pages_during_a_scan_say_it_is_running(
    client: TestClient, media: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_file(media / "Senhor dos Aneis" / "As Duas Torres.mkv")
    pages: list[str] = []

    def slow(path: Path) -> ProbeResult:
        # Halfway: one file has its row, the other not yet.
        if path.name == "As Duas Torres.mkv":
            pages.append(client.get("/").text)
            pages.append(client.get(folder_url("Senhor dos Aneis")).text)
            pages.append(client.post(folder_url("Senhor dos Aneis") + "/scan").text)
        return ProbeResult(json=MOVIE_JSON, error=None)

    monkeypatch.setattr(library, "run_ffprobe", slow)
    after = client.post(folder_url("Senhor dos Aneis") + "/scan").text

    library_page, folder_page, refused_scan = pages
    assert "escaneando" in library_page and ">mudou<" not in library_page
    assert "Um scan desta pasta está em andamento" in folder_page
    assert "Arquivos mudaram" not in folder_page
    assert "Já existe um scan em andamento" in refused_scan
    assert "Arquivos mudaram" not in refused_scan
    assert "em andamento" not in after


def test_a_failed_scan_request_shows_a_message(client: TestClient) -> None:
    response = client.get(folder_url("Senhor dos Aneis"))

    # HTMX 2 does not swap 4xx/5xx responses: without this the page would just go quiet.
    assert "hx-on::response-error" in response.text
    assert "hx-on::send-error" in response.text
    assert "O scan falhou" in response.text


@pytest.mark.parametrize("name", ["Vazia", "SoLegendas"])
def test_folders_without_videos_are_empty(client: TestClient, media: Path, name: str) -> None:
    (media / "Vazia").mkdir()
    make_file(media / "SoLegendas" / "a.srt")

    page = client.get(folder_url(name)).text
    card = client.get("/").text.split(f">{name}<", 1)[1].split("</li>", 1)[0]

    assert "Nenhum vídeo nesta pasta." in page
    assert "VIDEO_TS" in page  # a copied DVD folder lands here: say why
    assert "<table" not in page
    assert "badge-empty" in card


def test_hdr_and_above_1080p_are_flagged(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    make_file(media / "Senhor dos Aneis" / "uhd.mkv")

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert "2160p · HEVC" in response.text
    assert ">HDR</span>" in response.text
    for warning in (HDR, ABOVE_1080P):  # listed in the details, not only in the icon title
        assert f"</span> {warning}</li>" in response.text
    assert 'class="warning-icon"' in response.text
    assert "1 arquivo com aviso" in response.text


def test_library_without_drive_keeps_the_rows(
    client: TestClient, probes: list[str], media: Path
) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    shutil.rmtree(media)  # the drive is unplugged: /media is empty

    client.get("/")

    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        assert len(session.exec(select(MediaFile)).all()) == 1


def test_library_purges_a_removed_folder_when_others_exist(
    client: TestClient, probes: list[str], media: Path
) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    make_file(media / "Outra" / "a.mkv")
    shutil.rmtree(media / "Senhor dos Aneis")

    client.get("/")

    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        assert session.exec(select(MediaFile)).all() == []
