from typing import Any

from projeto_dvd.metadata.details import (
    episode_label,
    generic_episode_name,
    movie_label,
    title_info,
)
from projeto_dvd.metadata.tmdb_models import (
    DETAILS,
    EpisodeDetails,
    Image,
    Movie,
    MovieDetails,
    Season,
    Show,
)
from tests.tmdb_fakes import MOVIE, SHOW, season


def movie(**changes: Any) -> MovieDetails:
    return MovieDetails(kind="movie", movie=Movie.model_validate({**MOVIE, **changes}))


def test_movie_info() -> None:
    info = title_info(movie())

    assert info.title == "Anel Mágico"
    assert info.year == 2001
    assert info.cast == ["Ator 1", "Ator 2", "Ator 3", "Ator 4", "Ator 5"]
    assert info.runtime == 178
    assert info.original_language == "en"
    assert (info.collection, info.collection_id) == ("Anel Mágico: Coleção", 900)
    assert info.show is None


def test_movie_without_portuguese_translation_uses_english() -> None:
    translations = {"translations": [MOVIE["translations"]["translations"][1]]}

    info = title_info(movie(title="The Magic Ring", overview="", translations=translations))

    assert info.title == "The Magic Ring"
    assert info.overview == "A ring and a journey."


def test_brazilian_movie_keeps_its_title() -> None:
    info = title_info(movie(title="Cidade", original_language="pt", translations={}))

    assert info.title == "Cidade"


def test_episode_info() -> None:
    details = EpisodeDetails(
        kind="episode",
        show=Show.model_validate(SHOW),
        episode=Season.model_validate(season()).episodes[2],
    )

    info = title_info(details)

    assert (info.kind, info.show, info.season, info.episode) == (
        "episode",
        "Amigos de Sempre",
        1,
        3,
    )
    assert info.title == "O Polegar"
    assert info.runtime == 22
    assert info.year == 1994
    assert info.cast == ["Atriz A", "Ator B"]


def test_labels() -> None:
    assert movie_label("Anel", 2001) == "Anel (2001)"
    assert movie_label("Anel", None) == "Anel"
    assert episode_label("Amigos", 1, 3, "O Polegar") == "Amigos · S01E03 · O Polegar"
    assert episode_label("Amigos", 0, 12, "") == "Amigos · S00E12"


def test_generic_episode_name() -> None:
    assert generic_episode_name("Episódio 2")
    assert generic_episode_name("Episode 12")
    assert generic_episode_name("")
    assert not generic_episode_name("O Polegar")


def test_movie_without_any_translation_keeps_what_tmdb_sent() -> None:
    other = {"iso_639_1": "fr", "iso_3166_1": "FR", "data": {"title": "L'Anneau"}}

    info = title_info(movie(title="The Magic Ring", translations={"translations": [other]}))

    assert info.title == "The Magic Ring"


def test_show_without_portuguese_translation_uses_english() -> None:
    translations = {"translations": [
        {"iso_639_1": "en", "iso_3166_1": "US", "data": {"name": "Forever Friends"}}]}  # fmt: skip
    show = Show.model_validate({**SHOW, "name": "영원한 친구", "original_language": "ko",
                                "translations": translations})  # fmt: skip
    details = EpisodeDetails(kind="episode", show=show,
                             episode=Season.model_validate(season()).episodes[2])  # fmt: skip

    assert title_info(details).show == "Forever Friends"


def test_show_overview_in_portuguese_or_english() -> None:
    episode = Season.model_validate(season()).episodes[0]
    pt = EpisodeDetails(kind="episode", show=Show.model_validate(SHOW), episode=episode)
    english = {"iso_639_1": "en", "iso_3166_1": "US", "data": {"overview": "Six friends."}}
    empty = {**SHOW, "overview": "", "translations": {"translations": [english]}}
    en = EpisodeDetails(kind="episode", show=Show.model_validate(empty), episode=episode)

    assert title_info(pt).show_overview == "Seis amigos."
    assert title_info(en).show_overview == "Six friends."


def test_old_details_without_the_new_fields_still_load() -> None:
    movie_json: dict[str, Any] = {**MOVIE, "belongs_to_collection": {"id": 9, "name": "C"}}
    details = DETAILS.validate_python({"kind": "movie", "movie": movie_json})
    assert details.kind == "movie" and details.movie.belongs_to_collection is not None
    assert details.movie.belongs_to_collection.poster_path is None
    with_poster = {**movie_json, "belongs_to_collection": {"id": 9, "name": "C",
                                                             "poster_path": "/c.jpg"}}  # fmt: skip
    movie = DETAILS.validate_python({"kind": "movie", "movie": with_poster})
    assert movie.kind == "movie" and movie.movie.belongs_to_collection is not None
    assert movie.movie.belongs_to_collection.poster_path == "/c.jpg"
    assert (
        Image.model_validate({"file_path": "/a.jpg", "width": 2000, "height": 3000}).height == 3000
    )
