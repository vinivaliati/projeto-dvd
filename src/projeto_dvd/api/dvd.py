"""The DVD form: suggestions, live capacity, validation and the job creation."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlmodel import Session

from projeto_dvd.api.deps import FolderDep, MediaDirDep, SessionDep, SettingsDep, templates
from projeto_dvd.config import Settings
from projeto_dvd.db.models import Job
from projeto_dvd.jobs import store
from projeto_dvd.jobs.pipeline import preflight
from projeto_dvd.jobs.store import JobStatus
from projeto_dvd.library.scan import FolderView, Status, folder_view
from projeto_dvd.planner.calculator import Estimate, estimate
from projeto_dvd.planner.disc_source import DiscSource, folder_reasons, prepare, run_capture
from projeto_dvd.planner.dvd_plan import (
    Choices,
    audio_kbps,
    audio_output,
    build_plan,
    plan_chapters,
    suggest_choices,
    validate_choices,
)
from projeto_dvd.planner.profiles import PROFILES
from projeto_dvd.planner.source import geometry

router = APIRouter()
INVALID_FORM = "Formulário inválido. Recarregue a página."
# Frame scans of MPEG-2 rips, by (path, size, mtime_ns): the form and the estimates reuse them.
_frames: dict[tuple[str, int, int], str] = {}


@dataclass(frozen=True)
class DvdState:
    visible: bool
    reasons: tuple[str, ...]
    active: Job | None
    last_done: Job | None


def dvd_state(session: Session, view: FolderView) -> DvdState:
    latest = store.latest_job(session, view.name)
    return DvdState(
        visible=view.status != Status.EMPTY,
        reasons=folder_reasons(view),
        active=store.active_job(session, view.name),
        last_done=latest if latest and latest.status == JobStatus.DONE else None,
    )


def parse_choices(form: Mapping[str, list[str]]) -> Choices | None:
    def one(name: str, default: str = "") -> str:
        return form.get(name, [default])[0]

    try:
        return Choices.model_validate(
            {
                "profile": one("profile"),
                "audio": tuple(int(value) for value in form.get("audio", [])),
                "first_audio": int(one("first_audio", "-1") or -1),
                "subtitles": tuple(form.get("subtitle", [])),
                "subtitle_on": one("subtitle_on") or None,
                "chapters": one("chapters", "every"),
                "minutes": int(one("minutes", "0") or 0),
                "confirm_low": one("confirm_low") == "1",
                "replace_iso": one("replace_iso") == "1",
            }
        )
    except (ValueError, ValidationError):
        return None


async def _form(request: Request) -> dict[str, list[str]]:
    """The urlencoded form; parsed here so python-multipart is not needed for a few fields."""
    return parse_qs((await request.body()).decode(), keep_blank_values=True)


@router.get("/folders/{name}/dvd", response_class=HTMLResponse, name="dvd_form")
def dvd_form(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
) -> Response:
    active = store.active_job(session, name)
    if active is not None:
        return _redirect(request, "job_page", job_id=active.id)
    source = _source(session, media_dir, name, folder)
    if not isinstance(source, DiscSource):
        return _redirect(request, "folder", name=name)
    choices = suggest_choices(source.summary, source.options, _duration(source))
    return _render_form(request, settings, source, choices, errors=[])


@router.post("/folders/{name}/dvd/estimate", response_class=HTMLResponse, name="dvd_estimate")
async def dvd_estimate(
    request: Request, name: str, folder: FolderDep, session: SessionDep, media_dir: MediaDirDep
) -> Response:
    choices = parse_choices(await _form(request))
    source = _source(session, media_dir, name, folder)
    if choices is None or not isinstance(source, DiscSource):
        return HTMLResponse(f'<p class="banner banner-error">{INVALID_FORM}</p>')
    context = _cards_context(source, choices)
    return templates.TemplateResponse(request, "_profile_cards.html", context)


@router.post("/folders/{name}/dvd", response_class=HTMLResponse, name="create_dvd")
async def create_dvd(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
) -> Response:
    active = store.active_job(session, name)
    if active is not None:
        return _redirect(request, "job_page", job_id=active.id)
    source = _source(session, media_dir, name, folder)
    if not isinstance(source, DiscSource):
        return _redirect(request, "folder", name=name)
    choices = parse_choices(await _form(request))
    if choices is None:
        default = suggest_choices(source.summary, source.options, _duration(source))
        return _render_form(request, settings, source, default, errors=[INVALID_FORM])
    errors = validate_choices(choices, source.summary, source.options)
    if not errors:
        plan = build_plan(
            folder=name,
            path=source.video.path,
            size=source.video.size,
            mtime_ns=source.video.mtime_ns,
            summary=source.summary,
            options=source.options,
            choices=choices,
            mode=source.mode,
            top_field_first=source.top_field_first,
        )
        errors = preflight(
            settings.work_dir,
            settings.output_dir,
            plan.estimated_bytes,
            plan.iso_name,
            choices.replace_iso,
        )
    if errors:
        return _render_form(request, settings, source, choices, errors)
    try:
        job_id = store.enqueue(session, plan)
    except store.ActiveJobError as error:
        job_id = error.job_id
    return _redirect(request, "job_page", job_id=job_id)


def _redirect(request: Request, route: str, **params: object) -> RedirectResponse:
    # A path, not a full URL: the browser keeps the host it used (localhost or 127.0.0.1).
    return RedirectResponse(request.url_for(route, **params).path, status_code=303)


def _source(
    session: Session, media_dir: Path, name: str, folder: Path
) -> DiscSource | tuple[str, ...]:
    view = folder_view(session, media_dir, name, folder)
    reasons = folder_reasons(view)
    if reasons or len(view.files) != 1 or view.files[0].summary is None:
        return reasons or ("",)
    file = view.files[0]
    key = (file.video.path, file.video.size, file.video.mtime_ns)

    def cached_capture(command: list[str]) -> str:
        if key not in _frames:
            _frames[key] = run_capture(command)
        return _frames[key]

    assert file.summary is not None
    return prepare(name, file.video, file.summary, cached_capture)


def _duration(source: DiscSource) -> float:
    return source.summary.duration or 0.0


def _cards_context(source: DiscSource, choices: Choices) -> dict[str, object]:
    duration = _duration(source)
    kbps = audio_kbps(source.summary, choices)
    estimates: list[Estimate] = [
        estimate(profile, duration, kbps, len(choices.subtitles)) for profile in PROFILES.values()
    ]
    suggested = suggest_choices(source.summary, source.options, duration).profile
    chosen = next((e for e in estimates if e.profile.key == choices.profile), None)
    return {"estimates": estimates, "choices": choices, "suggested": suggested, "chosen": chosen}


def _render_form(
    request: Request, settings: Settings, source: DiscSource, choices: Choices, errors: list[str]
) -> HTMLResponse:
    video = source.summary.video
    assert video is not None
    existing = settings.output_dir / "iso" / f"{source.folder}.iso"
    chapters = plan_chapters(
        source.summary.chapters, _duration(source), choices.chapters, choices.minutes
    )
    context = {
        "source": source,
        "choices": choices,
        "errors": errors,
        "video": video,
        "shape": geometry(video),
        "outputs": {t.index: audio_output(t) for t in source.summary.audio},
        "chapters": chapters,
        "existing": existing if existing.exists() else None,
        **_cards_context(source, choices),
    }
    return templates.TemplateResponse(request, "dvd_form.html", context)
