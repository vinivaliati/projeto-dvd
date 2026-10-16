"""Invented TMDB answers and a MockTransport router. Never real responses."""

import json
from collections.abc import Callable, Mapping
from typing import Any

import httpx2

MOVIE: dict[str, Any] = {
    "id": 101,
    "title": "Anel Mágico",
    "original_title": "The Magic Ring",
    "original_language": "en",
    "overview": "Um anel e uma viagem.",
    "release_date": "2001-12-19",
    "runtime": 178,
    "poster_path": "/posterpt.jpg",
    "belongs_to_collection": {"id": 900, "name": "Anel Mágico: Coleção"},
    "credits": {"cast": [{"name": f"Ator {i}"} for i in range(1, 8)]},
    "images": {
        "posters": [{"file_path": "/posterpt.jpg", "iso_639_1": "pt", "vote_average": 5.0,
                     "width": 2000}],
        "backdrops": [
            {"file_path": "/backen.jpg", "iso_639_1": "en", "vote_average": 9.0, "width": 3840},
            {"file_path": "/backnull.jpg", "iso_639_1": None, "vote_average": 5.0, "width": 1920},
            {"file_path": "/backnull2.jpg", "iso_639_1": None, "vote_average": 5.0,
             "width": 3840},
        ],
        "logos": [
            {"file_path": "/logopt.svg", "iso_639_1": "pt", "vote_average": 9.0, "width": 500},
            {"file_path": "/logoen.png", "iso_639_1": "en", "vote_average": 5.0, "width": 500},
        ],
    },
    "translations": {
        "translations": [
            {"iso_639_1": "pt", "iso_3166_1": "BR",
             "data": {"title": "Anel Mágico", "overview": "Um anel e uma viagem."}},
            {"iso_639_1": "en", "iso_3166_1": "US",
             "data": {"title": "The Magic Ring", "overview": "A ring and a journey."}},
        ]
    },
}  # fmt: skip

SHOW: dict[str, Any] = {
    "id": 202,
    "name": "Amigos de Sempre",
    "original_name": "Forever Friends",
    "original_language": "en",
    "overview": "Seis amigos.",
    "first_air_date": "1994-09-22",
    "poster_path": "/showposter.jpg",
    "credits": {"cast": [{"name": "Atriz A"}, {"name": "Ator B"}]},
    "images": {"posters": [], "backdrops": [], "logos": []},
    "translations": {"translations": []},
}


def season(language: str = "pt-BR") -> dict[str, Any]:
    names = {1: "O Começo", 2: "Episódio 2", 3: "O Polegar"}
    en = {1: "The Start", 2: "The Middle", 3: "The Thumb"}
    return {
        "season_number": 1,
        "episodes": [
            {"season_number": 1, "episode_number": n,
             "name": en[n] if language.startswith("en") else names[n],
             "overview": "" if n == 2 and not language.startswith("en") else f"Resumo {n}",
             "air_date": "1994-09-22", "runtime": 22, "still_path": f"/still{n}.jpg"}
            for n in (1, 2, 3)
        ],
    }  # fmt: skip


def search_page(*results: dict[str, Any]) -> dict[str, Any]:
    return {"page": 1, "results": list(results)}


Handler = Callable[[httpx2.Request], httpx2.Response]


def router(routes: Mapping[str, Any], requests: list[httpx2.Request] | None = None) -> Handler:
    """Answer by URL path: a dict becomes JSON 200, an int becomes that status, bytes an image."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        key = request.url.path
        language = request.url.params.get("language", "")
        answer = routes.get(f"{key}?language={language}", routes.get(key, 404))
        if isinstance(answer, int):
            return httpx2.Response(answer, json={"status_message": "x"})
        if isinstance(answer, bytes):
            return httpx2.Response(200, content=answer, headers={"Content-Type": "image/jpeg"})
        return httpx2.Response(200, content=json.dumps(answer).encode())

    return handle
