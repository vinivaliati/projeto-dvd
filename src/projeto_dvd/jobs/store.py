"""The job queue in SQLite: atomic transitions shared by the web and the worker."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Engine, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from projeto_dvd.db.models import Job
from projeto_dvd.planner.dvd_plan import DvdPlan


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)


class ActiveJobError(Exception):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"job {job_id} is already active for this folder")
        self.job_id = job_id


# One statement each, so a cancel and the worker's claim cannot overwrite each other.
CLAIM = text(
    """
    UPDATE job
    SET status = 'running'
      , started_at = :now
    WHERE id = (
        SELECT id
        FROM job
        WHERE status = 'queued'
        ORDER BY id
        LIMIT 1
    )
      AND status = 'queued'
    RETURNING id
    """
).bindparams(bindparam("now", type_=DateTime()))
CANCEL_QUEUED = text(
    """
    UPDATE job
    SET status = 'canceled'
      , finished_at = :now
    WHERE id = :id
      AND status = 'queued'
    """
).bindparams(bindparam("now", type_=DateTime()))
ASK_CANCEL = text(
    """
    UPDATE job
    SET cancel_requested = 1
    WHERE id = :id
      AND status = 'running'
    """
)
SAVE_PROGRESS = text(
    """
    UPDATE job
    SET step = :step
      , progress = :progress
    WHERE id = :id
      AND status = 'running'
    """
)
FINISH = text(
    """
    UPDATE job
    SET status = :status
      , error = :error
      , qa_json = :qa_json
      , iso_path = :iso_path
      , finished_at = :now
    WHERE id = :id
      AND status = 'running'
    """
).bindparams(bindparam("now", type_=DateTime()))
FAIL_INTERRUPTED = text(
    """
    UPDATE job
    SET status = 'failed'
      , error = :error
      , finished_at = :now
    WHERE status = 'running'
    """
).bindparams(bindparam("now", type_=DateTime()))


def enqueue(session: Session, plan: DvdPlan) -> int:
    job = Job(folder=plan.folder, plan_json=plan.model_dump_json(), created_at=_now())
    session.add(job)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        existing = active_job(session, plan.folder)
        if existing is None or existing.id is None:  # it finished in between: a real error
            raise
        raise ActiveJobError(existing.id) from error
    assert job.id is not None
    return job.id


def get_job(session: Session, job_id: int) -> Job | None:
    return session.get(Job, job_id)


def active_job(session: Session, folder: str) -> Job | None:
    query = select(Job).where(Job.folder == folder, col(Job.status).in_(list(ACTIVE)))
    return session.exec(query).first()


def latest_job(session: Session, folder: str) -> Job | None:
    query = select(Job).where(Job.folder == folder).order_by(col(Job.id).desc())
    return session.exec(query).first()


def active_folders(session: Session) -> dict[str, Job]:
    query = select(Job).where(col(Job.status).in_(list(ACTIVE)))
    return {job.folder: job for job in session.exec(query).all()}


def running_job(session: Session) -> Job | None:
    return session.exec(select(Job).where(Job.status == JobStatus.RUNNING)).first()


def list_jobs(session: Session) -> list[Job]:
    return list(session.exec(select(Job).order_by(col(Job.id).desc())).all())


def claim_next(engine: Engine) -> int | None:
    with engine.begin() as connection:
        job_id: int | None = connection.execute(CLAIM, {"now": _now()}).scalar_one_or_none()
        return job_id


def request_cancel(engine: Engine, job_id: int) -> None:
    with engine.begin() as connection:
        canceled = connection.execute(CANCEL_QUEUED, {"id": job_id, "now": _now()}).rowcount
        if not canceled:
            connection.execute(ASK_CANCEL, {"id": job_id})


def cancel_requested(engine: Engine, job_id: int) -> bool:
    with engine.connect() as connection:
        value = connection.execute(
            text("SELECT cancel_requested FROM job WHERE id = :id"), {"id": job_id}
        ).scalar_one_or_none()
    return bool(value)


def save_progress(engine: Engine, job_id: int, step: str, progress: float) -> None:
    with engine.begin() as connection:
        connection.execute(SAVE_PROGRESS, {"id": job_id, "step": step, "progress": progress})


def finish(
    engine: Engine,
    job_id: int,
    status: JobStatus,
    *,
    error: str | None = None,
    qa_json: str | None = None,
    iso_path: str | None = None,
) -> bool:
    values = {"id": job_id, "status": str(status), "error": error, "qa_json": qa_json,
              "iso_path": iso_path, "now": _now()}  # fmt: skip
    with engine.begin() as connection:
        return bool(connection.execute(FINISH, values).rowcount)


def fail_interrupted(engine: Engine, message: str) -> int:
    with engine.begin() as connection:
        return int(connection.execute(FAIL_INTERRUPTED, {"error": message, "now": _now()}).rowcount)


def _now() -> datetime:
    return datetime.now(UTC)
