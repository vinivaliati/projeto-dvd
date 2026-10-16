from pathlib import Path
from typing import Any

from projeto_dvd.metadata.art import (
    BACKDROP_TEXT,
    LOW_RES,
    ArtPick,
    episode_code,
    pick_art,
    save_art,
)
from projeto_dvd.metadata.tmdb_models import EpisodeDetails, Movie, MovieDetails, Season, Show
from tests.tmdb_fakes import MOVIE, SHOW, season


def movie(**changes: Any) -> MovieDetails:
    return MovieDetails(kind="movie", movie=Movie.model_validate({**MOVIE, **changes}))


def test_movie_picks() -> None:
    assert pick_art(movie()) == [
        ArtPick("poster.jpg", "/posterpt.jpg", None),
        ArtPick("backdrop.jpg", "/backnull2.jpg", None),  # no language beats more votes
        ArtPick("logo.png", "/logoen.png", None),  # the pt logo is .svg
    ]


def test_low_resolution_poster_and_backdrop_with_text() -> None:
    images = {
        "posters": [{"file_path": "/posterpt.jpg", "iso_639_1": "pt", "width": 600}],
        "backdrops": [{"file_path": "/backen.jpg", "iso_639_1": "en", "width": 1920}],
        "logos": [],
    }

    assert pick_art(movie(images=images)) == [
        ArtPick("poster.jpg", "/posterpt.jpg", LOW_RES),
        ArtPick("backdrop.jpg", "/backen.jpg", BACKDROP_TEXT),
    ]


def test_nothing_to_pick() -> None:
    images: dict[str, list[object]] = {"posters": [], "backdrops": [], "logos": []}

    assert pick_art(movie(poster_path=None, images=images)) == []


def test_episode_picks_show_art_and_the_still() -> None:
    details = EpisodeDetails(
        kind="episode",
        show=Show.model_validate(SHOW),
        episode=Season.model_validate(season()).episodes[2],
    )

    assert pick_art(details) == [
        ArtPick("poster.jpg", "/showposter.jpg", None),
        ArtPick("S01E03.jpg", "/still3.jpg", None),
    ]


def test_episode_code() -> None:
    assert episode_code(1, 3) == "S01E03"
    assert episode_code(0, 112) == "S00E112"


def test_save_art_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "a" / "poster.jpg"

    save_art(b"image", target)

    assert target.read_bytes() == b"image"
    assert not (tmp_path / "a" / "poster.jpg.part").exists()
