"""What the screens, menus and covers show about a confirmed title. Pure."""

import re
from typing import Literal

from pydantic import BaseModel

from projeto_dvd.metadata.filename import Kind
from projeto_dvd.metadata.tmdb_models import (
    Details,
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
    show_overview: str = ""  # the synopsis of the series, for the back of a season cover


def title_info(details: Details) -> TitleInfo:
    if details.kind == "movie":
        movie = details.movie
        collection = movie.belongs_to_collection
        return TitleInfo(
            kind="movie",
            tmdb_id=movie.id,
            title=_localized(movie.title, movie.original_language, movie.translations, "title"),
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
        show=_localized(show.name, show.original_language, show.translations, "name"),
        season=episode.season_number,
        episode=episode.episode_number,
        episode_end=details.episode_end.episode_number if details.episode_end else None,
        year=year_of(episode.air_date) or year_of(show.first_air_date),
        overview=episode.overview,
        cast=[member.name for member in show.credits.cast[:CAST]],
        runtime=episode.runtime,
        original_language=show.original_language,
        show_overview=show.overview or _english(show.translations).overview,
    )


def movie_label(title: str, year: int | None) -> str:
    return f"{title} ({year})" if year else title


def episode_label(show: str, season: int, episode: int, name: str) -> str:
    code = f"S{season:02d}E{episode:02d}"
    return f"{show} · {code} · {name}" if name else f"{show} · {code}"


def generic_episode_name(name: str) -> bool:
    """TMDB fills a missing pt-BR episode name with 'Episódio N'."""
    return not name.strip() or bool(_GENERIC_EPISODE.fullmatch(name.strip()))


def _localized(
    value: str, original_language: str, translations: Translations, field: Literal["title", "name"]
) -> str:
    """TMDB falls back to the original when there is no pt-BR text: prefer English then."""

    def text(data: TranslationData) -> str:
        return data.title if field == "title" else data.name

    if original_language == "pt" or any(
        t.iso_639_1 == "pt" and t.iso_3166_1 == "BR" and text(t.data)
        for t in translations.translations
    ):
        return value
    return text(_english(translations)) or value


def _english(translations: Translations) -> TranslationData:
    for translation in translations.translations:
        if translation.iso_639_1 == "en":
            return translation.data
    return _EMPTY
