"""The TMDB answers the app reads, and the details stored for a confirmed title.

Only the fields used are declared (the rest is ignored). Image paths that do not look like a
TMDB file become None, so nothing odd ever reaches a download URL.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter

IMAGE_PATH = re.compile(r"/[A-Za-z0-9]+\.(?:jpg|png|svg)")


def _image_path(value: object) -> str | None:
    return value if isinstance(value, str) and IMAGE_PATH.fullmatch(value) else None


ImagePath = Annotated[str | None, BeforeValidator(_image_path)]


def year_of(date: str | None) -> int | None:
    """'2001-12-19' -> 2001; TMDB sends '' (or null) when it does not know."""
    if date and len(date) >= 4 and date[:4].isdecimal():
        return int(date[:4])
    return None


class Image(BaseModel):
    file_path: ImagePath = None
    iso_639_1: str | None = None
    vote_average: float = 0.0
    width: int = 0


class Images(BaseModel):
    posters: list[Image] = []
    backdrops: list[Image] = []
    logos: list[Image] = []


class TranslationData(BaseModel):
    title: str = ""
    name: str = ""
    overview: str = ""


class Translation(BaseModel):
    iso_639_1: str
    iso_3166_1: str
    data: TranslationData


class Translations(BaseModel):
    translations: list[Translation] = []


class CastMember(BaseModel):
    name: str


class Credits(BaseModel):
    cast: list[CastMember] = []


class CollectionRef(BaseModel):
    id: int
    name: str


class SearchResult(BaseModel):
    id: int
    title: str = ""
    original_title: str = ""
    name: str = ""
    original_name: str = ""
    release_date: str = ""
    first_air_date: str = ""
    overview: str = ""
    poster_path: ImagePath = None

    @property
    def display_title(self) -> str:
        return self.title or self.name

    @property
    def original(self) -> str:
        return self.original_title or self.original_name

    @property
    def year(self) -> int | None:
        return year_of(self.release_date or self.first_air_date)


class SearchPage(BaseModel):
    results: list[SearchResult] = []


class Movie(BaseModel):
    id: int
    title: str
    original_title: str = ""
    original_language: str = ""
    overview: str = ""
    release_date: str = ""
    runtime: int | None = None
    poster_path: ImagePath = None
    belongs_to_collection: CollectionRef | None = None
    credits: Credits = Credits()
    images: Images = Images()
    translations: Translations = Translations()


class Show(BaseModel):
    id: int
    name: str
    original_name: str = ""
    original_language: str = ""
    overview: str = ""
    first_air_date: str = ""
    poster_path: ImagePath = None
    credits: Credits = Credits()
    images: Images = Images()
    translations: Translations = Translations()


class Episode(BaseModel):
    season_number: int
    episode_number: int
    name: str = ""
    overview: str = ""
    air_date: str | None = None
    runtime: int | None = None
    still_path: ImagePath = None


class Season(BaseModel):
    season_number: int
    episodes: list[Episode] = []


class MovieDetails(BaseModel):
    kind: Literal["movie"]
    movie: Movie


class EpisodeDetails(BaseModel):
    kind: Literal["episode"]
    show: Show
    episode: Episode
    episode_end: Episode | None = None


Details = Annotated[MovieDetails | EpisodeDetails, Field(discriminator="kind")]
DETAILS: TypeAdapter[Details] = TypeAdapter(Details)
