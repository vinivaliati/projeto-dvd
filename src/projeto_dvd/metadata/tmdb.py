"""A small TMDB v3 client. The token goes in the Authorization header, never in a URL."""

from types import TracebackType
from typing import TypeVar

import httpx2
from pydantic import BaseModel, ValidationError

from projeto_dvd.metadata.tmdb_models import (
    IMAGE_PATH,
    Movie,
    SearchPage,
    SearchResult,
    Season,
    Show,
)

API = "https://api.themoviedb.org/3"
IMAGES = "https://image.tmdb.org/t/p/original"
MAX_IMAGE_BYTES = 30 * 1024 * 1024
DETAILS_PARAMS = {
    "append_to_response": "credits,images,translations",
    "include_image_language": "pt,en,null",
}

TOKEN_REFUSED = "O TMDB recusou o token. Confira TMDB_TOKEN no .env."
NOT_FOUND = "O TMDB não encontrou esse título."
RATE_LIMITED = "O TMDB pediu para esperar. Tente de novo em alguns segundos."
OFFLINE = "Não foi possível falar com o TMDB (sem internet ou fora do ar)."
BAD_ANSWER = "O TMDB mandou uma resposta inesperada."
BAD_IMAGE = "A arte do TMDB não pôde ser baixada (arquivo inválido)."

M = TypeVar("M", bound=BaseModel)


class TmdbError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TmdbClient:
    def __init__(
        self, token: str, language: str, transport: httpx2.BaseTransport | None = None
    ) -> None:
        self.language = language
        self._api = httpx2.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
            transport=transport,
        )
        # Images are public: no token on this client.
        self._images = httpx2.Client(timeout=30, transport=transport)

    def __enter__(self) -> "TmdbClient":
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._api.close()
        self._images.close()

    def search_movie(self, query: str, year: int | None) -> list[SearchResult]:
        params: dict[str, str | int] = {"query": query}
        if year:
            params["year"] = year
        return self._get("/search/movie", SearchPage, params).results

    def search_tv(self, query: str, year: int | None) -> list[SearchResult]:
        params: dict[str, str | int] = {"query": query}
        if year:
            params["first_air_date_year"] = year
        return self._get("/search/tv", SearchPage, params).results

    def movie(self, movie_id: int) -> Movie:
        return self._get(f"/movie/{movie_id}", Movie, dict(DETAILS_PARAMS))

    def tv(self, tv_id: int) -> Show:
        return self._get(f"/tv/{tv_id}", Show, dict(DETAILS_PARAMS))

    def season(self, tv_id: int, number: int, language: str | None = None) -> Season:
        params: dict[str, str | int] = {"language": language} if language else {}
        return self._get(f"/tv/{tv_id}/season/{number}", Season, params)

    def image(self, path: str) -> bytes:
        if not IMAGE_PATH.fullmatch(path):
            raise TmdbError(BAD_IMAGE)
        try:
            with self._images.stream("GET", IMAGES + path) as response:
                kind = response.headers.get("Content-Type", "")
                if response.status_code != 200 or not kind.startswith("image/"):
                    raise TmdbError(BAD_IMAGE)
                data = bytearray()
                for chunk in response.iter_bytes():
                    data += chunk
                    if len(data) > MAX_IMAGE_BYTES:
                        raise TmdbError(BAD_IMAGE)
        except httpx2.HTTPError:
            raise TmdbError(OFFLINE) from None
        return bytes(data)

    def _get(self, path: str, model: type[M], params: dict[str, str | int]) -> M:
        params.setdefault("language", self.language)
        try:
            response = self._api.get(path, params=params)
        except httpx2.HTTPError:
            raise TmdbError(OFFLINE) from None
        errors = {401: TOKEN_REFUSED, 404: NOT_FOUND, 429: RATE_LIMITED}
        if response.status_code in errors:
            raise TmdbError(errors[response.status_code])
        if response.status_code != 200:
            raise TmdbError(
                f"O TMDB respondeu com erro {response.status_code}. Tente de novo mais tarde."
            )
        try:
            return model.model_validate_json(response.content)
        except ValidationError:
            raise TmdbError(BAD_ANSWER) from None
