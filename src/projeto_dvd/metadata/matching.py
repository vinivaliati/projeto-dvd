"""Turn a guess into a TMDB suggestion. Ambiguous ones are 'doubtful', never confirmed in bulk."""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from projeto_dvd.metadata.art import episode_code
from projeto_dvd.metadata.details import episode_label, movie_label
from projeto_dvd.metadata.filename import Guess, Kind
from projeto_dvd.metadata.tmdb import NOT_FOUND, TmdbClient, TmdbError
from projeto_dvd.metadata.tmdb_models import SearchResult, Season

Status = Literal["suggested", "doubtful", "confirmed", "not_found"]

NOTHING = "Nada encontrado para '{0}'. Use Corrigir."
FROM_FOLDER = (
    "O nome do arquivo não diz qual título é; a sugestão veio do nome da pasta. Pode ser um extra."
)
MANY_GENERIC = "Os nomes dos arquivos não dizem qual filme é cada um. Use Corrigir."
SHORT_MOVIE = "Arquivo curto para um filme (menos de 40 min). Pode ser um extra: confira."
NO_EPISODE = "Não deu para saber o episódio pelo nome do arquivo. Use Corrigir."
MISSING_EPISODE = "O episódio {0} não existe no TMDB. Use Corrigir."
EPISODE_DURATION = "Duração bem diferente da do TMDB: episódio duplo, ordem do DVD ou play all?"
MIN_MOVIE_SECONDS = 40 * 60
EPISODE_TOLERANCE = 0.2


@dataclass(frozen=True)
class Suggestion:
    status: Status
    kind: Kind
    tmdb_id: int | None
    season: int | None
    episode: int | None
    episode_end: int | None
    label: str
    poster_path: str | None
    message: str | None


class Lookup:
    """TMDB calls of one click, cached: ten episodes search the show and its season once."""

    def __init__(self, client: TmdbClient) -> None:
        self.client = client
        self._searches: dict[tuple[Kind, str, int | None], list[SearchResult]] = {}
        self._seasons: dict[tuple[int, int], Season | None] = {}

    def search(self, kind: Kind, query: str, year: int | None) -> list[SearchResult]:
        key = (kind, query, year)
        if key not in self._searches:
            find = self.client.search_movie if kind == "movie" else self.client.search_tv
            self._searches[key] = find(query, year)
        return self._searches[key]

    def season(self, tv_id: int, number: int) -> Season | None:
        key = (tv_id, number)
        if key not in self._seasons:
            try:
                self._seasons[key] = self.client.season(tv_id, number)
            except TmdbError as error:
                if error.message != NOT_FOUND:
                    raise
                self._seasons[key] = None
        return self._seasons[key]


def suggest(guess: Guess, duration: float | None, lookup: Lookup) -> Suggestion:
    results = lookup.search(guess.kind, guess.title, guess.year)
    if not results and guess.year:
        results = lookup.search(guess.kind, guess.title, None)
    query_title = guess.title
    if not results and guess.fallback:
        query_title = guess.fallback
        results = lookup.search(guess.kind, guess.fallback, None)
    if not results:
        return _not_found(guess, NOTHING.format(guess.title))
    best, sure = _pick(results, query_title, guess.year)
    if guess.kind == "movie":
        status: Status = "suggested" if sure else "doubtful"
        message = None
        if duration is not None and duration < MIN_MOVIE_SECONDS:
            status, message = "doubtful", SHORT_MOVIE
        label = movie_label(best.display_title, best.year)
        return Suggestion(
            status, "movie", best.id, None, None, None, label, best.poster_path, message
        )
    return _episode(guess, best, sure, duration, lookup)


def suggest_folder(
    files: Sequence[tuple[int, Guess, float | None]], lookup: Lookup
) -> dict[int, Suggestion]:
    """Several generic names that all became the folder title cannot tell the movies apart."""
    generic = Counter(g.title for _, g, _ in files if g.from_folder and g.kind == "movie")
    found: dict[int, Suggestion] = {}
    for file_id, guess, duration in files:
        if guess.from_folder and guess.kind == "movie" and generic[guess.title] > 1:
            found[file_id] = _not_found(guess, MANY_GENERIC)
        else:
            found[file_id] = suggest(guess, duration, lookup)
        lone = len(files) == 1
        if guess.from_folder and not lone and found[file_id].status == "suggested":
            # Next to other videos, a file that says nothing is often an extra.
            found[file_id] = replace(found[file_id], status="doubtful", message=FROM_FOLDER)
    return found


def normalize(text: str) -> str:
    """Without accents, case or punctuation: 'Anel Mágico!' == 'anel magico'."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w\s]", " ", plain).split())


def _pick(results: list[SearchResult], title: str, year: int | None) -> tuple[SearchResult, bool]:
    key = normalize(title)
    same = [r for r in results if key in (normalize(r.display_title), normalize(r.original))]
    if year:
        same = [r for r in same if r.year is not None and abs(r.year - year) <= 1]
    if len(same) == 1:
        return same[0], True
    return (same or results)[0], False


def _episode(
    guess: Guess, show: SearchResult, sure: bool, duration: float | None, lookup: Lookup
) -> Suggestion:
    status: Status = "suggested" if sure else "doubtful"

    def result(status: Status, label: str, message: str | None) -> Suggestion:
        return Suggestion(status, "episode", show.id, guess.season, guess.episode,
                          guess.episode_end, label, show.poster_path, message)  # fmt: skip

    if guess.episode is None or guess.season is None:
        return result("doubtful", show.display_title, NO_EPISODE)
    code = episode_code(guess.season, guess.episode)
    season = lookup.season(show.id, guess.season)
    episode = next(
        (e for e in season.episodes if e.episode_number == guess.episode), None
    ) if season else None  # fmt: skip
    if episode is None:
        return result("doubtful", f"{show.display_title} · {code}", MISSING_EPISODE.format(code))
    label = episode_label(show.display_title, guess.season, guess.episode, episode.name)
    message = None
    if duration and episode.runtime and not guess.episode_end:
        minutes_off = abs(duration / 60 - episode.runtime)
        message = EPISODE_DURATION if minutes_off > EPISODE_TOLERANCE * episode.runtime else None
    return result(status, label, message)


def _not_found(guess: Guess, message: str) -> Suggestion:
    return Suggestion("not_found", guess.kind, None, guess.season, guess.episode,
                      guess.episode_end, "", None, message)  # fmt: skip
