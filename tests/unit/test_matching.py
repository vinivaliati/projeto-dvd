from collections.abc import Mapping

import httpx2
import pytest

from projeto_dvd.metadata.filename import Guess
from projeto_dvd.metadata.matching import (
    EPISODE_DURATION,
    MANY_GENERIC,
    MISSING_EPISODE,
    NO_EPISODE,
    NOTHING,
    SHORT_MOVIE,
    Lookup,
    Suggestion,
    suggest,
    suggest_folder,
)
from projeto_dvd.metadata.tmdb import TmdbClient, TmdbError
from tests.tmdb_fakes import router, search_page, season

RING = {"id": 101, "title": "Anel Mágico", "original_title": "The Magic Ring",
        "release_date": "2001-12-19", "poster_path": "/p.jpg"}  # fmt: skip
RING_REMAKE = {"id": 102, "title": "Anel Mágico", "release_date": "2019-01-01"}
FRIENDS = {"id": 202, "name": "Amigos de Sempre", "original_name": "Forever Friends",
           "first_air_date": "1994-09-22"}  # fmt: skip


def lookup(routes: Mapping[str, object], requests: list[httpx2.Request] | None = None) -> Lookup:
    transport = httpx2.MockTransport(router(routes, requests))
    return Lookup(TmdbClient("t", "pt-BR", transport=transport))


def movie(title: str, year: int | None = None, **kw: object) -> Guess:
    return Guess("movie", title, year, **kw)  # type: ignore[arg-type]


def test_exact_unique_title_is_suggested() -> None:
    found = suggest(movie("anel magico", 2001), 9000.0,
                    lookup({"/3/search/movie": search_page(RING, RING_REMAKE)}))  # fmt: skip

    assert found == Suggestion("suggested", "movie", 101, None, None, None,
                               "Anel Mágico (2001)", "/p.jpg", None)  # fmt: skip


def test_original_title_also_counts() -> None:
    found = suggest(movie("The Magic Ring"), 9000.0,
                    lookup({"/3/search/movie": search_page(RING)}))  # fmt: skip

    assert found.status == "suggested"


def test_two_with_the_same_name_without_year_is_doubtful() -> None:
    found = suggest(movie("Anel Mágico"), 9000.0,
                    lookup({"/3/search/movie": search_page(RING, RING_REMAKE)}))  # fmt: skip

    assert (found.status, found.tmdb_id) == ("doubtful", 101)


def test_year_that_does_not_match_is_doubtful() -> None:
    found = suggest(movie("Anel Mágico", 1950), 9000.0,
                    lookup({"/3/search/movie": search_page(RING)}))  # fmt: skip

    assert found.status == "doubtful"


def test_similar_name_is_doubtful() -> None:
    found = suggest(movie("Anel"), 9000.0, lookup({"/3/search/movie": search_page(RING)}))

    assert found.status == "doubtful"


def test_retries_without_year_then_the_folder() -> None:
    requests: list[httpx2.Request] = []
    empty = lookup({"/3/search/movie": search_page()}, requests)

    found = suggest(movie("xyz", 2001, fallback="Pasta"), None, empty)

    assert found.status == "not_found"
    assert found.message == NOTHING.format("xyz")
    assert [r.url.params["query"] for r in requests] == ["xyz", "xyz", "Pasta"]


def test_short_movie_is_doubtful() -> None:
    found = suggest(movie("Anel Mágico", 2001), 20 * 60.0,
                    lookup({"/3/search/movie": search_page(RING)}))  # fmt: skip

    assert (found.status, found.message) == ("doubtful", SHORT_MOVIE)


def test_episode_is_suggested_with_its_name() -> None:
    routes = {"/3/search/tv": search_page(FRIENDS), "/3/tv/202/season/1": season()}

    found = suggest(Guess("episode", "Forever Friends", None, 1, 3), 22 * 60.0, lookup(routes))

    assert found == Suggestion("suggested", "episode", 202, 1, 3, None,
                               "Amigos de Sempre · S01E03 · O Polegar", None, None)  # fmt: skip


def test_missing_episode_and_unknown_episode() -> None:
    routes = {"/3/search/tv": search_page(FRIENDS), "/3/tv/202/season/1": season()}

    missing = suggest(Guess("episode", "Forever Friends", None, 1, 9), None, lookup(routes))
    unknown = suggest(Guess("episode", "Forever Friends", None, 1, None), None, lookup(routes))

    assert (missing.status, missing.message) == ("doubtful", MISSING_EPISODE.format("S01E09"))
    assert (unknown.status, unknown.message) == ("doubtful", NO_EPISODE)


def test_missing_season_is_a_missing_episode() -> None:
    found = suggest(Guess("episode", "Forever Friends", None, 7, 1), None,
                    lookup({"/3/search/tv": search_page(FRIENDS)}))  # fmt: skip

    assert found.message == MISSING_EPISODE.format("S07E01")


def test_episode_duration_warning_keeps_the_status() -> None:
    routes = {"/3/search/tv": search_page(FRIENDS), "/3/tv/202/season/1": season()}

    found = suggest(Guess("episode", "Forever Friends", None, 1, 3), 44 * 60.0, lookup(routes))

    assert (found.status, found.message) == ("suggested", EPISODE_DURATION)


def test_lookup_caches_searches_and_seasons() -> None:
    requests: list[httpx2.Request] = []
    routes = {"/3/search/tv": search_page(FRIENDS), "/3/tv/202/season/1": season()}
    shared = lookup(routes, requests)

    for episode in (1, 2, 3):
        suggest(Guess("episode", "Forever Friends", None, 1, episode), None, shared)

    assert len(requests) == 2


def test_folder_with_several_generic_files() -> None:
    generic = movie("Anel Mágico", from_folder=True)
    files = [(1, generic, 9000.0), (2, generic, 9000.0), (3, movie("Anel Mágico", 2001), 9000.0)]

    found = suggest_folder(files, lookup({"/3/search/movie": search_page(RING)}))

    assert found[1].status == found[2].status == "not_found"
    assert found[1].message == MANY_GENERIC
    assert found[3].status == "suggested"


def test_other_season_errors_propagate() -> None:
    routes = {"/3/search/tv": search_page(FRIENDS), "/3/tv/202/season/1": 401}

    with pytest.raises(TmdbError):
        suggest(Guess("episode", "Forever Friends", None, 1, 3), None, lookup(routes))
