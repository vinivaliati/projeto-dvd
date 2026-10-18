import html
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from projeto_dvd.app import create_app
from projeto_dvd.authoring.dvd.qa import Check, QaReport
from projeto_dvd.config import Settings
from projeto_dvd.jobs import store
from projeto_dvd.jobs.files import job_dir
from projeto_dvd.jobs.store import JobStatus
from tests.client import client_for
from tests.plans import make_disc_plan, make_movie, movie_title
from tests.tree import make_file

SAME = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(media_dir=tmp_path / "media", work_dir=tmp_path / "work",
                    output_dir=tmp_path / "out", database_url=database_url)  # fmt: skip


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with client_for(create_app(settings)) as client:
        yield client


def new_job(client: TestClient, folder: str = "Filme") -> int:
    engine = client.app.state.engine  # type: ignore[attr-defined]
    with Session(engine) as session:
        return store.enqueue(session, make_movie(folder=folder))


def engine_of(client: TestClient) -> object:
    return client.app.state.engine  # type: ignore[attr-defined]


def test_queued_job_waiting_for_the_worker(client: TestClient) -> None:
    job_id = new_job(client)

    page = client.get(f"/jobs/{job_id}")

    assert page.status_code == 200
    assert "Na fila" in page.text
    assert 'hx-trigger="every 2s"' in page.text


def test_queued_behind_another_job(client: TestClient) -> None:
    first = new_job(client, "A")
    second = new_job(client, "B")
    store.claim_next(engine_of(client))  # type: ignore[arg-type]

    page = client.get(f"/jobs/{second}")

    assert f"Começa quando o job #{first} (pasta A) terminar." in page.text


def test_running_job_shows_steps_progress_and_cancel(client: TestClient) -> None:
    job_id = new_job(client)
    engine = engine_of(client)
    store.claim_next(engine)  # type: ignore[arg-type]
    store.save_progress(engine, job_id, "video_pass2", 0.5)  # type: ignore[arg-type]

    page = client.get(f"/jobs/{job_id}/status")

    assert "Vídeo: 2ª passada (codificação)" in page.text
    assert 'value="50"' in page.text and "50%" in page.text
    assert "Pode fechar esta página" in page.text
    assert 'hx-post="' in page.text and "/cancel" in page.text
    assert "<html" not in page.text


def test_cancel_a_queued_job(client: TestClient) -> None:
    job_id = new_job(client)

    response = client.post(f"/jobs/{job_id}/cancel", headers=SAME)

    assert response.status_code == 200
    assert "Cancelado por você" in response.text
    assert "Gerar de novo" in response.text
    assert 'hx-trigger="every 2s"' not in response.text


def test_cancel_a_running_job_shows_canceling(client: TestClient) -> None:
    job_id = new_job(client)
    store.claim_next(engine_of(client))  # type: ignore[arg-type]

    response = client.post(f"/jobs/{job_id}/cancel", headers=SAME)

    assert "Cancelando..." in response.text


def test_done_job_shows_the_iso_and_the_qa(client: TestClient, settings: Settings) -> None:
    job_id = new_job(client)
    engine = engine_of(client)
    store.claim_next(engine)  # type: ignore[arg-type]
    report = QaReport(checks=(Check(name="size", label="Cabe num DVD-9", ok=True,
                                    detail="4 GB de 8,5 GB"),), iso_bytes=4_000_000_000,
                      estimated_bytes=4_100_000_000)  # fmt: skip
    store.finish(engine, job_id, JobStatus.DONE, qa_json=report.model_dump_json(),  # type: ignore[arg-type]
                 iso_path=str(settings.output_dir / "iso" / "Filme.iso"))  # fmt: skip

    page = client.get(f"/jobs/{job_id}")

    assert "Pronto! O ISO passou na conferência automática." in page.text
    assert "iso\\Filme.iso" in page.text
    assert "Cabe num DVD-9" in page.text
    assert "ImgBurn" in page.text


def test_failed_job_explains_and_offers_to_retry(client: TestClient) -> None:
    job_id = new_job(client)
    engine = engine_of(client)
    store.claim_next(engine)  # type: ignore[arg-type]
    store.finish(engine, job_id, JobStatus.FAILED, error="Falhou na etapa Áudio.")  # type: ignore[arg-type]

    page = client.get(f"/jobs/{job_id}")

    assert "Falhou na etapa Áudio." in page.text
    assert "Gerar de novo" in page.text


def test_log_fragment(client: TestClient, settings: Settings) -> None:
    job_id = new_job(client)
    make_file(job_dir(settings.work_dir, job_id) / "job.log", b"$ ffmpeg -y\nfeito\n")

    response = client.get(f"/jobs/{job_id}/log")

    assert "feito" in response.text and "<html" not in response.text


def test_clean_refuses_an_active_job(client: TestClient) -> None:
    job_id = new_job(client)

    assert client.post(f"/jobs/{job_id}/clean", headers=SAME).status_code == 409


def test_clean_a_finished_job(client: TestClient, settings: Settings) -> None:
    job_id = new_job(client)
    store.request_cancel(engine_of(client), job_id)  # type: ignore[arg-type]
    root = job_dir(settings.work_dir, job_id)
    make_file(root / "job.log")
    make_file(root / "video.m2v", b"x" * 2_000_000)

    page = client.get(f"/jobs/{job_id}")
    response = client.post(f"/jobs/{job_id}/clean", headers=SAME)

    assert "Apagar arquivos temporários (2 MB)" in page.text
    assert response.status_code == 200
    assert sorted(p.name for p in root.iterdir()) == ["job.log"]


def test_unknown_job_is_404(client: TestClient) -> None:
    assert client.get("/jobs/999").status_code == 404
    assert client.post("/jobs/999/cancel", headers=SAME).status_code == 404


def test_job_list_and_nav(client: TestClient) -> None:
    new_job(client, "Senhor dos Aneis")

    page = client.get("/jobs")

    assert "Senhor dos Aneis" in page.text and "DVD-9" in page.text
    assert '/jobs">Jobs</a>' in client.get("/").text


def test_tiny_leftovers_do_not_offer_a_cleanup(client: TestClient, settings: Settings) -> None:
    job_id = new_job(client)
    store.request_cancel(engine_of(client), job_id)  # type: ignore[arg-type]
    make_file(job_dir(settings.work_dir, job_id) / "dvd.xml", b"<dvdauthor/>")

    assert "Apagar arquivos temporários" not in client.get(f"/jobs/{job_id}").text


def test_done_job_shows_the_windows_path(tmp_path: Path, database_url: str) -> None:
    settings = Settings(media_dir=tmp_path / "media", work_dir=tmp_path / "work",
                        output_dir=tmp_path / "out", database_url=database_url,
                        host_output_dir="/mnt/c/Users/vini/Videos/projeto-dvd")  # fmt: skip
    with client_for(create_app(settings)) as client:
        job_id = new_job(client)
        engine = engine_of(client)
        store.claim_next(engine)  # type: ignore[arg-type]
        store.finish(engine, job_id, JobStatus.DONE, iso_path="/output/iso/Filme.iso")  # type: ignore[arg-type]

        page = client.get(f"/jobs/{job_id}").text

    assert "C:\\Users\\vini\\Videos\\projeto-dvd\\iso\\Filme.iso" in page
    assert page.index("Antes de gravar") < page.index("Gravar no Windows")


def test_job_list_shows_the_job_number(client: TestClient) -> None:
    job_id = new_job(client)

    assert f">#{job_id}<" in client.get("/jobs").text


def running_job(client: TestClient, step: str, titles: int = 2) -> int:
    engine = engine_of(client)
    plan = make_disc_plan(titles=tuple(movie_title(path=f"Filme/{n}.mkv")
                                       for n in range(1, titles + 1)))  # fmt: skip
    with Session(engine) as session:  # type: ignore[arg-type]
        job_id = store.enqueue(session, plan)
    store.claim_next(engine)  # type: ignore[arg-type]
    store.save_progress(engine, job_id, step, 0.5)  # type: ignore[arg-type]
    return job_id


def test_several_titles_expand_only_the_current_one(client: TestClient) -> None:
    job_id = running_job(client, "2:video_pass2")

    text = client.get(f"/jobs/{job_id}").text

    assert '<li class="step step-done">Título 1 de 2</li>' in text
    assert "Etapa atual: Título 2 de 2 · Vídeo: 2ª passada (codificação)" in text
    assert '<li class="step step-todo">Desenhando os menus</li>' in text
    assert "2 títulos" in text


def test_a_step_from_another_version_marks_nothing_current(client: TestClient) -> None:
    job_id = running_job(client, "9:unknown", titles=1)

    assert "Etapa atual" not in client.get(f"/jobs/{job_id}").text


def test_a_phase_3_step_belongs_to_its_only_title(client: TestClient) -> None:
    job_id = running_job(client, "audio", titles=1)

    assert "Etapa atual: Áudio" in client.get(f"/jobs/{job_id}").text


# Resume and the cache


@pytest.fixture
def room(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Work and output folders with plenty of free space, for the resume preflight."""
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(settings.work_dir)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage._replace(free=10**12))


def stopped_job(client: TestClient, status: JobStatus = JobStatus.FAILED,
                folder: str = "Filme", **plan: Any) -> int:  # fmt: skip
    engine = engine_of(client)
    with Session(engine) as session:  # type: ignore[arg-type]
        job_id = store.enqueue(session, make_movie(folder=folder, **plan))
    store.claim_next(engine)  # type: ignore[arg-type]
    store.finish(engine, job_id, status, error="O worker parou no meio.")  # type: ignore[arg-type]
    return job_id


def test_a_stopped_job_offers_resume(client: TestClient) -> None:
    job_id = stopped_job(client)

    assert f'/jobs/{job_id}/resume"' in client.get(f"/jobs/{job_id}").text


def test_resume_puts_the_job_back_and_keeps_only_the_log(
    client: TestClient, room: None, settings: Settings
) -> None:
    job_id = stopped_job(client)
    folder = job_dir(settings.work_dir, job_id)
    make_file(folder / "job.log", b"antes\n")
    make_file(folder / "disc.iso", b"x" * 100)

    response = client.post(f"/jobs/{job_id}/resume", headers=SAME)

    assert response.status_code == 200 and "Na fila" in response.text
    assert sorted(p.name for p in folder.iterdir()) == ["job.log"]
    with Session(engine_of(client)) as session:  # type: ignore[arg-type]
        job = store.get_job(session, job_id)
        assert job is not None and job.status == "queued"


def test_resume_runs_the_preflight(client: TestClient, room: None, settings: Settings) -> None:
    job_id = stopped_job(client)
    make_file(settings.output_dir / "iso" / "Filme.iso")
    folder = job_dir(settings.work_dir, job_id)
    make_file(folder / "title1.mpg")

    response = client.post(f"/jobs/{job_id}/resume", headers=SAME)

    assert "Já existe um ISO com este nome" in html.unescape(response.text)
    assert (folder / "title1.mpg").exists()  # nothing cleaned when it cannot resume


def test_only_the_last_job_of_a_folder_resumes(client: TestClient) -> None:
    old = stopped_job(client)
    stopped_job(client, JobStatus.CANCELED)

    assert "/resume" not in client.get(f"/jobs/{old}").text
    assert client.post(f"/jobs/{old}/resume", headers=SAME).status_code == 409


def test_a_phase_3_job_or_a_done_one_does_not_resume(client: TestClient) -> None:
    old = stopped_job(client, menu=None)
    done = stopped_job(client, JobStatus.DONE, folder="Outro")

    assert client.post(f"/jobs/{old}/resume", headers=SAME).status_code == 409
    assert client.post(f"/jobs/{done}/resume", headers=SAME).status_code == 409
    assert "/resume" not in client.get(f"/jobs/{done}").text


def test_resume_when_another_job_of_the_folder_runs(
    client: TestClient, room: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = stopped_job(client)

    def busy(engine: object, job_id: int) -> bool:
        raise store.ActiveJobError(42)

    monkeypatch.setattr(store, "resume", busy)
    response = client.post(f"/jobs/{job_id}/resume", headers=SAME)

    assert 'href="/jobs/42"' in response.text


def test_resume_of_a_job_that_already_changed(
    client: TestClient, room: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = stopped_job(client)
    monkeypatch.setattr(store, "resume", lambda engine, job_id: False)

    assert client.post(f"/jobs/{job_id}/resume", headers=SAME).status_code == 409


def test_cross_site_resume_and_clean_are_refused(client: TestClient) -> None:
    job_id = stopped_job(client)
    cross = {"Sec-Fetch-Site": "cross-site"}

    assert client.post(f"/jobs/{job_id}/resume", headers=cross).status_code == 403
    assert client.post("/cache/clean", headers=cross).status_code == 403


def test_the_job_list_shows_the_cache(client: TestClient, settings: Settings) -> None:
    make_file(settings.work_dir / "cache" / f"{'a' * 64}.m2v", b"x" * 3_000_000)

    page = client.get("/jobs").text

    assert "Cache de vídeo: 3 MB de 50 GB" in page and "/cache/clean" in page


def test_clean_cache(client: TestClient, settings: Settings) -> None:
    video = make_file(settings.work_dir / "cache" / f"{'a' * 64}.m2v")
    notes = make_file(settings.work_dir / "cache" / "notas.txt")

    response = client.post("/cache/clean", headers=SAME, follow_redirects=False)

    assert (response.status_code, response.headers["location"]) == (303, "/jobs")
    assert not video.exists() and notes.exists()


def test_clean_cache_refuses_while_a_job_is_active(client: TestClient, settings: Settings) -> None:
    video = make_file(settings.work_dir / "cache" / f"{'a' * 64}.m2v")
    new_job(client)

    assert client.post("/cache/clean", headers=SAME).status_code == 409
    assert video.exists()


def test_a_copied_title_shows_the_copy_step(client: TestClient) -> None:
    engine = engine_of(client)
    plan = make_disc_plan(titles=(movie_title(copy_video=True, video_bytes=10),
                                  movie_title(path="Filme/2.mkv")))  # fmt: skip
    with Session(engine) as session:  # type: ignore[arg-type]
        job_id = store.enqueue(session, plan)
    store.claim_next(engine)  # type: ignore[arg-type]
    store.save_progress(engine, job_id, "1:video_copy", 0.1)  # type: ignore[arg-type]

    text = client.get(f"/jobs/{job_id}").text

    assert "Etapa atual: Título 1 de 2 · Vídeo copiado da origem" in text
    assert "Título 1 de 2 · Vídeo: 1ª passada" not in text


def test_clean_cache_with_an_active_job_explains(client: TestClient, settings: Settings) -> None:
    make_file(settings.work_dir / "cache" / f"{'a' * 64}.m2v")
    new_job(client)

    response = client.post("/cache/clean", headers=SAME)

    assert response.status_code == 409
    assert "Espere o job terminar" in response.text and 'href="/jobs"' in response.text


def test_a_stopped_blu_ray_job_resumes_and_shows_its_own_steps(client: TestClient) -> None:
    job_id = stopped_job(client, profile="bd25", menu=None)

    page = html.unescape(client.get(f"/jobs/{job_id}").text)

    assert f"/jobs/{job_id}/resume" in page
    assert "Montando o Blu-ray (tsMuxeR)" in page
    assert "Desenhando os menus" not in page and "Ajuste de quadros" not in page
