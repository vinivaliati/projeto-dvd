"""The Montar DVD page: the titles, languages, menu and disc of a folder, saved as they change."""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlmodel import Session

from projeto_dvd.api.deps import FolderDep, MediaDirDep, SessionDep, SettingsDep, templates
from projeto_dvd.api.formatting import ENCODE_SECONDS_PER_SECOND
from projeto_dvd.config import Settings
from projeto_dvd.db.models import DiscProject, Job
from projeto_dvd.jobs import store
from projeto_dvd.jobs.pipeline import preflight
from projeto_dvd.jobs.store import JobStatus
from projeto_dvd.library.scan import FolderView, Status
from projeto_dvd.menus.render import preview
from projeto_dvd.menus.theme import PALETTE, auto_accent, available_backdrops
from projeto_dvd.planner.calculator import Estimate, suggest_profile
from projeto_dvd.planner.disc import (
    DiscTitle,
    audio_languages,
    menu_name,
    missing_languages,
    reconcile,
    strip_prefix,
    subtitle_languages,
    track_warnings,
)
from projeto_dvd.planner.disc_build import (
    TitleSource,
    build_disc_plan,
    disc_errors,
    disc_estimates,
    menu_plan,
)
from projeto_dvd.planner.disc_plan import DiscChoices, MenuPlan
from projeto_dvd.planner.disc_source import (
    Capture,
    disc_menu,
    folder_reasons,
    load_disc,
    prepare_title,
    run_capture,
    suggestion,
    theme_image,
)
from projeto_dvd.planner.languages import language_name

router = APIRouter()
INVALID_FORM = "Formulário inválido. Recarregue a página."
# Frame scans of MPEG-2 rips, by (path, size, mtime_ns): only "Gerar" runs them.
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


@dataclass(frozen=True)
class Disc:
    """A folder ready for the Montar DVD page."""

    name: str
    titles: tuple[DiscTitle, ...]
    backdrops: tuple[str, ...]
    suggested: DiscChoices
    saved: str | None


def parse_disc_form(form: Mapping[str, list[str]], disc: Disc) -> DiscChoices | None:
    """The form as choices; None when it does not fit the folder (a stale or forged page)."""

    def one(name: str, default: str = "") -> str:
        return form.get(name, [default])[0]

    order = list(form.get("order", []))
    if sorted(order) != sorted(t.path for t in disc.titles):
        return None
    move = one("move")
    if move:
        index, _, direction = move.partition(":")
        if not index.isdecimal() or direction not in ("up", "down"):
            return None
        i = int(index)
        j = i - 1 if direction == "up" else i + 1
        if 0 <= i < len(order) and 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
    audio = [lang for lang in audio_languages(disc.titles) if lang in form.get("audio", [])]
    first = one("first_audio")
    if first in audio:
        audio.remove(first)
        audio.insert(0, first)
    subtitles = [lang for lang in subtitle_languages(disc.titles)
                 if lang in form.get("subtitle", [])]  # fmt: skip
    backdrop = one("backdrop") or None
    fields = {
        "kind": one("kind"), "order": tuple(order), "profile": one("profile"),
        "audio": tuple(audio), "subtitles": tuple(subtitles),
        "subtitle_on": one("subtitle_on") or None, "chapters": one("chapters", "every"),
        "theme": {"backdrop": backdrop if backdrop in disc.backdrops else None,
                  "accent": one("accent", "auto"), "side": one("side", "left")},
    }  # fmt: skip
    try:
        return DiscChoices.model_validate({**fields, "minutes": int(one("minutes", "0") or 0)})
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
    disc = _disc(session, media_dir, settings, name, folder)
    if disc is None:
        return _redirect(request, "folder", name=name)
    choices = _choices(disc)
    return _render(request, "dvd_form.html", settings, disc, choices, errors=[])


@router.post("/folders/{name}/dvd/choices", response_class=HTMLResponse, name="dvd_choices")
async def dvd_choices(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
) -> Response:
    form = await _form(request)
    disc = _disc(session, media_dir, settings, name, folder)
    choices = parse_disc_form(form, disc) if disc else None
    if disc is None or choices is None:
        return HTMLResponse(f'<p class="banner banner-error" role="alert">{INVALID_FORM}</p>')
    before = _choices(disc)
    project = session.get(DiscProject, name) or DiscProject(folder=name, choices_json="")
    project.choices_json = choices.model_dump_json()
    session.add(project)
    session.commit()
    page = _page(form.get("preview_page", ["0"])[0])
    return _render(request, "_disc_results.html", settings, disc, choices, errors=[],
                   preview_page=page, titles_changed=choices.order != before.order)  # fmt: skip


@router.get("/folders/{name}/dvd/menu.png", name="dvd_menu_preview")
def dvd_menu_preview(
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
    page: int = 0,
) -> Response:
    disc = _disc(session, media_dir, settings, name, folder)
    if disc is None:
        raise HTTPException(status_code=404)
    menu = disc_menu(_choices(disc), disc.titles, name, settings.output_dir)
    if not 0 <= page < len(menu.pages):
        raise HTTPException(status_code=404)
    # The page URL carries a hash of the choices, so a new choice never shows an old image.
    return Response(preview(menu, page), media_type="image/png",
                    headers={"Cache-Control": "no-cache"})  # fmt: skip


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
    disc = _disc(session, media_dir, settings, name, folder)
    if disc is None:
        return _redirect(request, "folder", name=name)
    form = await _form(request)
    choices = parse_disc_form(form, disc)
    if choices is None:
        return _render(request, "dvd_form.html", settings, disc, _choices(disc), [INVALID_FORM])
    # Asked at the moment of generating, never saved: a later, worse disc asks again.
    confirm_low = form.get("confirm_low", [""])[0] == "1"
    replace_iso = form.get("replace_iso", [""])[0] == "1"
    estimate = _chosen(disc_estimates(choices, disc.titles, name), choices)
    errors = disc_errors(choices, disc.titles, estimate, confirm_low)
    sources: list[TitleSource] = []
    if not errors:
        for title in disc.titles:
            source = prepare_title(title, _cached_capture(title))
            if isinstance(source, tuple):
                errors += [f"{title.path.split('/', 1)[1]}: {reason}" for reason in source]
            else:
                sources.append(source)
    if not errors:
        menu = disc_menu(choices, disc.titles, name, settings.output_dir)
        plan = build_disc_plan(name, sources, choices, menu, confirm_low, replace_iso)
        errors = preflight(settings.work_dir, settings.output_dir, plan.estimated_bytes,
                           plan.iso_name, replace_iso)  # fmt: skip
    if errors:
        return _render(request, "dvd_form.html", settings, disc, choices, errors,
                       confirm_low=confirm_low, replace_iso=replace_iso)  # fmt: skip
    try:
        job_id = store.enqueue(session, plan)
    except store.ActiveJobError as error:
        job_id = error.job_id
    return _redirect(request, "job_page", job_id=job_id)


def _disc(
    session: Session, media_dir: Path, settings: Settings, name: str, folder: Path
) -> Disc | None:
    view, titles = load_disc(session, media_dir, name, folder)
    if folder_reasons(view) or not titles:
        return None
    project = session.get(DiscProject, name)
    return Disc(
        name=name, titles=titles, backdrops=available_backdrops(settings.output_dir, name),
        suggested=suggestion(titles, name), saved=project.choices_json if project else None,
    )  # fmt: skip


def _choices(disc: Disc) -> DiscChoices:
    return reconcile(disc.saved, disc.titles, disc.suggested, disc.backdrops)


def _cached_capture(title: DiscTitle) -> Capture:
    key = (title.path, title.video.size, title.video.mtime_ns)

    def capture(command: list[str]) -> str:
        if key not in _frames:
            _frames[key] = run_capture(command)
        return _frames[key]

    return capture


def _chosen(estimates: Sequence[Estimate], choices: DiscChoices) -> Estimate:
    return next(e for e in estimates if e.profile.key == choices.profile)


def _page(value: str) -> int:
    return int(value) if value.isdecimal() else 0


def _redirect(request: Request, route: str, **params: object) -> RedirectResponse:
    # A path, not a full URL: the browser keeps the host it used (localhost or 127.0.0.1).
    return RedirectResponse(request.url_for(route, **params).path, status_code=303)


def _render(
    request: Request,
    template: str,
    settings: Settings,
    disc: Disc,
    choices: DiscChoices,
    errors: list[str],
    *,
    preview_page: int = 0,
    titles_changed: bool = True,
    confirm_low: bool = False,
    replace_iso: bool = False,
) -> HTMLResponse:
    estimates = disc_estimates(choices, disc.titles, disc.name)
    path, image = theme_image(choices, disc.name, settings.output_dir)
    menu = menu_plan(choices, disc.titles, disc.name, path, image)
    by_path = {t.path: t for t in disc.titles}
    ordered = [by_path[path] for path in choices.order]
    existing = settings.output_dir / "iso" / f"{disc.name}.iso"
    context = {
        "disc": disc, "choices": choices, "errors": errors, "ordered": ordered,
        "labels": _menu_labels(ordered, menu), "names": [menu_name(t) for t in ordered],
        "warnings": track_warnings(disc.titles, choices),
        "badges": [missing_languages(title, choices) for title in ordered],
        "audio_languages": audio_languages(disc.titles),
        "subtitle_languages": subtitle_languages(disc.titles), "language_name": language_name,
        "estimates": estimates, "chosen": _chosen(estimates, choices),
        "suggested": suggest_profile(estimates).key, "menu": menu,
        "page_names": _page_names(menu), "preview_page": min(preview_page, len(menu.pages) - 1),
        "version": hashlib.sha1(choices.model_dump_json().encode()).hexdigest()[:12],
        "palette": PALETTE, "auto_key": auto_accent(image), "titles_changed": titles_changed,
        "existing": existing if existing.exists() else None,
        "confirm_low": confirm_low, "replace_iso": replace_iso,
        "encode_seconds": sum(
            (t.summary.duration or 0.0)
            * ENCODE_SECONDS_PER_SECOND[bool(t.summary.video and t.summary.video.height > 576)]
            for t in disc.titles
        ),
    }  # fmt: skip
    return templates.TemplateResponse(request, template, context)


def _menu_labels(ordered: Sequence[DiscTitle], menu: MenuPlan) -> list[str]:
    """The text each title gets on its menu button (prefix stripped, but not yet cut)."""
    heading = menu.pages[0].heading
    return [strip_prefix(menu_name(title), heading) for title in ordered]


def _page_names(menu: MenuPlan) -> list[str]:
    names = []
    lists = audio = subtitles = 0
    for page in menu.pages:
        if page.kind == "main":
            names.append("Principal")
        elif page.kind == "list":
            lists += 1
            names.append(f"Lista {lists}")
        elif page.kind == "audio":
            audio += 1
            names.append(f"Áudio {audio}")
        else:
            subtitles += 1
            names.append(f"Legendas {subtitles}")
    return names
