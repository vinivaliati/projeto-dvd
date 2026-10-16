"""What the screens, menus and covers show about a confirmed title. Pure."""

import re

from pydantic import BaseModel

from projeto_dvd.metadata.filename import Kind
from projeto_dvd.metadata.tmdb_models import (
    Details,
    Movie,
    TranslationData,
    Translations,
    year_of,
)

CAST = 5
_EMPTY = TranslationData()
_GENERIC_EPISODE = re.compile(r"(?:epis[oó]dio|episode) \d+", re.IGNORECASE)


class TitleInfo(BaseModel):
    kind: Kind
    tmdb_id: int
    title: str  # the movie title, or the episode name
    show: str | None = None
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None
    year: int | None = None
    overview: str = ""
    cast: list[str] = []
    runtime: int | None = None
    original_language: str = ""
    collection: str | None = None
    collection_id: int | None = None


def title_info(details: Details) -> TitleInfo:
    if details.kind == "movie":
        movie = details.movie
        collection = movie.belongs_to_collection
        return TitleInfo(
            kind="movie",
            tmdb_id=movie.id,
            title=_movie_title(movie),
            year=year_of(movie.release_date),
            overview=movie.overview or _english(movie.translations).overview,
            cast=[member.name for member in movie.credits.cast[:CAST]],
            runtime=movie.runtime,
            original_language=movie.original_language,
            collection=collection.name if collection else None,
            collection_id=collection.id if collection else None,
        )
    show, episode = details.show, details.episode
    return TitleInfo(
        kind="episode",
        tmdb_id=show.id,
        title=episode.name,
        show=show.name,
        season=episode.season_number,
        episode=episode.episode_number,
        episode_end=details.episode_end.episode_number if details.episode_end else None,
        year=year_of(episode.air_date) or year_of(show.first_air_date),
        overview=episode.overview,
        cast=[member.name for member in show.credits.cast[:CAST]],
        runtime=episode.runtime,
        original_language=show.original_language,
    )


def movie_label(title: str, year: int | None) -> str:
    return f"{title} ({year})" if year else title


def episode_label(show: str, season: int, episode: int, name: str) -> str:
    code = f"S{season:02d}E{episode:02d}"
    return f"{show} · {code} · {name}" if name else f"{show} · {code}"


def generic_episode_name(name: str) -> bool:
    """TMDB fills a missing pt-BR episode name with 'Episódio N'."""
    return not name.strip() or bool(_GENERIC_EPISODE.fullmatch(name.strip()))


def _movie_title(movie: Movie) -> str:
    """TMDB falls back to the original title when there is no pt-BR one: prefer English then."""
    if movie.original_language == "pt" or any(
        t.iso_639_1 == "pt" and t.iso_3166_1 == "BR" and t.data.title
        for t in movie.translations.translations
    ):
        return movie.title
    return _english(movie.translations).title or movie.title


def _english(translations: Translations) -> TranslationData:
    for translation in translations.translations:
        if translation.iso_639_1 == "en":
            return translation.data
    return _EMPTY
