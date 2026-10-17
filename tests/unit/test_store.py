from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from projeto_dvd.jobs import store
from projeto_dvd.jobs.store import ActiveJobError, JobStatus
from tests.plans import make_movie


def enqueue(session: Session, folder: str = "Filme") -> int:
    return store.enqueue(session, make_movie(folder=folder))


def status(engine: Engine, job_id: int) -> str:
    with Session(engine) as session:
        job = store.get_job(session, job_id)
        assert job is not None
        return job.status


def test_enqueue_stores_the_plan(session: Session) -> None:
    job_id = enqueue(session)

    job = store.get_job(session, job_id)
    assert job is not None
    assert (job.folder, job.status, job.progress) == ("Filme", "queued", 0.0)
    assert job.plan_json == make_movie().model_dump_json()


def test_one_active_job_per_folder(session: Session) -> None:
    first = enqueue(session)

    with pytest.raises(ActiveJobError) as caught:
        enqueue(session)

    assert caught.value.job_id == first
    assert enqueue(session, "Outro") != first


def test_a_finished_job_frees_the_folder(engine: Engine, session: Session) -> None:
    first = enqueue(session)
    store.claim_next(engine)
    store.finish(engine, first, JobStatus.DONE, iso_path="/output/iso/Filme.iso")

    assert enqueue(session) != first


def test_claim_takes_the_oldest_once(engine: Engine, session: Session) -> None:
    first, second = enqueue(session, "A"), enqueue(session, "B")

    assert store.claim_next(engine) == first
    assert store.claim_next(engine) == second
    assert store.claim_next(engine) is None
    assert status(engine, first) == "running"


def test_cancel_a_queued_job_at_once(engine: Engine, session: Session) -> None:
    job_id = enqueue(session)

    store.request_cancel(engine, job_id)

    assert status(engine, job_id) == "canceled"
    assert store.claim_next(engine) is None


def test_cancel_after_the_claim_only_asks(engine: Engine, session: Session) -> None:
    job_id = enqueue(session)
    store.claim_next(engine)

    store.request_cancel(engine, job_id)

    assert status(engine, job_id) == "running"
    assert store.cancel_requested(engine, job_id)


def test_finish_only_moves_running_jobs(engine: Engine, session: Session) -> None:
    job_id = enqueue(session)
    store.request_cancel(engine, job_id)

    assert not store.finish(engine, job_id, JobStatus.DONE)
    assert status(engine, job_id) == "canceled"


def test_progress_is_saved_while_running(engine: Engine, session: Session) -> None:
    job_id = enqueue(session)
    store.claim_next(engine)

    store.save_progress(engine, job_id, "video_pass2", 0.42)

    session.expire_all()
    job = store.get_job(session, job_id)
    assert job is not None and (job.step, job.progress) == ("video_pass2", 0.42)


def test_fail_interrupted(engine: Engine, session: Session) -> None:
    running, queued = enqueue(session, "A"), enqueue(session, "B")
    store.claim_next(engine)

    assert store.fail_interrupted(engine, "reiniciou") == 1

    session.expire_all()
    job = store.get_job(session, running)
    assert job is not None and (job.status, job.error) == ("failed", "reiniciou")
    assert status(engine, queued) == "queued"


def test_queries(engine: Engine, session: Session) -> None:
    a, b = enqueue(session, "A"), enqueue(session, "B")
    store.claim_next(engine)

    assert set(store.active_folders(session)) == {"A", "B"}
    running = store.running_job(session)
    assert running is not None and running.id == a
    latest = store.latest_job(session, "B")
    assert latest is not None and latest.id == b
    assert [job.id for job in store.list_jobs(session)] == [b, a]


def test_dates_come_back_in_utc(engine: Engine, session: Session) -> None:
    # SQLModel returns UTC-aware datetimes, also for values written by the raw claim SQL, so
    # the pages can subtract them from datetime.now(UTC).
    job_id = enqueue(session)
    store.claim_next(engine)
    session.expire_all()

    job = store.get_job(session, job_id)

    assert job is not None and job.started_at is not None
    assert job.created_at.tzinfo == UTC and job.started_at.tzinfo == UTC
    assert datetime.now(UTC) - job.started_at < timedelta(minutes=1)


def test_integrity_error_without_an_active_job_is_raised(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueue(session)
    monkeypatch.setattr(store, "active_job", lambda session, folder: None)

    with pytest.raises(IntegrityError):
        enqueue(session)
