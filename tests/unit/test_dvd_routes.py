import html
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from projeto_dvd.api import dvd, library
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from projeto_dvd.jobs import pipeline, store
from projeto_dvd.library.probe import ProbeResult
from projeto_dvd.planner.dvd_plan import DvdPlan
from tests.client import client_for
from tests.tree import make_file

SAME = {"Sec-Fetch-Site": "same-origin"}
MOVIE = {
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 800,
            "r_frame_rate": "24000/1001",
            "avg_frame_rate": "24000/1001",
            "display_aspect_ratio": "12:5",
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "dts",
            "channels": 6,
            "sample_rate": "48000",
            "tags": {"language": "eng"},
        },
        {
            "index": 2,
            "codec_type": "audio",
            "codec_name": "ac3",
            "channels": 6,
            "sample_rate": "48000",
            "bit_rate": "448000",
            "tags": {"language": "por"},
        },
        {"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "por"}},
        {
            "index": 4,
            "codec_type": "subtitle",
            "codec_name": "hdmv_pgs_subtitle",
            "tags": {"language": "eng"},
        },
    ],
    "format": {"duration": "7200.0"},
    "chapters": [{"start_time": "0"}, {"start_time": "600"}],
}


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    media = tmp_path / "media"
    make_file(media / "Filme" / "Filme.mkv", b"x" * 100)
    make_file(media / "Dois" / "a.mkv")
    make_file(media / "Dois" / "b.mkv")
    (tmp_path / "work").mkdir()
    (tmp_path / "out").mkdir()
    return Settings(
        media_dir=media,
        work_dir=tmp_path / "work",
        output_dir=tmp_path / "out",
        database_url=database_url,
    )


@pytest.fixture
def probe_data() -> dict[str, object]:
    copy: dict[str, object] = json.loads(json.dumps(MOVIE))  # a copy each test can change
    return copy


@pytest.fixture
def client(
    settings: Settings, probe_data: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(
        library, "run_ffprobe", lambda path: ProbeResult(json=json.dumps(probe_data), error=None)
    )
    usage = shutil.disk_usage(settings.work_dir)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage._replace(free=100 * 10**9))
    with client_for(create_app(settings)) as client:
        yield client


def scan(client: TestClient, name: str = "Filme") -> str:
    return client.post(f"/folders/{quote(name)}/scan", headers=SAME).text


def form_data(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "profile": "dvd9",
        "audio": ["1", "2"],
        "first_audio": "2",
        "subtitle": ["s3"],
        "subtitle_on": "",
        "chapters": "file",
        "minutes": "5",
    }
    data.update(changes)
    return data


def test_folder_offers_generate_after_the_scan(client: TestClient) -> None:
    body = scan(client)

    assert "Gerar DVD" in body
    assert '/folders/Filme/dvd">Gerar DVD' in body


def test_folder_with_two_videos_explains(client: TestClient) -> None:
    body = scan(client, "Dois")

    assert "Não dá para gerar o DVD desta pasta" in body
    assert "vídeo só" in body


def test_unscanned_folder_asks_for_a_scan(client: TestClient) -> None:
    assert "Escaneie a pasta antes de gerar o disco." in client.get("/folders/Filme").text


def test_form_shows_the_suggestions(client: TestClient) -> None:
    scan(client)

    page = client.get("/folders/Filme/dvd")

    assert page.status_code == 200
    assert "Entrada: 1080p, 23,976 quadros/s, 2h00" in page.text
    assert "faixas pretas" in page.text
    assert 'name="first_audio" value="2" checked' in page.text  # Portuguese plays first
    assert "copiar sem perda" in page.text and "converter para Dolby Digital 5.1" in page.text
    assert "Legenda em imagem (PGS): ainda não suportada" in page.text
    assert "sugerido" in page.text and "Ótima" in page.text and "Aceitável" in page.text


def test_form_of_a_refused_folder_goes_back(client: TestClient) -> None:
    scan(client, "Dois")

    response = client.get("/folders/Dois/dvd", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/folders/Dois"


def test_estimate_updates_the_cards(client: TestClient) -> None:
    scan(client)

    response = client.post(
        "/folders/Filme/dvd/estimate",
        headers=SAME,
        data=form_data(audio=["1", "2"], profile="dvd5"),
    )

    assert response.status_code == 200
    assert "<html" not in response.text
    assert "Baixa" in response.text or "Aceitável" in response.text
    assert 'value="dvd5" checked' in response.text


def test_create_queues_a_job_and_redirects(client: TestClient) -> None:
    scan(client)

    response = client.post(
        "/folders/Filme/dvd", headers=SAME, data=form_data(), follow_redirects=False
    )

    assert response.status_code == 303
    job_url = response.headers["location"]
    assert job_url.startswith("/jobs/")
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        job = store.get_job(session, int(job_url.rsplit("/", 1)[1]))
        assert job is not None
        plan = DvdPlan.model_validate_json(job.plan_json)
    assert [a.index for a in plan.audio] == [2, 1]
    assert plan.chapters == (0.0, 600.0)


def test_second_click_goes_to_the_same_job(client: TestClient) -> None:
    scan(client)
    first = client.post(
        "/folders/Filme/dvd", headers=SAME, data=form_data(), follow_redirects=False
    )

    again = client.post(
        "/folders/Filme/dvd", headers=SAME, data=form_data(), follow_redirects=False
    )
    form = client.get("/folders/Filme/dvd", follow_redirects=False)

    assert again.headers["location"] == first.headers["location"]
    assert form.headers["location"] == first.headers["location"]
    assert "Gerando DVD" in client.get("/folders/Filme").text
    assert "gerando DVD" in client.get("/").text


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"audio": []}, "Escolha ao menos uma faixa de áudio."),
        ({"first_audio": "9"}, "A faixa que toca ao colocar o disco precisa estar marcada."),
        ({"subtitle_on": "s4"}, "A legenda ligada ao iniciar precisa estar marcada."),
        (
            {"chapters": "every", "minutes": "0"},
            "O intervalo dos capítulos precisa ser de 1 minuto ou mais.",
        ),
        ({"minutes": "abc"}, "Formulário inválido. Recarregue a página."),
    ],
)
def test_validation_errors_keep_the_form(
    client: TestClient, changes: dict[str, object], message: str
) -> None:
    scan(client)

    response = client.post("/folders/Filme/dvd", headers=SAME, data=form_data(**changes))

    assert response.status_code == 200
    assert message in response.text
    assert 'aria-invalid="true"' in response.text or "Formulário inválido" in message


def test_low_quality_needs_the_checkbox(client: TestClient, probe_data: dict[str, object]) -> None:
    probe_data["format"] = {"duration": "25000"}  # about 7 h: "Baixa" on a DVD-9
    scan(client)

    refused = client.post("/folders/Filme/dvd", headers=SAME, data=form_data())
    accepted = client.post(
        "/folders/Filme/dvd", headers=SAME, data=form_data(confirm_low="1"), follow_redirects=False
    )

    assert "Confirme que quer gerar com qualidade baixa." in refused.text
    assert "Entendo que a qualidade vai ficar baixa" in refused.text
    assert accepted.status_code == 303


def test_existing_iso_needs_confirmation(client: TestClient, settings: Settings) -> None:
    make_file(settings.output_dir / "iso" / "Filme.iso", b"x" * 1000)
    scan(client)

    page = client.get("/folders/Filme/dvd")
    refused = client.post("/folders/Filme/dvd", headers=SAME, data=form_data())
    accepted = client.post(
        "/folders/Filme/dvd", headers=SAME, data=form_data(replace_iso="1"), follow_redirects=False
    )

    assert "Substituir o ISO existente" in page.text
    assert pipeline.ISO_EXISTS_FORM in html.unescape(refused.text)
    assert accepted.status_code == 303


def test_mpeg2_rip_is_classified_by_its_frames(
    client: TestClient, probe_data: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    streams = probe_data["streams"]
    assert isinstance(streams, list)
    streams[0].update(
        codec_name="mpeg2video",
        width=720,
        height=480,
        r_frame_rate="179/6",
        display_aspect_ratio="16:9",
    )
    frames = [
        {"repeat_pict": r, "interlaced_frame": 0, "top_field_first": 1} for r in (1, 0, 1, 0) * 30
    ]
    calls: list[list[str]] = []

    def capture(command: list[str]) -> str:
        calls.append(command)
        return json.dumps({"frames": frames})

    monkeypatch.setattr(dvd, "run_capture", capture)
    scan(client)

    client.get("/folders/Filme/dvd")
    client.post("/folders/Filme/dvd/estimate", headers=SAME, data=form_data())

    assert len(calls) == 1  # cached between the form and the estimate


def test_cross_site_create_is_refused(client: TestClient) -> None:
    scan(client)

    response = client.post(
        "/folders/Filme/dvd", headers={"Sec-Fetch-Site": "cross-site"}, data=form_data()
    )

    assert response.status_code == 403


def test_regenerate_link_points_to_the_form(client: TestClient) -> None:
    scan(client)
    location = client.post(
        "/folders/Filme/dvd", headers=SAME, data=form_data(), follow_redirects=False
    ).headers["location"]
    client.post(location + "/cancel", headers=SAME)

    assert '/folders/Filme/dvd">Gerar de novo' in client.get(location).text


def test_estimate_with_a_broken_form(client: TestClient) -> None:
    scan(client)

    response = client.post("/folders/Filme/dvd/estimate", headers=SAME, data={"minutes": "x"})

    assert "Formulário inválido" in response.text


def test_create_on_a_refused_folder_goes_back(client: TestClient) -> None:
    scan(client, "Dois")

    response = client.post("/folders/Dois/dvd", headers=SAME, data=form_data(),
                           follow_redirects=False)  # fmt: skip

    assert response.headers["location"] == "/folders/Dois"


def test_job_created_by_another_click_in_between(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan(client)

    def busy(session: Session, plan: DvdPlan) -> int:
        raise store.ActiveJobError(7)

    monkeypatch.setattr(store, "enqueue", busy)
    response = client.post("/folders/Filme/dvd", headers=SAME, data=form_data(),
                           follow_redirects=False)  # fmt: skip

    assert response.headers["location"] == "/jobs/7"
