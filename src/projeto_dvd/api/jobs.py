"""Job pages: progress while it runs, the result, the log, cancel and cleanup."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from projeto_dvd.api.deps import EngineDep, SessionDep, SettingsDep, templates
from projeto_dvd.api.formatting import windows_path
from projeto_dvd.authoring.dvd.qa import QaReport
from projeto_dvd.config import Settings
from projeto_dvd.db.models import Job
from projeto_dvd.jobs import store
from projeto_dvd.jobs.files import clean_job_dir, log_tail, temporary_bytes
from projeto_dvd.jobs.pipeline import DISC_STEPS, STEP_LABELS, TITLE_STEPS, Step
from projeto_dvd.jobs.store import ACTIVE, JobStatus
from projeto_dvd.planner.disc_plan import DiscPlan, TitlePlan
from projeto_dvd.planner.profiles import PROFILES
from projeto_dvd.planner.source import VideoMode

router = APIRouter()
WORKER_GRACE_SECONDS = 60
MIN_PROGRESS_FOR_ESTIMATE = 0.02


@dataclass(frozen=True)
class StepView:
    label: str
    state: Literal["done", "current", "todo"]


@dataclass(frozen=True)
class JobView:
    job: Job
    plan: DiscPlan
    profile_name: str
    steps: tuple[StepView, ...]
    percent: int
    active: bool
    canceling: bool
    started: datetime | None
    elapsed_seconds: float | None
    remaining_seconds: float | None
    queue_ahead: Job | None
    waiting_worker: bool
    qa: QaReport | None
    temp_bytes: int
    iso_display: str
    now: datetime


def job_view(session: Session, settings: Settings, job: Job, now: datetime) -> JobView:
    assert job.id is not None
    plan = DiscPlan.model_validate_json(job.plan_json)
    started = job.started_at
    elapsed = (now - started).total_seconds() if started else None
    remaining = None
    if job.status == JobStatus.RUNNING and elapsed and job.progress >= MIN_PROGRESS_FOR_ESTIMATE:
        remaining = elapsed * (1 - job.progress) / job.progress
    running = store.running_job(session)
    created = job.created_at
    queued = job.status == JobStatus.QUEUED
    return JobView(
        job=job, plan=plan, profile_name=PROFILES[plan.profile].name,
        steps=_steps(plan, job), percent=int(job.progress * 100),
        active=job.status in ACTIVE, canceling=job.status == JobStatus.RUNNING
        and job.cancel_requested, started=started, elapsed_seconds=elapsed,
        remaining_seconds=remaining,
        queue_ahead=running if queued and running is not None else None,
        waiting_worker=queued and running is None and created is not None
        and (now - created).total_seconds() > WORKER_GRACE_SECONDS,
        qa=QaReport.model_validate_json(job.qa_json) if job.qa_json else None,
        temp_bytes=0 if job.status in ACTIVE else temporary_bytes(settings.work_dir, job.id),
        iso_display=_iso_display(settings, plan.iso_name),
        now=now,
    )  # fmt: skip


@router.get("/jobs", response_class=HTMLResponse, name="jobs")
def jobs_page(request: Request, session: SessionDep) -> HTMLResponse:
    jobs = [(job, DiscPlan.model_validate_json(job.plan_json)) for job in store.list_jobs(session)]
    context = {"jobs": jobs, "profiles": PROFILES, "now": _now()}
    return templates.TemplateResponse(request, "jobs.html", context)


@router.get("/jobs/{job_id}", response_class=HTMLResponse, name="job_page")
def job_page(request: Request, job_id: int, session: SessionDep,
             settings: SettingsDep) -> HTMLResponse:  # fmt: skip
    view = job_view(session, settings, _job(session, job_id), _now())
    return templates.TemplateResponse(request, "job.html", {"view": view})


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse, name="job_status")
def job_status(request: Request, job_id: int, session: SessionDep,
               settings: SettingsDep) -> HTMLResponse:  # fmt: skip
    view = job_view(session, settings, _job(session, job_id), _now())
    return templates.TemplateResponse(request, "_job_status.html", {"view": view})


@router.get("/jobs/{job_id}/log", response_class=HTMLResponse, name="job_log")
def job_log(request: Request, job_id: int, session: SessionDep,
            settings: SettingsDep) -> HTMLResponse:  # fmt: skip
    _job(session, job_id)
    context = {"log": log_tail(settings.work_dir, job_id)}
    return templates.TemplateResponse(request, "_job_log.html", context)


@router.post("/jobs/{job_id}/cancel", response_class=HTMLResponse, name="cancel_job")
def cancel_job(request: Request, job_id: int, session: SessionDep, settings: SettingsDep,
               engine: EngineDep) -> HTMLResponse:  # fmt: skip
    _job(session, job_id)
    store.request_cancel(engine, job_id)
    session.expire_all()
    return job_status(request, job_id, session, settings)


@router.post("/jobs/{job_id}/clean", response_class=HTMLResponse, name="clean_job")
def clean_job(request: Request, job_id: int, session: SessionDep,
              settings: SettingsDep) -> HTMLResponse:  # fmt: skip
    if _job(session, job_id).status in ACTIVE:
        raise HTTPException(status_code=409)
    clean_job_dir(settings.work_dir, job_id)
    return job_status(request, job_id, session, settings)


def _job(session: Session, job_id: int) -> Job:
    job = store.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404)
    return job


def _steps(plan: DiscPlan, job: Job) -> tuple[StepView, ...]:
    """The steps of the job. With several titles, only the current one is expanded; the
    others show as one line each, so a 24-episode disc does not list 144 steps."""
    rows = [(n, step) for n, title in enumerate(plan.titles, 1) for step in _title_steps(title)]
    rows += [(0, step) for step in DISC_STEPS if step != Step.MENUS or plan.menu is not None]
    if job.status == JobStatus.DONE:
        current = len(rows)
    elif job.status == JobStatus.QUEUED:
        current = -1
    else:
        current = next((i for i, row in enumerate(rows) if row == _parse_step(job.step)), -1)
    count = len(plan.titles)
    focus = rows[current][0] if 0 <= current < len(rows) else 0
    views: list[StepView] = []
    for n in range(1, count + 1):
        indices = [i for i, row in enumerate(rows) if row[0] == n]
        if count > 1 and n != focus:
            views.append(StepView(f"Título {n} de {count}", _state(indices, current)))
            continue
        prefix = f"Título {n} de {count} · " if count > 1 else ""
        views += [StepView(prefix + STEP_LABELS[rows[i][1]], _state([i], current)) for i in indices]
    views += [StepView(STEP_LABELS[step], _state([i], current))
              for i, (n, step) in enumerate(rows) if n == 0]  # fmt: skip
    return tuple(views)


def _title_steps(title: TitlePlan) -> list[Step]:
    return [
        step for step in TITLE_STEPS
        if not (step == Step.PULLDOWN and title.mode != VideoMode.FILM)
        and not (step == Step.SUBTITLES and not title.subtitles)
    ]  # fmt: skip


def _parse_step(text: str | None) -> tuple[int, Step] | None:
    """'2:video_pass2', or a phase 3 job's bare step (its only title)."""
    if not text:
        return None
    title, _, name = text.rpartition(":")
    if name not in {s.value for s in Step}:
        return None
    step = Step(name)
    return (int(title) if title else (1 if step in TITLE_STEPS else 0)), step


def _state(indices: list[int], current: int) -> Literal["done", "current", "todo"]:
    if all(i < current for i in indices):
        return "done"
    if current in indices:
        return "current"
    return "todo"


def _iso_display(settings: Settings, iso_name: str) -> str:
    if settings.host_output_dir:
        return windows_path(settings.host_output_dir, f"iso/{iso_name}")
    return f"iso\\{iso_name} (na pasta HOST_OUTPUT_DIR do .env)"


def _now() -> datetime:
    return datetime.now(UTC)
