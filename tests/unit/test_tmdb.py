from collections.abc import Mapping

import httpx2
import pytest

from projeto_dvd.metadata.tmdb import (
    BAD_ANSWER,
    BAD_IMAGE,
    MAX_IMAGE_BYTES,
    NOT_FOUND,
    OFFLINE,
    RATE_LIMITED,
    TOKEN_REFUSED,
    TmdbClient,
    TmdbError,
)
from tests.tmdb_fakes import MOVIE, SHOW, router, search_page, season

TOKEN = "secret-token-123"


def client(
    routes: Mapping[str, object], requests: list[httpx2.Request] | None = None
) -> TmdbClient:
    return TmdbClient(TOKEN, "pt-BR", transport=httpx2.MockTransport(router(routes, requests)))


def test_search_movie_sends_bearer_language_and_year() -> None:
    requests: list[httpx2.Request] = []
    routes = {"/3/search/movie": search_page({"id": 1, "title": "Anel"})}

    with client(routes, requests) as tmdb:
        results = tmdb.search_movie("Anel", 2001)

    assert [r.id for r in results] == [1]
    request = requests[0]
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert dict(request.url.params) == {"query": "Anel", "year": "2001", "language": "pt-BR"}
    assert TOKEN not in str(request.url)


def test_search_tv_uses_first_air_date_year() -> None:
    requests: list[httpx2.Request] = []

    with client({"/3/search/tv": search_page()}, requests) as tmdb:
        assert tmdb.search_tv("Amigos", 1994) == []
        tmdb.search_tv("Amigos", None)

    assert requests[0].url.params["first_air_date_year"] == "1994"
    assert "first_air_date_year" not in requests[1].url.params


def test_details_ask_for_credits_images_and_translations() -> None:
    requests: list[httpx2.Request] = []
    routes = {"/3/movie/101": MOVIE, "/3/tv/202": SHOW}

    with client(routes, requests) as tmdb:
        assert tmdb.movie(101).title == "Anel Mágico"
        assert tmdb.tv(202).name == "Amigos de Sempre"

    for request in requests:
        assert request.url.params["append_to_response"] == "credits,images,translations"
        assert request.url.params["include_image_language"] == "pt,en,null"


def test_season_in_another_language() -> None:
    routes = {"/3/tv/202/season/1": season(), "/3/tv/202/season/1?language=en-US": season("en")}

    with client(routes) as tmdb:
        assert tmdb.season(202, 1).episodes[1].name == "Episódio 2"
        assert tmdb.season(202, 1, language="en-US").episodes[1].name == "The Middle"


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, TOKEN_REFUSED), (404, NOT_FOUND), (429, RATE_LIMITED)],
)
def test_http_errors(status: int, message: str) -> None:
    with client({"/3/movie/1": status}) as tmdb, pytest.raises(TmdbError) as error:
        tmdb.movie(1)

    assert error.value.message == message
    assert TOKEN not in str(error.value)


def test_other_status() -> None:
    with client({"/3/movie/1": 500}) as tmdb, pytest.raises(TmdbError) as error:
        tmdb.movie(1)

    assert error.value.message == "O TMDB respondeu com erro 500. Tente de novo mais tarde."


def test_network_errors() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    def slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    for handler in (fail, slow):
        with (
            TmdbClient(TOKEN, "pt-BR", transport=httpx2.MockTransport(handler)) as tmdb,
            pytest.raises(TmdbError) as error,
        ):
            tmdb.search_movie("x", None)
        assert error.value.message == OFFLINE
        assert error.value.__cause__ is None


def test_unexpected_answer() -> None:
    with client({"/3/movie/1": {"nothing": True}}) as tmdb, pytest.raises(TmdbError) as error:
        tmdb.movie(1)

    assert error.value.message == BAD_ANSWER


def test_image_download_without_token() -> None:
    requests: list[httpx2.Request] = []

    with client({"/t/p/original/poster.jpg": b"jpeg"}, requests) as tmdb:
        assert tmdb.image("/poster.jpg") == b"jpeg"

    assert str(requests[0].url) == "https://image.tmdb.org/t/p/original/poster.jpg"
    assert "Authorization" not in requests[0].headers


def test_image_refuses_odd_paths_types_and_sizes() -> None:
    def text(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"<html>", headers={"Content-Type": "text/html"})

    def huge(request: httpx2.Request) -> httpx2.Response:
        body = b"x" * (MAX_IMAGE_BYTES + 1)
        return httpx2.Response(200, content=body, headers={"Content-Type": "image/jpeg"})

    def moved(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"Location": "http://169.254.169.254/"})

    with client({}) as tmdb, pytest.raises(TmdbError) as error:
        tmdb.image("../etc/passwd")
    assert error.value.message == BAD_IMAGE
    for handler in (text, huge, moved):
        with (
            TmdbClient(TOKEN, "pt-BR", transport=httpx2.MockTransport(handler)) as tmdb,
            pytest.raises(TmdbError) as error,
        ):
            tmdb.image("/a.jpg")
        assert error.value.message == BAD_IMAGE


def test_image_network_error() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    with (
        TmdbClient(TOKEN, "pt-BR", transport=httpx2.MockTransport(fail)) as tmdb,
        pytest.raises(TmdbError) as error,
    ):
        tmdb.image("/a.jpg")

    assert error.value.message == OFFLINE
