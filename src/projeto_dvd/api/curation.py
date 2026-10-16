"""TMDB match on the folder page. Errors come back inside the fragment, with status 200.

HTMX 2 does not swap error responses, so a 4xx/5xx would leave the Vini looking at a button
that did nothing. Routes that read a form are async (the body), and run the TMDB calls in the
thread pool so the network never blocks the event loop.
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from projeto_dvd.api.deps import (
    FolderDep,
    MediaDirDep,
    SessionDep,
    SettingsDep,
    TmdbDep,
    templates,
)
from projeto_dvd.config import Settings
from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.library.scan import FolderView, folder_view
from projeto_dvd.metadata.curation import (
    ART_FAILED,
    Choice,
    confirm,
    confirm_all,
    download_again,
    file_guess,
    run_suggestions,
)
from projeto_dvd.metadata.filename import Guess, Kind
from projeto_dvd.metadata.tmdb import TmdbClient, TmdbError
from projeto_dvd.metadata.tmdb_models import SearchResult

router = APIRouter()

# One TMDB action at a time (per process; one uvicorn worker): two clicks would write the
# same rows.
_tmdb_lock = threading.Lock()
BUSY = "Já existe uma busca no TMDB em andamento. Aguarde ela terminar."
INVALID_FORM = "Formulário inválido. Recarregue a página e tente de novo."
DISABLED = "Curadoria desligada: coloque o token em TMDB_TOKEN no .env."
MAX_RESULTS = 10


@dataclass(frozen=True)
class Card:
    file_id: int
    name: str  # path inside the disc folder
    title: Title | None
    guess: Guess

    @property
    def status(self) -> str:
        return self.title.status if self.title else "new"

    @property
    def art_failed(self) -> bool:
        return bool(self.title and self.title.message and ART_FAILED in self.title.message)

    @property
    def choice_json(self) -> str:
        """The suggestion as form values, for the "Confirmar" button."""
        assert self.title is not None
        values = {
            "kind": self.title.kind,
            "tmdb_id": self.title.tmdb_id,
            "season": self.title.season,
            "episode": self.title.episode,
            "episode_end": self.title.episode_end,
        }
        return json.dumps({k: "" if v is None else str(v) for k, v in values.items()})


@dataclass(frozen=True)
class Query:
    kind: Kind
    q: str
    year: int | None
    season: int | None
    episode: int | None


def tmdb_enabled(settings: Settings) -> bool:
    return bool(settings.tmdb_token and settings.tmdb_token.get_secret_value())


def tmdb_context(
    session: Session,
    view: FolderView,
    enabled: bool,
    banner: str | None = None,
    error: str | None = None,
) -> dict[str, object]:
    return {"enabled": enabled, "cards": _cards(session, view), "banner": banner, "error": error}


@router.post("/folders/{name}/match", response_class=HTMLResponse, name="match_folder")
def match_folder(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    tmdb: TmdbDep,
) -> HTMLResponse:
    def action(client: TmdbClient) -> None:
        run_suggestions(session, name, client, _max_year())

    return _folder_action(request, name, folder, session, media_dir, tmdb, action)


@router.post("/folders/{name}/confirm", response_class=HTMLResponse, name="confirm_folder")
def confirm_folder(
    request: Request,
    name: str,
    folder: FolderDep,
    session: SessionDep,
    media_dir: MediaDirDep,
    settings: SettingsDep,
    tmdb: TmdbDep,
) -> HTMLResponse:
    def action(client: TmdbClient) -> str:
        count = confirm_all(session, name, client, settings.output_dir)
        plural = "s" if count != 1 else ""
        return f"{count} título{plural} confirmado{plural}."

    return _folder_action(request, name, folder, session, media_dir, tmdb, action)


@router.get("/files/{file_id}/card", response_class=HTMLResponse, name="title_card")
def title_card(request: Request, file_id: int, session: SessionDep, tmdb: TmdbDep) -> HTMLResponse:
    return _render_card(request, session, file_id, tmdb is not None, None)


@router.post("/files/{file_id}/search", response_class=HTMLResponse, name="search_title")
async def search_title(
    request: Request, file_id: int, session: SessionDep, tmdb: TmdbDep
) -> HTMLResponse:
    form = await _form(request)
    return await run_in_threadpool(_search, request, session, file_id, tmdb, form)


@router.post("/files/{file_id}/choose", response_class=HTMLResponse, name="choose_title")
async def choose_title(
    request: Request, file_id: int, session: SessionDep, settings: SettingsDep, tmdb: TmdbDep
) -> HTMLResponse:
    form = await _form(request)
    choice = _choice(form)

    def action(client: TmdbClient) -> None:
        if choice is None:
            raise TmdbError(INVALID_FORM)
        confirm(session, file_id, choice, client, settings.output_dir)

    return await run_in_threadpool(_card_action, request, session, file_id, tmdb, action)


@router.post("/files/{file_id}/art", response_class=HTMLResponse, name="title_art")
def title_art(
    request: Request, file_id: int, session: SessionDep, settings: SettingsDep, tmdb: TmdbDep
) -> HTMLResponse:
    def action(client: TmdbClient) -> None:
        download_again(session, file_id, client, settings.output_dir)

    return _card_action(request, session, file_id, tmdb, action)


def _folder_action(
    request: Request,
    name: str,
    folder: FolderDep,
    session: Session,
    media_dir: MediaDirDep,
    tmdb: TmdbClient | None,
    action: Callable[[TmdbClient], str | None],
) -> HTMLResponse:
    banner, error = _locked(session, tmdb, action)
    view = folder_view(session, media_dir, name, folder)
    context = {"folder": view, "tmdb": tmdb_context(session, view, tmdb is not None, banner, error)}
    return templates.TemplateResponse(request, "_tmdb_section.html", context)


def _card_action(
    request: Request,
    session: Session,
    file_id: int,
    tmdb: TmdbClient | None,
    action: Callable[[TmdbClient], None],
) -> HTMLResponse:
    _row(session, file_id)  # 404 before any TMDB call
    _, error = _locked(session, tmdb, action)
    return _render_card(request, session, file_id, tmdb is not None, error)


def _locked(
    session: Session, tmdb: TmdbClient | None, action: Callable[[TmdbClient], str | None]
) -> tuple[str | None, str | None]:
    """(banner, error) of running one TMDB action under the lock."""
    if tmdb is None:
        return None, DISABLED
    if not _tmdb_lock.acquire(blocking=False):
        return None, BUSY
    try:
        return action(tmdb), None
    except TmdbError as failure:
        session.rollback()
        return None, failure.message
    finally:
        _tmdb_lock.release()


def _search(
    request: Request,
    session: Session,
    file_id: int,
    tmdb: TmdbClient | None,
    form: dict[str, list[str]],
) -> HTMLResponse:
    card = _card(_row(session, file_id))
    query = _query(form, card.guess)
    results: list[SearchResult] = []
    error = None
    if tmdb is None:
        error = DISABLED
    elif query is None:
        error = INVALID_FORM
    else:
        try:
            find = tmdb.search_movie if query.kind == "movie" else tmdb.search_tv
            results = find(query.q, query.year)[:MAX_RESULTS]
        except TmdbError as failure:
            error = failure.message
    context = {
        "card": card,
        "query": query or _guess_query(card.guess),
        "results": results,
        "card_error": error,
    }
    return templates.TemplateResponse(request, "_title_search.html", context)


def _render_card(
    request: Request, session: Session, file_id: int, enabled: bool, error: str | None
) -> HTMLResponse:
    row = _row(session, file_id)
    session.refresh(row)
    context = {"card": _card(row), "enabled": enabled, "card_error": error}
    return templates.TemplateResponse(request, "_title_card.html", context)


def _cards(session: Session, view: FolderView) -> list[Card]:
    query = select(MediaFile).where(MediaFile.folder == view.name)
    rows = {row.path: row for row in session.exec(query).all()}
    return [_card(rows[f.video.path]) for f in view.files if f.video.path in rows]


def _card(row: MediaFile) -> Card:
    assert row.id is not None
    return Card(row.id, row.path.split("/", 1)[1], row.title, file_guess(row, _max_year()))


def _row(session: Session, file_id: int) -> MediaFile:
    row = session.get(MediaFile, file_id)
    if row is None:
        raise HTTPException(status_code=404)
    return row


def _max_year() -> int:
    return date.today().year + 1


async def _form(request: Request) -> dict[str, list[str]]:
    """The urlencoded form; parsed here so python-multipart is not needed for a few fields."""
    return parse_qs((await request.body()).decode(), keep_blank_values=True)


def _guess_query(guess: Guess) -> Query:
    return Query(guess.kind, guess.title, guess.year, guess.season, guess.episode)


def _query(form: dict[str, list[str]], guess: Guess) -> Query | None:
    """The guess when the form is empty (Corrigir just opened); None on a bad value."""
    if not form:
        return _guess_query(guess)
    try:
        q = _one(form, "q")
        if not q:
            return None
        kind = _kind(_one(form, "kind"))
        return Query(kind, q, _opt(form, "year"), _opt(form, "season"), _opt(form, "episode"))
    except ValueError:
        return None


def _choice(form: dict[str, list[str]]) -> Choice | None:
    try:
        return Choice(
            _kind(_one(form, "kind")),
            int(_one(form, "tmdb_id")),
            _opt(form, "season"),
            _opt(form, "episode"),
            _opt(form, "episode_end"),
        )
    except ValueError:
        return None


def _one(form: dict[str, list[str]], name: str) -> str:
    return form.get(name, [""])[0].strip()


def _opt(form: dict[str, list[str]], name: str) -> int | None:
    value = _one(form, name)
    return int(value) if value else None


def _kind(value: str) -> Kind:
    if value == "movie":
        return "movie"
    if value == "episode":
        return "episode"
    raise ValueError(value)
