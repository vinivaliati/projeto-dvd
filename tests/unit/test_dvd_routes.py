import html
import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from projeto_dvd.api import dvd, library
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from projeto_dvd.db.models import DiscProject, MediaFile, Title
from projeto_dvd.jobs import pipeline, store
from projeto_dvd.library.probe import ProbeResult
from projeto_dvd.metadata.tmdb_models import DETAILS, Movie, MovieDetails
from projeto_dvd.planner.disc_plan import DiscChoices, DiscPlan
from tests.client import client_for
from tests.tmdb_fakes import MOVIE as TMDB_MOVIE
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


def disc_form(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "kind": "movies", "order": ["Filme/Filme.mkv"], "profile": "dvd9",
        "audio": ["pt", "en"], "first_audio": "pt", "subtitle": ["pt"], "subtitle_on": "",
        "chapters": "file", "minutes": "5", "backdrop": "", "accent": "auto", "side": "left",
        "preview_page": "0",
    }  # fmt: skip
    data.update(changes)
    return data


def saved(client: TestClient, name: str = "Filme") -> DiscChoices | None:
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        project = session.get(DiscProject, name)
        return DiscChoices.model_validate_json(project.choices_json) if project else None


def queued_plan(client: TestClient, location: str) -> DiscPlan:
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        job = store.get_job(session, int(location.rsplit("/", 1)[1]))
        assert job is not None
        return DiscPlan.model_validate_json(job.plan_json)


def test_folder_offers_the_disc_builder_after_the_scan(client: TestClient) -> None:
    assert '/folders/Filme/dvd">Montar DVD' in scan(client)


def test_a_folder_with_several_videos_can_become_a_disc(client: TestClient) -> None:
    assert '/folders/Dois/dvd">Montar DVD' in scan(client, "Dois")


def test_unscanned_folder_asks_for_a_scan(client: TestClient) -> None:
    assert "Escaneie a pasta antes de gerar o disco." in client.get("/folders/Filme").text


def test_unscanned_folder_form_goes_back(client: TestClient) -> None:
    response = client.get("/folders/Filme/dvd", follow_redirects=False)

    assert (response.status_code, response.headers["location"]) == (303, "/folders/Filme")


def test_page_shows_the_suggestions_without_saving(client: TestClient) -> None:
    scan(client)

    page = client.get("/folders/Filme/dvd")

    assert page.status_code == 200
    text = html.unescape(page.text)
    assert "Montar DVD de" in text and "1080p, 23,976 quadros/s" in text
    assert 'name="first_audio" value="pt" checked' in text  # Portuguese plays first
    assert 'name="audio" value="en" checked' in text and "Inglês" in text
    assert "/folders/Filme/dvd/menu.png?page=0&v=" in text
    assert "sugerido" in text and "Ótima" in text
    assert "A geração leva cerca de 24 min" in text
    assert saved(client) is None


def test_choices_are_saved_and_the_results_come_back(client: TestClient) -> None:
    scan(client)

    form = disc_form(profile="dvd5", accent="verde", confirm_low="1")
    response = client.post("/folders/Filme/dvd/choices", headers=SAME, data=form)

    assert response.status_code == 200 and "<html" not in response.text
    for block in ("disc-warnings", "menu-preview", "profiles", "disc-bar", "disc-confirm"):
        assert f'id="{block}"' in response.text
    assert 'hx-swap-oob="true"' in response.text
    assert 'id="disc-titles"' not in response.text  # the order did not change
    choices = saved(client)
    assert choices is not None
    assert (choices.profile, choices.theme.accent) == ("dvd5", "verde")
    assert "confirm" not in choices.model_dump_json()
    assert 'value="dvd5" checked' in client.get("/folders/Filme/dvd").text


def test_moving_a_title_changes_the_order(client: TestClient) -> None:
    scan(client, "Dois")
    form = disc_form(order=["Dois/a.mkv", "Dois/b.mkv"], move="1:up")

    response = client.post("/folders/Dois/dvd/choices", headers=SAME, data=form)

    assert 'id="disc-titles"' in response.text
    choices = saved(client, "Dois")
    assert choices is not None and choices.order == ("Dois/b.mkv", "Dois/a.mkv")


@pytest.mark.parametrize(
    "changes",
    [
        {"order": ["Filme/Outro.mkv"]},
        {"move": "x:up"},
        {"kind": "documentary"},
        {"minutes": "abc"},
    ],
)
def test_a_form_that_does_not_fit_the_folder_is_refused(
    client: TestClient, changes: dict[str, object]
) -> None:
    scan(client)

    response = client.post("/folders/Filme/dvd/choices", headers=SAME, data=disc_form(**changes))

    assert "Formulário inválido" in response.text
    assert saved(client) is None


def test_a_move_past_the_ends_changes_nothing(client: TestClient) -> None:
    scan(client, "Dois")
    form = disc_form(order=["Dois/a.mkv", "Dois/b.mkv"], move="0:up")

    client.post("/folders/Dois/dvd/choices", headers=SAME, data=form)

    choices = saved(client, "Dois")
    assert choices is not None and choices.order == ("Dois/a.mkv", "Dois/b.mkv")


def test_a_forged_backdrop_is_ignored(client: TestClient) -> None:
    scan(client)

    client.post("/folders/Filme/dvd/choices", headers=SAME,
                data=disc_form(backdrop="../../../etc/passwd"))  # fmt: skip

    choices = saved(client)
    assert choices is not None and choices.theme.backdrop is None


def test_an_available_backdrop_is_kept(client: TestClient, settings: Settings) -> None:
    path = settings.output_dir / "covers" / "Filme" / "Filme (2001)" / "backdrop.jpg"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 36), (30, 60, 200)).save(path)
    scan(client)

    client.post("/folders/Filme/dvd/choices", headers=SAME,
                data=disc_form(backdrop="Filme (2001)"))  # fmt: skip
    page = client.get("/folders/Filme/dvd").text

    choices = saved(client)
    assert choices is not None and choices.theme.backdrop == "Filme (2001)"
    assert 'value="Filme (2001)" checked' in page and "do fundo" in page


def test_a_saved_project_that_no_longer_validates_opens_with_the_suggestion(
    client: TestClient,
) -> None:
    scan(client)
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        session.add(DiscProject(folder="Filme", choices_json='{"kind": "x"}'))
        session.commit()

    page = client.get("/folders/Filme/dvd")

    assert page.status_code == 200 and 'name="first_audio" value="pt" checked' in page.text


def test_the_preview_is_a_png(client: TestClient) -> None:
    scan(client)

    image = client.get("/folders/Filme/dvd/menu.png?page=0&v=1")
    missing = client.get("/folders/Filme/dvd/menu.png?page=99")
    unscanned = client.get("/folders/Dois/dvd/menu.png")

    assert (image.status_code, image.headers["content-type"]) == (200, "image/png")
    assert image.headers["cache-control"] == "no-cache"
    assert image.content.startswith(b"\x89PNG")
    assert (missing.status_code, unscanned.status_code) == (404, 404)


def test_create_queues_a_disc_and_redirects(client: TestClient) -> None:
    scan(client, "Dois")
    form = disc_form(order=["Dois/b.mkv", "Dois/a.mkv"])

    response = client.post("/folders/Dois/dvd", headers=SAME, data=form, follow_redirects=False)

    assert response.status_code == 303
    plan = queued_plan(client, response.headers["location"])
    assert [t.path for t in plan.titles] == ["Dois/b.mkv", "Dois/a.mkv"]
    assert plan.menu is not None and plan.menu.pages[0].kind == "main"
    assert [a.index for a in plan.titles[0].audio] == [2, 1]  # Portuguese first
    assert plan.titles[0].chapters == (0.0, 600.0)


def test_second_click_goes_to_the_same_job(client: TestClient) -> None:
    scan(client)
    first = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form(),
                        follow_redirects=False)  # fmt: skip

    again = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form(),
                        follow_redirects=False)  # fmt: skip
    form = client.get("/folders/Filme/dvd", follow_redirects=False)
    still_saving = client.post("/folders/Filme/dvd/choices", headers=SAME,
                               data=disc_form(side="right"))  # fmt: skip

    assert again.headers["location"] == first.headers["location"]
    assert form.headers["location"] == first.headers["location"]
    assert still_saving.status_code == 200
    assert "Gerando DVD" in client.get("/folders/Filme").text


def test_create_with_errors_keeps_the_page(client: TestClient) -> None:
    scan(client)

    response = client.post(
        "/folders/Filme/dvd", headers=SAME, data=disc_form(audio=[], first_audio="")
    )
    broken = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form(minutes="abc"))

    assert "Escolha ao menos um idioma de áudio." in response.text
    assert "Formulário inválido" in broken.text


def test_low_quality_needs_the_checkbox_every_time(
    client: TestClient, probe_data: dict[str, object]
) -> None:
    probe_data["format"] = {"duration": "25000"}  # about 7 h: "Baixa" on a DVD-9
    scan(client)

    refused = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form())
    accepted = client.post("/folders/Filme/dvd", headers=SAME,
                           data=disc_form(confirm_low="1"), follow_redirects=False)  # fmt: skip

    assert "Confirme que quer gerar com qualidade baixa." in refused.text
    assert "Entendo que a qualidade vai ficar baixa" in refused.text
    assert accepted.status_code == 303


def test_existing_iso_needs_confirmation(client: TestClient, settings: Settings) -> None:
    make_file(settings.output_dir / "iso" / "Filme.iso", b"x" * 1000)
    scan(client)

    page = client.get("/folders/Filme/dvd")
    refused = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form())
    accepted = client.post("/folders/Filme/dvd", headers=SAME,
                           data=disc_form(replace_iso="1"), follow_redirects=False)  # fmt: skip

    assert "Substituir o ISO existente" in page.text
    assert pipeline.ISO_EXISTS_FORM in html.unescape(refused.text)
    assert accepted.status_code == 303


def test_mpeg2_rips_are_classified_only_when_generating(
    client: TestClient, probe_data: dict[str, object], monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:  # fmt: skip
    streams = probe_data["streams"]
    assert isinstance(streams, list)
    streams[0].update(codec_name="mpeg2video", width=720, height=480, r_frame_rate="179/6",
                      display_aspect_ratio="16:9")  # fmt: skip
    frames = [{"repeat_pict": r, "interlaced_frame": 0, "top_field_first": 1}
              for r in (1, 0, 1, 0) * 30]  # fmt: skip
    calls: list[list[str]] = []

    def capture(command: list[str]) -> str:
        calls.append(command)
        return json.dumps({"frames": frames})

    monkeypatch.setattr(dvd, "run_capture", capture)
    scan(client)

    client.get("/folders/Filme/dvd")
    client.post("/folders/Filme/dvd/choices", headers=SAME, data=disc_form())
    assert calls == []
    make_file(settings.output_dir / "iso" / "Filme.iso")  # refused after the scan: try again
    client.post("/folders/Filme/dvd", headers=SAME, data=disc_form())
    client.post("/folders/Filme/dvd", headers=SAME, data=disc_form())
    assert len(calls) == 1  # cached


def test_a_rip_whose_frames_cannot_be_read_is_explained(
    client: TestClient, probe_data: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    streams = probe_data["streams"]
    assert isinstance(streams, list)
    streams[0].update(codec_name="mpeg2video", width=720, height=480, r_frame_rate="30000/1001",
                      display_aspect_ratio="16:9")  # fmt: skip

    def broken(command: list[str]) -> str:
        raise OSError("boom")

    monkeypatch.setattr(dvd, "run_capture", broken)
    dvd._frames.clear()
    scan(client)

    response = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form())

    assert "Filme.mkv: " in response.text and "quadros" in response.text


def test_cross_site_writes_are_refused(client: TestClient) -> None:
    scan(client)
    cross = {"Sec-Fetch-Site": "cross-site"}

    assert client.post("/folders/Filme/dvd", headers=cross, data=disc_form()).status_code == 403
    choices = client.post("/folders/Filme/dvd/choices", headers=cross, data=disc_form())
    assert choices.status_code == 403


def test_regenerate_link_points_to_the_page(client: TestClient) -> None:
    scan(client)
    location = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form(),
                           follow_redirects=False).headers["location"]  # fmt: skip
    client.post(location + "/cancel", headers=SAME)

    assert '/folders/Filme/dvd">Gerar de novo' in client.get(location).text


def test_create_on_an_unscanned_folder_goes_back(client: TestClient) -> None:
    response = client.post("/folders/Dois/dvd", headers=SAME, data=disc_form(),
                           follow_redirects=False)  # fmt: skip
    choices = client.post("/folders/Dois/dvd/choices", headers=SAME, data=disc_form())

    assert response.headers["location"] == "/folders/Dois"
    assert "Formulário inválido" in choices.text


def test_job_created_by_another_click_in_between(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan(client)

    def busy(session: Session, plan: DiscPlan) -> int:
        raise store.ActiveJobError(7)

    monkeypatch.setattr(store, "enqueue", busy)
    response = client.post("/folders/Filme/dvd", headers=SAME, data=disc_form(),
                           follow_redirects=False)  # fmt: skip

    assert response.headers["location"] == "/jobs/7"


def confirm_original_language(client: TestClient, language: str) -> None:
    movie = Movie.model_validate({**TMDB_MOVIE, "original_language": language})
    details = DETAILS.dump_json(MovieDetails(kind="movie", movie=movie)).decode()
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        row = session.exec(select(MediaFile).where(MediaFile.path == "Filme/Filme.mkv")).one()
        row.title = Title(status="confirmed", kind="movie", label="Filme", tmdb_id=101,
                          tmdb_json=details)  # fmt: skip
        session.commit()


def test_page_uses_the_original_language_from_tmdb(client: TestClient) -> None:
    scan(client)
    confirm_original_language(client, "pt")  # a Brazilian movie: no English track suggested

    page = client.get("/folders/Filme/dvd").text

    assert 'name="audio" value="pt" checked' in page
    assert 'name="audio" value="en" checked' not in page


def test_page_ignores_a_tmdb_language_without_a_track(client: TestClient) -> None:
    scan(client)
    confirm_original_language(client, "fr")

    page = client.get("/folders/Filme/dvd").text

    assert 'name="audio" value="pt" checked' in page
    assert 'name="audio" value="en" checked' in page


def test_a_series_lists_its_pages(client: TestClient) -> None:
    scan(client, "Dois")
    form = disc_form(kind="series", order=["Dois/a.mkv", "Dois/b.mkv"], preview_page="1")

    response = client.post("/folders/Dois/dvd/choices", headers=SAME, data=form)
    page = client.get("/folders/Dois/dvd").text

    assert "menu.png?page=1&amp;v=" in response.text and "Lista 1" in response.text
    for name in ("Principal", "Lista 1", "Áudio: Inglês", "Legendas: Sem legenda",
                 "Legendas: Português"):  # fmt: skip
        assert name in page


def test_the_frame_scan_runs_off_the_event_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan(client)
    calls: list[str] = []

    async def threadpool(function: Any, *args: Any) -> Any:
        calls.append(function.__name__)
        return function(*args)

    monkeypatch.setattr(dvd, "run_in_threadpool", threadpool)
    client.post("/folders/Filme/dvd", headers=SAME, data=disc_form(), follow_redirects=False)

    assert calls == ["prepare_titles"]


def test_a_dvd_rip_warns_that_generating_takes_minutes(
    client: TestClient, probe_data: dict[str, object]
) -> None:
    streams = probe_data["streams"]
    assert isinstance(streams, list)
    streams[0].update(codec_name="mpeg2video", width=720, height=480, r_frame_rate="30000/1001",
                      display_aspect_ratio="16:9")  # fmt: skip
    scan(client)

    assert "pode levar alguns minutos" in client.get("/folders/Filme/dvd").text


def test_an_h264_folder_has_no_frame_scan_notice(client: TestClient) -> None:
    scan(client)

    assert "pode levar alguns minutos" not in client.get("/folders/Filme/dvd").text


def test_the_language_turned_on_is_always_on_the_disc(client: TestClient) -> None:
    scan(client)
    form = disc_form(audio=["en"], first_audio="pt", subtitle=[], subtitle_on="pt")

    client.post("/folders/Filme/dvd/choices", headers=SAME, data=form)

    choices = saved(client)
    assert choices is not None
    assert (choices.audio, choices.subtitles, choices.subtitle_on) == (("pt", "en"), ("pt",), "pt")


def test_the_radios_check_their_language_on_the_page(client: TestClient) -> None:
    scan(client)

    page = client.get("/folders/Filme/dvd").text

    assert page.count("closest('.track').querySelector('input[type=checkbox]').checked = true") == 3


def test_the_preflight_knows_the_cache_is_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan(client)
    seen: list[bool] = []

    def record(*args: Any, cache_on: bool = False) -> list[str]:
        seen.append(cache_on)
        return ["parado"]

    monkeypatch.setattr(dvd, "preflight", record)
    client.post("/folders/Filme/dvd", headers=SAME, data=disc_form())

    assert seen == [True]


# DVD rips


def as_rip(probe_data: dict[str, object], settings: Settings, size: int = 6 * 10**9,
           tag: int = 4 * 10**9) -> None:  # fmt: skip
    streams = probe_data["streams"]
    assert isinstance(streams, list)
    streams[0].update(
        codec_name="mpeg2video", width=720, height=480, r_frame_rate="30000/1001",
        avg_frame_rate="30000/1001", display_aspect_ratio="16:9",
        tags={"NUMBER_OF_BYTES-eng": str(tag)},
        side_data_list=[{"side_data_type": "CPB properties", "max_bitrate": 9800000,
                         "buffer_size": 1835008}],
    )  # fmt: skip
    os.truncate(settings.media_dir / "Filme" / "Filme.mkv", size)  # sparse: a 6 GB rip


def test_a_rip_shows_whether_its_video_is_copied(
    client: TestClient, probe_data: dict[str, object], settings: Settings
) -> None:
    as_rip(probe_data, settings)
    scan(client)

    both = client.post("/folders/Filme/dvd/choices", headers=SAME, data=disc_form())
    page_both = client.get("/folders/Filme/dvd").text
    client.post(
        "/folders/Filme/dvd/choices", headers=SAME, data=disc_form(audio=["pt"], subtitle=[])
    )
    page_pt = client.get("/folders/Filme/dvd").text

    assert "recodificado: as faixas escolhidas pedem mais espaço que o disco original" in page_both
    assert both.status_code == 200
    assert "vídeo copiado do DVD" in page_pt and 'name="reencode_rips"' in page_pt
    assert "usam os capítulos do DVD original" in page_pt


def test_the_reencode_box_is_saved(
    client: TestClient, probe_data: dict[str, object], settings: Settings
) -> None:
    as_rip(probe_data, settings)
    scan(client)

    client.post("/folders/Filme/dvd/choices", headers=SAME,
                data=disc_form(audio=["pt"], subtitle=[], reencode_rips="1"))  # fmt: skip

    choices = saved(client)
    assert choices is not None and choices.reencode_rips
    assert "recodificado: Recodificar os rips está marcado" in client.get("/folders/Filme/dvd").text


def test_a_copy_that_does_not_fit_says_so(
    client: TestClient, probe_data: dict[str, object], settings: Settings
) -> None:
    as_rip(probe_data, settings, size=12 * 10**9, tag=10 * 10**9)
    scan(client)

    client.post(
        "/folders/Filme/dvd/choices", headers=SAME, data=disc_form(audio=["pt"], subtitle=[])
    )

    assert "Não cabe com o vídeo copiado" in client.get("/folders/Filme/dvd").text


def test_a_long_gop_found_when_generating_recodes_the_rip(
    client: TestClient, probe_data: dict[str, object], settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    as_rip(probe_data, settings)
    sample = [{"repeat_pict": r, "interlaced_frame": 0, "top_field_first": 1,
               "key_frame": int(n % 15 == 0), "best_effort_timestamp_time": f"{n / 30:.4f}"}
              for n, r in enumerate((1, 0) * 40)]  # fmt: skip
    monkeypatch.setattr(dvd, "run_capture", lambda command: json.dumps({"frames": sample}))
    dvd._frames.clear()
    scan(client)

    response = client.post("/folders/Filme/dvd", headers=SAME,
                           data=disc_form(audio=["pt"], subtitle=[], confirm_low="1"),
                           follow_redirects=False)  # fmt: skip

    assert response.status_code == 303
    plan = queued_plan(client, response.headers["location"])
    assert not plan.titles[0].copy_video and plan.video_kbps > 0
