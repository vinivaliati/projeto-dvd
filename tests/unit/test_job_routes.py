from collections.abc import Iterator
from pathlib import Path

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
from tests.plans import make_plan
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
        return store.enqueue(session, make_plan(folder=folder))


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
