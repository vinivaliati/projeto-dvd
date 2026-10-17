"""The Capa page: the printed cover and the disc labels of a folder, from the saved disc choices."""

import hashlib
import html
import io
import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from PIL import Image
from pydantic import ValidationError
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from projeto_dvd.api.curation import run_locked
from projeto_dvd.api.deps import (
    FolderDep,
    MediaDirDep,
    SessionDep,
    SettingsDep,
    TmdbDep,
    templates,
)
from projeto_dvd.api.dvd import INVALID_FORM, Disc, load_disc_page, read_form, saved_choices
from projeto_dvd.api.formatting import output_display
from projeto_dvd.config import Settings
from projeto_dvd.covers import render
from projeto_dvd.covers.art import (
    FRONT_NAMES,
    PRINT_DPI,
    ArtOption,
    art_options,
    default_front,
    front_file,
)
from projeto_dvd.covers.content import CoverContent, cover_content
from projeto_dvd.db.models import DiscProject
from projeto_dvd.jobs.files import cannot_write
from projeto_dvd.menus.theme import resolve_accent
from projeto_dvd.metadata.art import save_art
from projeto_dvd.metadata.curation import confirmed_details, title_art_dir
from projeto_dvd.metadata.names import safe_name
from projeto_dvd.metadata.tmdb import TmdbClient
from projeto_dvd.metadata.tmdb_models import Details
from projeto_dvd.planner.disc_plan import CoverChoices, DiscChoices
from projeto_dvd.planner.disc_source import theme_image

router = APIRouter()
PREVIEW_DPI = 50
ART_FAILED = "A arte não pôde ser usada (o arquivo do TMDB não abriu). A frente anterior continua."
PDF_OPEN = "Feche o PDF aberto e tente de novo."
SHOW_NAME = {"auto": None, "yes": True, "no": False}
ART_FORMATS = {"JPEG": "front.jpg", "PNG": "front.png"}


@dataclass(frozen=True)
class Cover:
    """Everything the page and the renders need, read once per request."""

    disc: Disc
    choices: DiscChoices
    details: dict[str, Details]
    options: list[ArtOption]
    front: Path | None
    backdrop: Image.Image | None
    accent: str
    show_name: bool
    content: CoverContent

    @property
    def version(self) -> str:
        """Changes with any choice or a new front file, so the preview never shows an old image."""
        stamp = self.front.stat().st_mtime_ns if self.front and self.front.exists() else 0
        text = f"{self.choices.model_dump_json()}{self.front}{stamp}"
        return hashlib.sha1(text.encode()).hexdigest()[:12]


def build_cover(session: Session, settings: Settings, disc: Disc) -> Cover:
    choices = saved_choices(disc)
    details = confirmed_details(session, disc.name)
    by_path = {t.path: t for t in disc.titles}
    ordered = [by_path[path] for path in choices.order if path in by_path]
    options = art_options(ordered, details)
    chosen = front_file(settings.output_dir, disc.name) if choices.cover.front else None
    front = chosen or default_front(settings.output_dir, disc.name, ordered, details)
    _, backdrop = theme_image(choices, disc.name, settings.output_dir)
    return Cover(
        disc=disc, choices=choices, details=details, options=options, front=front,
        backdrop=backdrop, accent=resolve_accent(choices.theme.accent, backdrop),
        show_name=not _front_has_text(choices.cover, chosen, front, options, details,
                                      settings.output_dir, disc.name)
        if choices.cover.show_name is None else choices.cover.show_name,
        content=cover_content(choices, disc.titles, disc.name,
                              front is not None or backdrop is not None),
    )  # fmt: skip


@router.get("/folders/{name}/cover", response_class=HTMLResponse, name="cover_page")
def cover_page(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
) -> Response:
    disc = load_disc_page(session, media_dir, settings, name, folder)
    if disc is None:
        path = request.url_for("folder", name=name).path
        return RedirectResponse(path, status_code=303)
    cover = build_cover(session, settings, disc)
    return _render(request, "cover.html", cover, settings, tmdb=bool(settings.tmdb_token))


@router.post("/folders/{name}/cover/choices", response_class=HTMLResponse, name="cover_choices")
async def cover_choices(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
) -> Response:
    form = await read_form(request)
    disc = _disc_or_404(session, media_dir, settings, name, folder)
    current = saved_choices(disc).cover

    def text(field: str) -> str | None:
        return form.get(field, [""])[0].strip() or None

    try:
        cover = CoverChoices.model_validate({
            **current.model_dump(), "front_text": text("front_text"),
            "spine_text": text("spine_text"),
            "show_name": SHOW_NAME[form.get("show_name", ["auto"])[0]],
        })  # fmt: skip
    except (KeyError, ValidationError):
        return HTMLResponse(f'<p class="banner banner-error" role="alert">{INVALID_FORM}</p>')
    _save(session, disc, cover)
    return _results(request, session, settings, name, folder, media_dir)


@router.post("/folders/{name}/cover/art", response_class=HTMLResponse, name="cover_art")
async def cover_art(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
    tmdb: TmdbDep,
) -> Response:
    form = await read_form(request)
    disc = _disc_or_404(session, media_dir, settings, name, folder)
    cover = build_cover(session, settings, disc)
    path = form.get("file_path", [""])[0]
    if not path:  # back to the default front: nothing to download
        _save(session, disc, cover.choices.cover.model_copy(
            update={"front": None, "front_language": None, "show_name": None}))  # fmt: skip
        return _results(request, session, settings, name, folder, media_dir)
    option = next((o for o in cover.options if o.path == path), None)
    if option is None:
        raise HTTPException(status_code=400)

    def action(client: TmdbClient) -> str | None:
        return _download(client, option, settings.output_dir, name)

    failure, error = await run_in_threadpool(run_locked, session, tmdb, action)
    if not (failure or error):
        _save(session, disc, cover.choices.cover.model_copy(
            update={"front": option.path, "front_language": option.language,
                    "show_name": None}))  # fmt: skip
    return _results(request, session, settings, name, folder, media_dir, failure or error)


@router.get("/folders/{name}/cover/preview.png", name="cover_preview")
def cover_preview(
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
    page: int = 1,
) -> Response:
    disc = _disc_or_404(session, media_dir, settings, name, folder)
    if page not in (1, 2):
        raise HTTPException(status_code=404)
    image = _page(build_cover(session, settings, disc), page, PREVIEW_DPI)
    data = io.BytesIO()
    image.save(data, "PNG")
    return Response(data.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-cache"})  # fmt: skip


@router.post("/folders/{name}/cover/pdf", response_class=HTMLResponse, name="cover_pdf")
async def cover_pdf(
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
) -> Response:
    disc = _disc_or_404(session, media_dir, settings, name, folder)
    cover = build_cover(session, settings, disc)
    relative = f"print/{safe_name(name)}.pdf"
    message = await run_in_threadpool(_write, cover, settings.output_dir / relative)
    if message is None:
        shown = output_display(settings.host_output_dir, relative)
        return HTMLResponse(f'<p class="banner" role="status">PDF gravado em {_escape(shown)}.</p>')
    return HTMLResponse(f'<p class="banner banner-error" role="alert">{_escape(message)}</p>')


def _write(cover: Cover, target: Path) -> str | None:
    """Renders at 300 DPI (a few seconds) and writes the PDF; None when it worked."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return cannot_write("pasta de saída", target.parent.parent)
    if not os.access(target.parent, os.W_OK):
        return cannot_write("pasta de saída", target.parent.parent)
    dpi = render.PDF_DPI
    try:
        render.write_pdf(_page(cover, 1, dpi), _page(cover, 2, dpi), target)
    except PermissionError:  # the folder is writable: the old PDF is open in a Windows reader
        return PDF_OPEN
    except OSError:
        return cannot_write("pasta de saída", target.parent.parent)
    return None


def _page(cover: Cover, page: int, dpi: int) -> Image.Image:
    front = render.load_art(cover.front)
    if page == 1:
        return render.render_cover(cover.content, front, cover.backdrop, cover.accent,
                                   cover.show_name, dpi)  # fmt: skip
    return render.render_labels(cover.content, cover.backdrop, cover.accent, dpi)


def _download(client: TmdbClient, option: ArtOption, output_dir: Path, folder: str) -> str | None:
    """The art as the front of the folder; a message when it is not a JPEG or PNG image."""
    data = client.image(option.path)
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            kind = image.format
    except (OSError, SyntaxError, Image.DecompressionBombError):
        return ART_FAILED
    if kind not in ART_FORMATS:
        return ART_FAILED
    directory = output_dir / "covers" / safe_name(folder)
    try:
        save_art(data, directory / ART_FORMATS[kind])
        for other in FRONT_NAMES:
            if other != ART_FORMATS[kind]:
                (directory / other).unlink(missing_ok=True)
    except OSError:
        return cannot_write("pasta de saída", output_dir)
    return None


def _front_has_text(
    cover: CoverChoices, chosen: Path | None, front: Path | None, options: list[ArtOption],
    details: dict[str, Details], output_dir: Path, folder: str,
) -> bool:  # fmt: skip
    """A poster with a language carries its own title: the name does not go over it."""
    if front is None:
        return False
    if chosen is not None:
        kind = next((o.kind for o in options if o.path == cover.front), "poster")
        return kind == "poster" and cover.front_language is not None
    # The default front is the downloaded poster of one of the titles: which language is it?
    detail = next(d for d in details.values()
                  if title_art_dir(output_dir, folder, d) / "poster.jpg" == front)  # fmt: skip
    work = detail.movie if detail.kind == "movie" else detail.show
    languages = {i.file_path: i.iso_639_1 for i in work.images.posters}
    return work.poster_path not in languages or languages[work.poster_path] is not None


def _save(session: Session, disc: Disc, cover: CoverChoices) -> None:
    """The cover inside the saved disc choices; the Montar DVD page keeps it in turn."""
    choices = saved_choices(disc).model_copy(update={"cover": cover})
    project = session.get(DiscProject, disc.name) or DiscProject(folder=disc.name, choices_json="")
    project.choices_json = choices.model_dump_json()
    session.add(project)
    session.commit()


def _disc_or_404(
    session: Session, media_dir: Path, settings: Settings, name: str, folder: Path
) -> Disc:
    disc = load_disc_page(session, media_dir, settings, name, folder)
    if disc is None:
        raise HTTPException(status_code=404)
    return disc


def _results(
    request: Request, session: Session, settings: Settings, name: str, folder: Path,
    media_dir: Path, message: str | None = None,
) -> HTMLResponse:  # fmt: skip
    """The preview, the art grid and the message, swapped out of band after a change."""
    cover = build_cover(session, settings, _disc_or_404(session, media_dir, settings, name, folder))
    return _render(request, "_cover_results.html", cover, settings,
                   tmdb=bool(settings.tmdb_token), message=message, oob=True)  # fmt: skip


def _render(
    request: Request, template: str, cover: Cover, settings: Settings, *, tmdb: bool,
    message: str | None = None, oob: bool = False,
) -> HTMLResponse:  # fmt: skip
    plain = cover.choices.model_copy(update={"cover": CoverChoices()})
    automatic = cover_content(plain, cover.disc.titles, cover.disc.name, False)
    ordered = [t for t in cover.disc.titles if t.path in cover.choices.order]
    context = {
        "cover": cover, "disc": cover.disc, "choices": cover.choices,
        "automatic": automatic, "unmatched": sum(1 for t in ordered if t.info is None),
        "print_dpi": PRINT_DPI, "tmdb": tmdb, "message": message, "oob": oob,
        "pdf_path": output_display(settings.host_output_dir,
                                   f"print/{safe_name(cover.disc.name)}.pdf"),
    }  # fmt: skip
    return templates.TemplateResponse(request, template, context)


def _escape(text: str) -> str:
    return html.escape(text, quote=False)
