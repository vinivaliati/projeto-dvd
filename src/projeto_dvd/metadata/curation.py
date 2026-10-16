"""The database and disk side of the curation: network first, then a short transaction."""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, col, select

from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.jobs.pipeline import cannot_write
from projeto_dvd.library.probe import summarize
from projeto_dvd.metadata.art import episode_code, pick_art, save_art
from projeto_dvd.metadata.details import (
    episode_label,
    generic_episode_name,
    movie_label,
    title_info,
)
from projeto_dvd.metadata.filename import Guess, Kind, guess
from projeto_dvd.metadata.matching import MISSING_EPISODE, Lookup, suggest_folder
from projeto_dvd.metadata.names import art_dir
from projeto_dvd.metadata.tmdb import NOT_FOUND, TmdbClient, TmdbError
from projeto_dvd.metadata.tmdb_models import (
    DETAILS,
    Details,
    Episode,
    EpisodeDetails,
    MovieDetails,
)

MOVIE_DURATION = "Duração bem diferente da do TMDB: versão estendida ou filme errado?"
ART_FAILED = "Arte não baixada: "
MOVIE_TOLERANCE = 0.15


@dataclass(frozen=True)
class Choice:
    kind: Kind
    tmdb_id: int
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None


def file_guess(row: MediaFile, max_year: int) -> Guess:
    relative = row.path.split("/", 1)[1]
    return guess(relative, row.folder, max_year)


def run_suggestions(session: Session, folder: str, client: TmdbClient, max_year: int) -> int:
    rows = [row for row in _folder_rows(session, folder)
            if row.title is None or row.title.status != "confirmed"]  # fmt: skip
    files = [(_id(row), file_guess(row, max_year), _duration(row)) for row in rows]
    found = suggest_folder(files, Lookup(client))  # network; raises before any write
    for row in rows:
        s = found[_id(row)]
        title = row.title or Title(status=s.status, kind=s.kind)
        title.status, title.kind, title.tmdb_id = s.status, s.kind, s.tmdb_id
        title.season, title.episode, title.episode_end = s.season, s.episode, s.episode_end
        title.label, title.poster_path, title.message = s.label, s.poster_path, s.message
        title.tmdb_json = None
        row.title = title
    session.commit()
    return sum(1 for row in rows if found[_id(row)].status != "not_found")


def fetch_details(choice: Choice, client: TmdbClient) -> Details:
    if choice.kind == "movie":
        return MovieDetails(kind="movie", movie=client.movie(choice.tmdb_id))
    if choice.season is None or choice.episode is None:
        raise TmdbError(MISSING_EPISODE.format("?"))
    show = client.tv(choice.tmdb_id)
    episode = _episode(client, choice.tmdb_id, choice.season, choice.episode)
    end = None
    if choice.episode_end:
        end = _episode(client, choice.tmdb_id, choice.season, choice.episode_end)
    return EpisodeDetails(kind="episode", show=show, episode=episode, episode_end=end)


def confirm(
    session: Session, media_file_id: int, choice: Choice, client: TmdbClient, output_dir: Path
) -> Title:
    row = _row(session, media_file_id)
    details = fetch_details(choice, client)
    warnings = _save(details, row.folder, client, output_dir, overwrite=False)
    warnings += _duration_warning(details, _duration(row))
    title = row.title or Title(status="confirmed", kind=choice.kind)
    info = title_info(details)
    title.status, title.kind, title.tmdb_id = "confirmed", choice.kind, choice.tmdb_id
    title.season, title.episode, title.episode_end = info.season, info.episode, info.episode_end
    title.label = _label(details)
    title.poster_path = details.movie.poster_path if details.kind == "movie" else (
        details.show.poster_path
    )  # fmt: skip
    title.message = " ".join(warnings) or None
    title.tmdb_json = DETAILS.dump_json(details).decode()
    row.title = title
    session.commit()
    return title


def confirm_all(session: Session, folder: str, client: TmdbClient, output_dir: Path) -> int:
    rows = [r for r in _folder_rows(session, folder) if r.title and r.title.status == "suggested"]
    for row in rows:
        assert row.title is not None
        title = row.title
        assert title.tmdb_id is not None
        kind: Kind = "episode" if title.kind == "episode" else "movie"
        choice = Choice(kind, title.tmdb_id, title.season, title.episode, title.episode_end)
        confirm(session, _id(row), choice, client, output_dir)  # one commit per title
    return len(rows)


def download_again(
    session: Session, media_file_id: int, client: TmdbClient, output_dir: Path
) -> Title:
    row = _row(session, media_file_id)
    title = row.title
    if title is None or title.tmdb_json is None:
        raise TmdbError(NOT_FOUND)
    details = DETAILS.validate_json(title.tmdb_json)
    warnings = _save(details, row.folder, client, output_dir, overwrite=True)
    title.message = " ".join(warnings) or None
    session.commit()
    return title


def confirmed_counts(session: Session) -> dict[str, int]:
    query = (
        select(MediaFile.folder, func.count())
        .join(Title)
        .where(Title.status == "confirmed")
        .group_by(MediaFile.folder)
    )
    return {folder: count for folder, count in session.exec(query).all()}


def original_language(session: Session, path: str) -> str | None:
    row = session.exec(select(MediaFile).where(MediaFile.path == path)).first()
    if row is None or row.title is None or row.title.tmdb_json is None:
        return None
    if row.title.status != "confirmed":
        return None
    return title_info(DETAILS.validate_json(row.title.tmdb_json)).original_language or None


def _save(
    details: Details, folder: str, client: TmdbClient, output_dir: Path, overwrite: bool
) -> list[str]:
    """Art and metadata.json; failures become warnings, never undo the confirmation."""
    info = title_info(details)
    if details.kind == "movie":
        name, metadata = movie_label(info.title, info.year), "metadata.json"
    else:
        code = episode_code(details.episode.season_number, details.episode.episode_number)
        name, metadata = details.show.name, f"{code}.json"
    warnings: list[str] = []
    try:
        directory = art_dir(output_dir, folder, name)
        directory.mkdir(parents=True, exist_ok=True)
        save_art(info.model_dump_json(indent=2).encode(), directory / metadata)
    except (OSError, ValueError):
        return [cannot_write("pasta de saída", output_dir)]
    for pick in pick_art(details):
        if pick.warning:
            warnings.append(pick.warning)
        target = directory / pick.name
        if target.exists() and not overwrite:
            continue
        try:
            save_art(client.image(pick.path), target)
        except TmdbError as error:
            warnings.append(f"{ART_FAILED}{pick.name} ({error.message})")
        except OSError:
            warnings.append(cannot_write("pasta de saída", output_dir))
            break
    return warnings


def _episode(client: TmdbClient, tv_id: int, season: int, number: int) -> Episode:
    code = episode_code(season, number)
    try:
        episodes = client.season(tv_id, season).episodes
    except TmdbError as error:
        if error.message != NOT_FOUND:
            raise
        raise TmdbError(MISSING_EPISODE.format(code)) from None
    episode = next((e for e in episodes if e.episode_number == number), None)
    if episode is None:
        raise TmdbError(MISSING_EPISODE.format(code))
    if generic_episode_name(episode.name) or not episode.overview:
        english = client.season(tv_id, season, language="en-US").episodes
        en = next((e for e in english if e.episode_number == number), None)
        if en is not None:
            episode = episode.model_copy(update={
                "name": en.name if generic_episode_name(episode.name) else episode.name,
                "overview": episode.overview or en.overview,
            })  # fmt: skip
    return episode


def _label(details: Details) -> str:
    info = title_info(details)
    if details.kind == "movie":
        return movie_label(info.title, info.year)
    assert info.season is not None and info.episode is not None
    return episode_label(details.show.name, info.season, info.episode, info.title)


def _duration_warning(details: Details, duration: float | None) -> list[str]:
    runtime = details.movie.runtime if details.kind == "movie" else None
    if duration and runtime and abs(duration / 60 - runtime) > MOVIE_TOLERANCE * runtime:
        return [MOVIE_DURATION]
    return []


def _folder_rows(session: Session, folder: str) -> list[MediaFile]:
    query = select(MediaFile).where(MediaFile.folder == folder).order_by(col(MediaFile.path))
    return list(session.exec(query).all())


def _row(session: Session, media_file_id: int) -> MediaFile:
    row = session.get(MediaFile, media_file_id)
    if row is None:
        raise LookupError(media_file_id)
    return row


def _id(row: MediaFile) -> int:
    assert row.id is not None
    return row.id


def _duration(row: MediaFile) -> float | None:
    if row.probe_json is None:
        return None
    return summarize(json.loads(row.probe_json)).duration
