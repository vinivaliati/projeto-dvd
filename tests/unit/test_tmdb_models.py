from projeto_dvd.metadata.tmdb_models import (
    DETAILS,
    EpisodeDetails,
    Image,
    Movie,
    MovieDetails,
    SearchResult,
    Season,
    Show,
    year_of,
)
from tests.tmdb_fakes import MOVIE, SHOW, season


def test_year_of() -> None:
    assert year_of("2001-12-19") == 2001
    assert year_of("") is None
    assert year_of(None) is None
    assert year_of("abc") is None


def test_invalid_image_paths_become_none() -> None:
    for bad in ("../x.jpg", "https://evil/x.jpg", "/a/b.jpg", "/x.gif", 3, None):
        assert Image.model_validate({"file_path": bad}).file_path is None
    assert Image.model_validate({"file_path": "/abcXYZ09.png"}).file_path == "/abcXYZ09.png"
    assert Image.model_validate({"file_path": "/logo.svg"}).file_path == "/logo.svg"


def test_search_result_movie_and_show() -> None:
    movie = SearchResult.model_validate(
        {"id": 1, "title": "A", "original_title": "B", "release_date": ""}
    )
    show = SearchResult.model_validate(
        {"id": 2, "name": "C", "original_name": "D", "first_air_date": "1994-01-01"}
    )

    assert (movie.display_title, movie.original, movie.year) == ("A", "B", None)
    assert (show.display_title, show.original, show.year) == ("C", "D", 1994)


def test_full_answers_parse() -> None:
    movie = Movie.model_validate(MOVIE)
    show = Show.model_validate(SHOW)
    first = Season.model_validate(season())

    assert movie.belongs_to_collection is not None
    assert movie.belongs_to_collection.name == "Anel Mágico: Coleção"
    assert len(movie.credits.cast) == 7
    assert show.name == "Amigos de Sempre"
    assert first.episodes[2].still_path == "/still3.jpg"


def test_episode_air_date_can_be_null() -> None:
    data = season()
    data["episodes"][0]["air_date"] = None

    assert Season.model_validate(data).episodes[0].air_date is None


def test_details_round_trip() -> None:
    movie = MovieDetails(kind="movie", movie=Movie.model_validate(MOVIE))
    episode = EpisodeDetails(
        kind="episode",
        show=Show.model_validate(SHOW),
        episode=Season.model_validate(season()).episodes[0],
    )

    assert DETAILS.validate_json(DETAILS.dump_json(movie)) == movie
    assert DETAILS.validate_json(DETAILS.dump_json(episode)) == episode
