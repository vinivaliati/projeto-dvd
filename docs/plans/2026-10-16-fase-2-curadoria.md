# Fase 2: Curadoria Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** each video of a disc folder gets a TMDB match (movie or episode) that the Vini confirms
or corrects on the folder page, with pt-BR details stored and the default art downloaded.

**Architecture:** pure functions guess the title from the path (`metadata/filename.py`), pick the
art (`metadata/art.py`) and compute the screen data from the stored TMDB JSON
(`metadata/details.py`); a typed `httpx2` client (`metadata/tmdb.py`, Pydantic models in
`metadata/tmdb_models.py`) talks to TMDB with a Bearer token; `metadata/matching.py` turns a
guess into a suggestion; `metadata/curation.py` runs suggestions and confirmations against the
database and the output folder (network first, short transactions); `api/curation.py` and three
templates put it on the folder page with HTMX.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX 2.0.11, SQLModel/Alembic (SQLite WAL),
Pydantic v2, httpx2 (client and `MockTransport`), pytest.

**Spec:** `docs/plans/2026-10-16-fase-2-curadoria-design.md` (read it first: it is the
authority; this plan argues from it).

## Global Constraints

- Code, identifiers, docstrings, commits and README in English; UI text in Brazilian Portuguese.
- No em dash (—) in any text (code comments, UI, docs, commits).
- Conventional Commits; every commit message ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `ruff check`, `ruff format --check`, `mypy` (strict, `src` and `tests`) and `pytest` (coverage
  ≥ 90%, target 100%, branch coverage) pass at the end of every task (`make lint && make test`).
- Never call the real TMDB API in tests; TMDB JSON in tests is invented, never copied.
- The token goes only in `Authorization: Bearer`; never in a URL, HTML, log, `repr` or message.
- Every art file is written as `.part` and renamed; nothing is written outside
  `OUTPUT_DIR/covers`.
- Network and downloads first, then one short transaction per title.
- HTMX routes of the match answer 200 with the error inside the fragment.
- Status values: `suggested`, `doubtful`, `confirmed`, `not_found`. "Confirmar todas" confirms
  only `suggested`.
- The Vini authorized running the whole plan without stopping; stop only for a decision that no
  agent (`curador`, `revisor-codigo`, `designer`, `qa`, `organizador`) can answer, or for an
  irreversible/external action. Manual QA with the real token happens at the end of the project.

## Review Focus

1. The external drive disconnected while the library opens: no `media_file` and no `title` row
   is deleted (Task 6, `test_library_without_drive_keeps_titles`).
2. A movie title with `:` (and a disc folder with `:`) becomes the art folder name on Windows:
   the files land inside `OUTPUT_DIR/covers`, with a valid name (Task 1 `safe_name` tests,
   Task 7 `test_confirm_movie_with_colon_in_title`).
3. Two "Buscar no TMDB" at the same time, or a click while "Confirmar todas" runs: one runs, the
   other gets the "em andamento" message, no 500 (Task 8 `test_second_search_is_refused`).
4. A TMDB answer with an odd image path (`../x.jpg`, a full URL, `.svg` logo) or a huge or
   non-image body: nothing is written, the title is still confirmed with a warning (Task 2
   model tests, Task 4 `image` tests, Task 7 art warning test).
5. A file replaced by another with the same name (MakeMKV `title_t00.mkv`) after confirmation:
   the title goes back to "Sugestão" with a message (Task 6
   `test_changed_file_unconfirms_title`).

---

## File map

| File | Responsibility |
|---|---|
| `src/projeto_dvd/metadata/__init__.py` | package |
| `src/projeto_dvd/metadata/filename.py` | `guess()`: path to `Guess` (pure) |
| `src/projeto_dvd/metadata/names.py` | `safe_name()`, `art_dir()` (pure, Windows-safe) |
| `src/projeto_dvd/metadata/tmdb_models.py` | Pydantic models of the TMDB answers and of the stored details |
| `src/projeto_dvd/metadata/details.py` | `title_info()`, `movie_label()`, `episode_label()` (pure) |
| `src/projeto_dvd/metadata/art.py` | `pick_art()` (pure), `save_art()` |
| `src/projeto_dvd/metadata/tmdb.py` | `TmdbClient`, `TmdbError` |
| `src/projeto_dvd/metadata/matching.py` | `Lookup`, `Suggestion`, `suggest()`, `suggest_folder()` |
| `src/projeto_dvd/metadata/curation.py` | database and disk side: suggestions, confirm, art again, counts, original language |
| `src/projeto_dvd/db/models.py` | `Title`, relationship on `MediaFile` |
| `src/projeto_dvd/db/migrations/versions/0003_create_title.py` | migration |
| `src/projeto_dvd/library/scan.py` | changed file unconfirms its title |
| `src/projeto_dvd/api/library.py` | purge guard, title counts, TMDB section in the folder context |
| `src/projeto_dvd/api/curation.py` | match routes |
| `src/projeto_dvd/api/deps.py` | `get_tmdb`, `TmdbDep` |
| `src/projeto_dvd/api/dvd.py` | original language into `suggest_choices` |
| `src/projeto_dvd/planner/dvd_plan.py` | `suggest_choices(..., original_language)` |
| `src/projeto_dvd/config.py` | `tmdb_token`, `tmdb_language` |
| `src/projeto_dvd/web/templates/_tmdb_section.html`, `_title_card.html`, `_title_search.html` | match UI |
| `src/projeto_dvd/web/templates/_folder_body.html`, `base.html`, `library.html` | order, footer, card line |
| `src/projeto_dvd/web/static/app.css`, `static/tmdb.svg` | styles, TMDB logo |
| `tests/unit/test_filename.py`, `test_names.py`, `test_tmdb_models.py`, `test_details.py`, `test_art.py`, `test_tmdb.py`, `test_matching.py`, `test_curation.py`, `test_curation_routes.py` | tests |
| `tests/tmdb_fakes.py` | invented TMDB JSON and a `MockTransport` router for tests |

---

## Group 1: pure

### Task 1: Filename guess and safe names

**Files:**
- Create: `src/projeto_dvd/metadata/__init__.py`, `src/projeto_dvd/metadata/filename.py`,
  `src/projeto_dvd/metadata/names.py`
- Test: `tests/unit/test_filename.py`, `tests/unit/test_names.py`

**Interfaces:**
- Produces: `Kind = Literal["movie", "episode"]`; `Guess(kind, title, year, season, episode,
  episode_end, warnings, from_folder, fallback)`; `guess(path: str, folder: str, max_year: int)
  -> Guess` where `path` is relative to the disc folder (`"Temporada 2/03.mkv"`);
  `safe_name(text: str, default: str = "Sem nome") -> str`; `art_dir(output_dir: Path,
  folder: str, name: str) -> Path` (raises `ValueError` outside `covers`).

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_filename.py`)

```python
import pytest

from projeto_dvd.metadata.filename import Guess, guess

Y = 2026


@pytest.mark.parametrize(
    ("path", "folder", "kind", "title", "year", "season", "episode"),
    [
        ("The.Lord.of.the.Rings.2001.1080p.BluRay.x264-GRUPO.mkv", "LOTR", "movie",
         "The Lord of the Rings", 2001, None, None),
        ("O Senhor dos Anéis (2001).mkv", "Senhor", "movie", "O Senhor dos Anéis", 2001, None, None),
        ("Cidade de Deus 2002 DUBLADO 720p.mkv", "x", "movie", "Cidade de Deus", 2002, None, None),
        ("Movie.2019.2160p.UHD.BDRemux.HDR.DV.TrueHD.Atmos.7.1-RARBG.mkv", "x", "movie",
         "Movie", 2019, None, None),
        ("Filme (Dublado) (2010).mkv", "x", "movie", "Filme", 2010, None, None),
        ("Amelie.2001.DDP5.1.NF.WEB-DL.mkv", "x", "movie", "Amelie", 2001, None, None),
        ("1917.mkv", "x", "movie", "1917", None, None, None),
        ("1917 (2019).mkv", "x", "movie", "1917", 2019, None, None),
        ("2012 2009 1080p.mkv", "x", "movie", "2012", 2009, None, None),
        ("2001 A Space Odyssey 1968.mkv", "x", "movie", "2001 A Space Odyssey", 1968, None, None),
        ("E.T.the.Extra-Terrestrial.1982.mkv", "x", "movie", "E.T. the Extra-Terrestrial",
         1982, None, None),
        ("Spider-Man.2002.mkv", "x", "movie", "Spider-Man", 2002, None, None),
        ("Friends.S01E03.720p.mkv", "x", "episode", "Friends", None, 1, 3),
        ("friends s1e3.mkv", "x", "episode", "friends", None, 1, 3),
        ("Friends 1x03.mkv", "x", "episode", "Friends", None, 1, 3),
        ("Friends T01E03.mkv", "x", "episode", "Friends", None, 1, 3),
        ("Friends Temporada 1 Episódio 3.mkv", "x", "episode", "Friends", None, 1, 3),
        ("Doctor.Who.2005.S01E01.mkv", "x", "episode", "Doctor Who", 2005, 1, 1),
        ("Show.S00E02.mkv", "x", "episode", "Show", None, 0, 2),
        ("S01E03.mkv", "Friends", "episode", "Friends", None, 1, 3),
        ("Temporada 2/03.mkv", "Friends", "episode", "Friends", None, 2, 3),
        ("Ep 03.mkv", "Friends Temporada 1", "episode", "Friends", None, 1, 3),
        ("EP03.mkv", "Friends T1", "episode", "Friends", None, 1, 3),
        ("Episódio 3.mkv", "Friends Season 1", "episode", "Friends", None, 1, 3),
        ("E03.mkv", "1ª Temporada", "episode", "1ª Temporada", None, 1, 3),
    ],
)  # fmt: skip
def test_guess(
    path: str,
    folder: str,
    kind: str,
    title: str,
    year: int | None,
    season: int | None,
    episode: int | None,
) -> None:
    result = guess(path, folder, Y)

    assert (result.kind, result.title, result.year, result.season, result.episode) == (
        kind, title, year, season, episode,
    )  # fmt: skip


def test_resolution_is_not_an_episode() -> None:
    result = guess("Movie 1920x1080 720x480.mkv", "x", Y)

    assert result.kind == "movie"
    assert result.title == "Movie 1920x1080 720x480"


def test_two_episodes_in_one_file() -> None:
    for name in ("Friends.S01E01E02.mkv", "Friends.S01E01-E02.mkv"):
        result = guess(name, "x", Y)
        assert (result.episode, result.episode_end) == (1, 2)
        assert result.warnings == ("Este arquivo tem dois episódios (E01 e E02).",)


@pytest.mark.parametrize("name", ["title_t00.mkv", "TITLE_01.mkv", "Disc 1.mkv", "Faixa 2.mkv",
                                  "12.mkv", "x.mkv", "[GRUPO].mkv"])  # fmt: skip
def test_generic_names_use_the_folder(name: str) -> None:
    result = guess(name, "Senhor dos Aneis (2001)", Y)

    assert result == Guess(kind="movie", title="Senhor dos Aneis", year=2001, from_folder=True)


def test_makemkv_volume_names() -> None:
    lotr = guess("LORD_OF_THE_RINGS_D1_t00.mkv", "Senhor", Y)
    friends = guess("Friends_S1_D1_t03.mkv", "Seriados", Y)

    assert (lotr.kind, lotr.title, lotr.from_folder) == ("movie", "LORD OF THE RINGS", False)
    assert lotr.fallback == "Senhor"
    assert (friends.kind, friends.title, friends.season, friends.episode) == (
        "episode", "Friends", 1, None,
    )  # fmt: skip


def test_makemkv_number_in_a_season_folder_is_not_an_episode() -> None:
    result = guess("Temporada 1/title_t03.mkv", "Friends", Y)

    assert (result.kind, result.episode, result.from_folder) == ("movie", None, True)
    assert result.title == "Friends"


def test_t2_in_a_movie_folder_is_not_a_season() -> None:
    result = guess("title_t00.mkv", "Exterminador do Futuro T2", Y)

    assert (result.kind, result.title, result.season) == (
        "movie", "Exterminador do Futuro T2", None,
    )  # fmt: skip


def test_future_year_is_not_a_year() -> None:
    assert guess("Blade Runner 2049.mkv", "x", 2026).year is None
    assert guess("Blade Runner 2049.mkv", "x", 2026).title == "Blade Runner 2049"


def test_fallback_is_the_folder_title_when_the_name_is_used() -> None:
    result = guess("Matrix.1999.mkv", "Trilogia Matrix", Y)

    assert result.fallback == "Trilogia Matrix"
```

(`tests/unit/test_names.py`)

```python
from pathlib import Path

import pytest

from projeto_dvd.metadata.names import art_dir, safe_name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("O Senhor dos Anéis: A Sociedade do Anel (2001)",
         "O Senhor dos Anéis - A Sociedade do Anel (2001)"),
        ('a<b>c"d/e\\f|g?h*i', "a b c d e f g h i"),
        ("Fim com ponto.", "Fim com ponto"),
        ("  espaços  ", "espaços"),
        ("CON", "Sem nome"),
        ("nul.txt", "Sem nome"),
        ("..", "Sem nome"),
        ("", "Sem nome"),
        ("tab\tnova\nlinha", "tab nova linha"),
        ("x" * 100, "x" * 80),
        ("Amélie", "Amélie"),
    ],
)  # fmt: skip
def test_safe_name(text: str, expected: str) -> None:
    assert safe_name(text) == expected


def test_art_dir_stays_inside_covers(tmp_path: Path) -> None:
    path = art_dir(tmp_path, "Disco: 1", "Filme: Parte 2 (2001)")

    assert path == tmp_path / "covers" / "Disco - 1" / "Filme - Parte 2 (2001)"


def test_art_dir_refuses_an_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import projeto_dvd.metadata.names as names

    monkeypatch.setattr(names, "safe_name", lambda text, default="Sem nome": "../..")

    with pytest.raises(ValueError):
        art_dir(tmp_path, "a", "b")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_filename.py tests/unit/test_names.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'projeto_dvd.metadata'`.

- [ ] **Step 3: Implement** (`src/projeto_dvd/metadata/__init__.py` is empty; then
  `src/projeto_dvd/metadata/filename.py`)

```python
"""Guess a movie or an episode from a video's path inside its disc folder. Pure."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from projeto_dvd.library.files import nfc

Kind = Literal["movie", "episode"]

# Anything from the first of these on is release noise (lowercase; matched as whole words).
RELEASE_TERMS = (
    "480p", "576p", "720p", "1080p", "1080i", "2160p", "4k", "uhd", "10bit", "hdr", "dv",
    "imax", "bluray", "bdrip", "brrip", "bdremux", "remux", "web-dl", "webrip", "hdtv",
    "dvdrip", "nf", "amzn", "dsnp", "hmax", "atvp", "x264", "x265", "h264", "hevc", "avc",
    "xvid", "dts", "ac3", "eac3", "aac", "flac", "truehd", "atmos", "ddp5.1", "dd5.1", "5.1",
    "7.1", "2.0", "extended", "unrated", "directors cut", "remastered", "remasterizado",
    "versão estendida", "proper", "repack", "dublado", "dub", "legendado", "leg",
    "dual audio", "dual", "nacional",
)  # fmt: skip
_RELEASE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(t) for t in sorted(RELEASE_TERMS, key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)
_EPISODE = re.compile(
    r"(?<![A-Za-z0-9])[ST](\d{1,2}) ?E(\d{1,3})(?: ?-? ?E(\d{1,3}))?(?![0-9])", re.IGNORECASE
)
_CROSS = re.compile(r"(?<![A-Za-z0-9])(\d{1,2})x(\d{2,3})(?![A-Za-z0-9])", re.IGNORECASE)
_LONG = re.compile(r"temporada (\d{1,2}) epis[oó]dio (\d{1,3})", re.IGNORECASE)
_NUMBER_ONLY = re.compile(r"(?:(?:e|ep|epis[oó]dio|episode) ?)?(\d{1,3})", re.IGNORECASE)
_YEAR = re.compile(r"(?<!\d)(19\d\d|20\d\d)(?!\d)")
_MAKEMKV_TITLE = re.compile(r"_t\d+$", re.IGNORECASE)
_MAKEMKV_DISC = re.compile(r"(?:^|[ _.])(?:S(\d{1,2})_)?D(?:isc)?[ _]?\d{1,2}(?=$|[ _.])", re.I)
_SEASON_WORD = re.compile(r"(?:temporada|season) ?(\d{1,2})|(\d{1,2}) ?ª ?temporada", re.I)
_SEASON_TAIL = re.compile(r"(?<!\w)[TS](\d{1,2})$", re.IGNORECASE)
_GENERIC = re.compile(r"(?:title|disc|disco|faixa|track)? ?\d*", re.IGNORECASE)
TWO_EPISODES = "Este arquivo tem dois episódios (E{0:02d} e E{1:02d})."


@dataclass(frozen=True)
class Guess:
    kind: Kind
    title: str
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None
    warnings: tuple[str, ...] = ()
    from_folder: bool = False  # the file name said nothing; the title is the folder's
    fallback: str | None = None  # the folder title, to search when the name finds nothing


def guess(path: str, folder: str, max_year: int) -> Guess:
    """`path` is relative to the disc folder; subfolders can say the season."""
    pure = PurePosixPath(nfc(path))
    stem = pure.stem
    makemkv = bool(_MAKEMKV_TITLE.search(stem))
    stem = _MAKEMKV_TITLE.sub("", stem)
    disc = _MAKEMKV_DISC.search(stem)
    disc_season = int(disc.group(1)) if disc and disc.group(1) else None
    stem = _MAKEMKV_DISC.sub(" ", stem)
    text = _clean(stem)
    # A movie keeps the whole folder name ("Exterminador do Futuro T2"); a show drops the season.
    movie_title, movie_year = _title_and_year(_clean(nfc(folder)), max_year)
    show_title, show_year = _title_and_year(_strip_season(_clean(nfc(folder))), max_year)
    season_here = next(
        (s for s in (_season_of(p) for p in reversed((*pure.parent.parts, nfc(folder)))) if s),
        None,
    )

    marker = _EPISODE.search(text) or _CROSS.search(text) or _LONG.search(text)
    if marker:
        season, episode = int(marker.group(1)), int(marker.group(2))
        end = marker.group(3) if marker.re is _EPISODE else None
        show, year = _title_and_year(_cut_release(text[: marker.start()]), max_year)
        if _generic(show):
            show, year = show_title, show_year
        warnings = (TWO_EPISODES.format(episode, int(end)),) if end else ()
        return Guess("episode", show, year, season, episode, int(end) if end else None, warnings)

    number = _NUMBER_ONLY.fullmatch(text)
    if number and season_here is not None and not makemkv:
        return Guess("episode", show_title, show_year, season_here, int(number.group(1)))

    title, year = _title_and_year(_cut_release(text), max_year)
    if disc_season is not None and not _generic(title):
        return Guess("episode", title, year, disc_season, None)
    if _generic(title):
        return Guess("movie", movie_title, movie_year, from_folder=True)
    return Guess("movie", title, year, fallback=movie_title)


def _clean(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", text)
    # Keep the dots of acronyms (E.T.) and of numbers (5.1); the others separate words.
    text = re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m.group().replace(".", "\0"), text)
    text = re.sub(r"(?<=\d)\.(?=\d)", "\0", text)
    text = text.replace(".", " ").replace("_", " ").replace("\0", ".")
    text = re.sub(r"\((?!\s*(?:19|20)\d\d\s*\))[^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _cut_release(text: str) -> str:
    found = _RELEASE.search(text)
    return text[: found.start()] if found else text


def _title_and_year(text: str, max_year: int) -> tuple[str, int | None]:
    """The last plausible year that has a title before it."""
    for found in reversed(list(_YEAR.finditer(text))):
        year = int(found.group(1))
        before = _tidy(text[: found.start()])
        if year <= max_year and before:
            return before, year
    return _tidy(text), None


def _tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" -.,(")


def _generic(title: str) -> bool:
    letters = sum(ch.isalpha() for ch in title)
    return letters < 2 or bool(_GENERIC.fullmatch(title))


def _season_of(name: str) -> int | None:
    found = _SEASON_WORD.search(name) or _SEASON_TAIL.search(name.strip())
    if not found:
        return None
    return int(next(group for group in found.groups() if group))


def _strip_season(name: str) -> str:
    stripped = _tidy(_SEASON_TAIL.sub("", _SEASON_WORD.sub("", name)))
    return stripped or name
```

`_strip_season` falls back to the full name when nothing is left ("1ª Temporada" stays the
title, as the test expects).

(`src/projeto_dvd/metadata/names.py`)

```python
"""Folder and file names that Windows accepts. Pure."""

import re
from pathlib import Path

from projeto_dvd.library.files import nfc

MAX_NAME = 80  # keeps OUTPUT_DIR\covers\<disc>\<title>\poster.jpg under MAX_PATH (260)
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}  # fmt: skip


def safe_name(text: str, default: str = "Sem nome") -> str:
    name = nfc(text).replace(": ", " - ")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()[:MAX_NAME].rstrip(" .")
    if not name or name.split(".")[0].upper() in _RESERVED:
        return default
    return name


def art_dir(output_dir: Path, folder: str, name: str) -> Path:
    """OUTPUT_DIR/covers/<disc folder>/<title>; ValueError if it would land outside covers."""
    covers = (output_dir / "covers").resolve()
    path = (covers / safe_name(folder) / safe_name(name)).resolve()
    if not path.is_relative_to(covers) or path.parent.parent != covers:
        raise ValueError(f"art folder outside covers: {path}")
    return output_dir / "covers" / safe_name(folder) / safe_name(name)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_filename.py tests/unit/test_names.py -q`
Expected: PASS. Then `make lint && make test`.

- [ ] **Step 5: Commit**

```bash
git add src/projeto_dvd/metadata tests/unit/test_filename.py tests/unit/test_names.py
git commit -m "feat: guess movies and episodes from file and folder names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: TMDB models and title details

**Files:**
- Create: `src/projeto_dvd/metadata/tmdb_models.py`, `src/projeto_dvd/metadata/details.py`
- Test: `tests/unit/test_tmdb_models.py`, `tests/unit/test_details.py`
- Create: `tests/tmdb_fakes.py` (invented data, used from here on)

**Interfaces:**
- Produces (`tmdb_models.py`): `IMAGE_PATH: re.Pattern[str]`; `year_of(date: str | None) ->
  int | None`; models `Image(file_path, iso_639_1, vote_average, width)`, `Images(posters,
  backdrops, logos)`, `TranslationData(title, name, overview)`, `Translation(iso_639_1,
  iso_3166_1, data)`, `Translations(translations)`, `CastMember(name)`, `Credits(cast)`,
  `CollectionRef(id, name)`, `SearchResult(id, title, original_title, name, original_name,
  release_date, first_air_date, overview, poster_path)` with properties `display_title`,
  `original`, `year`; `SearchPage(results)`; `Movie`; `Show`; `Episode(season_number,
  episode_number, name, overview, air_date, runtime, still_path)`; `Season(season_number,
  episodes)`; stored details `MovieDetails(kind="movie", movie)`, `EpisodeDetails(kind=
  "episode", show, episode, episode_end)`, `Details` (discriminated union) and
  `DETAILS: TypeAdapter[Details]`.
- Produces (`details.py`): `TitleInfo` (Pydantic, dumped to `metadata.json`);
  `title_info(details: Details) -> TitleInfo`; `movie_label(title: str, year: int | None) ->
  str`; `episode_label(show: str, season: int, episode: int, name: str) -> str`;
  `generic_episode_name(name: str) -> bool`.

- [ ] **Step 1: Write `tests/tmdb_fakes.py`** (invented values only)

```python
"""Invented TMDB answers and a MockTransport router. Never real responses."""

import json
from collections.abc import Callable
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


def router(routes: dict[str, Any], requests: list[httpx2.Request] | None = None) -> Handler:
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
```

- [ ] **Step 2: Write the failing tests**

(`tests/unit/test_tmdb_models.py`)

```python
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
```

(`tests/unit/test_details.py`)

```python
from typing import Any

from projeto_dvd.metadata.details import (
    episode_label,
    generic_episode_name,
    movie_label,
    title_info,
)
from projeto_dvd.metadata.tmdb_models import EpisodeDetails, Movie, MovieDetails, Season, Show
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

    assert (info.kind, info.show, info.season, info.episode) == ("episode", "Amigos de Sempre", 1, 3)
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
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/test_tmdb_models.py tests/unit/test_details.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement** (`src/projeto_dvd/metadata/tmdb_models.py`)

```python
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
```

(`src/projeto_dvd/metadata/details.py`)

```python
"""What the screens, menus and covers show about a confirmed title. Pure."""

import re

from pydantic import BaseModel

from projeto_dvd.metadata.filename import Kind
from projeto_dvd.metadata.tmdb_models import (
    Details,
    Movie,
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


def title_info(details: Details) -> TitleInfo:
    if details.kind == "movie":
        movie = details.movie
        collection = movie.belongs_to_collection
        return TitleInfo(
            kind="movie",
            tmdb_id=movie.id,
            title=_movie_title(movie),
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
        show=show.name,
        season=episode.season_number,
        episode=episode.episode_number,
        episode_end=details.episode_end.episode_number if details.episode_end else None,
        year=year_of(episode.air_date) or year_of(show.first_air_date),
        overview=episode.overview,
        cast=[member.name for member in show.credits.cast[:CAST]],
        runtime=episode.runtime,
        original_language=show.original_language,
    )


def movie_label(title: str, year: int | None) -> str:
    return f"{title} ({year})" if year else title


def episode_label(show: str, season: int, episode: int, name: str) -> str:
    code = f"S{season:02d}E{episode:02d}"
    return f"{show} · {code} · {name}" if name else f"{show} · {code}"


def generic_episode_name(name: str) -> bool:
    """TMDB fills a missing pt-BR episode name with 'Episódio N'."""
    return not name.strip() or bool(_GENERIC_EPISODE.fullmatch(name.strip()))


def _movie_title(movie: Movie) -> str:
    """TMDB falls back to the original title when there is no pt-BR one: prefer English then."""
    if movie.original_language == "pt" or any(
        t.iso_639_1 == "pt" and t.iso_3166_1 == "BR" and t.data.title
        for t in movie.translations.translations
    ):
        return movie.title
    return _english(movie.translations).title or movie.title


def _english(translations: Translations) -> TranslationData:
    for translation in translations.translations:
        if translation.iso_639_1 == "en":
            return translation.data
    return _EMPTY
```

- [ ] **Step 5: Run to verify they pass**, then `make lint && make test`.

- [ ] **Step 6: Commit** `feat: model the TMDB answers and the confirmed title details`

### Task 3: Art choice and saving

**Files:**
- Create: `src/projeto_dvd/metadata/art.py`
- Test: `tests/unit/test_art.py`

**Interfaces:**
- Consumes: `Details`, `Images`, `Image` (Task 2).
- Produces: `ArtPick(name: str, path: str, warning: str | None)`; `pick_art(details: Details) ->
  list[ArtPick]`; `save_art(data: bytes, target: Path) -> None` (atomic); `LOW_RES`,
  `BACKDROP_TEXT` messages; `episode_code(season: int, episode: int) -> str` (`"S01E03"`).

- [ ] **Step 1: Write the failing tests**

```python
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
    images = {"posters": [], "backdrops": [], "logos": []}

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
```

- [ ] **Step 2: Run to verify they fail** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
"""Which TMDB images become the default art of a title, and writing them safely."""

from dataclasses import dataclass
from pathlib import Path

from projeto_dvd.metadata.tmdb_models import Details, Image, Images

LOW_RES = "Pôster com baixa resolução para impressão (menos de 1000 px de largura)."
BACKDROP_TEXT = "O fundo escolhido pode ter texto (não há um sem idioma)."
MIN_POSTER_WIDTH = 1000


@dataclass(frozen=True)
class ArtPick:
    name: str  # file name in the art folder
    path: str  # TMDB file path
    warning: str | None = None


def episode_code(season: int, episode: int) -> str:
    return f"S{season:02d}E{episode:02d}"


def pick_art(details: Details) -> list[ArtPick]:
    if details.kind == "movie":
        poster, images = details.movie.poster_path, details.movie.images
    else:
        poster, images = details.show.poster_path, details.show.images
    picks = [p for p in (_poster(poster, images), _backdrop(images), _logo(images)) if p]
    if details.kind == "episode" and details.episode.still_path:
        code = episode_code(details.episode.season_number, details.episode.episode_number)
        picks.append(ArtPick(f"{code}.jpg", details.episode.still_path))
    return picks


def save_art(data: bytes, target: Path) -> None:
    """Never leave half a file: write next to it and rename."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    part.replace(target)


def _poster(path: str | None, images: Images) -> ArtPick | None:
    """The poster TMDB chose for pt-BR; the image list only says its width."""
    if path is None or not path.endswith(".jpg"):
        return None
    width = next((i.width for i in images.posters if i.file_path == path), None)
    low = width is not None and width < MIN_POSTER_WIDTH
    return ArtPick("poster.jpg", path, LOW_RES if low else None)


def _backdrop(images: Images) -> ArtPick | None:
    usable = [i for i in images.backdrops if i.file_path and i.file_path.endswith(".jpg")]
    clean = [i for i in usable if i.iso_639_1 is None]
    best = _best(clean or usable)
    if best is None or best.file_path is None:
        return None
    return ArtPick("backdrop.jpg", best.file_path, None if clean else BACKDROP_TEXT)


def _logo(images: Images) -> ArtPick | None:
    pngs = [i for i in images.logos if i.file_path and i.file_path.endswith(".png")]
    for language in ("pt", "en", None):
        best = _best([i for i in pngs if i.iso_639_1 == language])
        if best is not None and best.file_path is not None:
            return ArtPick("logo.png", best.file_path)
    return None


def _best(images: list[Image]) -> Image | None:
    return max(images, key=lambda i: (i.vote_average, i.width), default=None)
```

- [ ] **Step 4: Run to verify they pass**, `make lint && make test`.

- [ ] **Step 5: Commit** `feat: pick the default art of a title`

---

## Group 2: TMDB

### Task 4: TMDB client

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (`httpx2` to the app dependencies),
  `src/projeto_dvd/config.py`
- Create: `src/projeto_dvd/metadata/tmdb.py`
- Test: `tests/unit/test_tmdb.py`, `tests/unit/test_config.py`

**Interfaces:**
- Consumes: models of Task 2.
- Produces: `TmdbError(message: str)` with `.message`; `TmdbClient(token: str, language: str,
  transport: httpx2.BaseTransport | None = None)`, a context manager, with
  `search_movie(query: str, year: int | None) -> list[SearchResult]`, `search_tv(query: str,
  year: int | None) -> list[SearchResult]`, `movie(movie_id: int) -> Movie`, `tv(tv_id: int) ->
  Show`, `season(tv_id: int, number: int, language: str | None = None) -> Season`,
  `image(path: str) -> bytes`; constants `TOKEN_REFUSED`, `NOT_FOUND`, `RATE_LIMITED`,
  `OFFLINE`, `BAD_ANSWER`, `BAD_IMAGE`, `MAX_IMAGE_BYTES = 30 * 1024 * 1024`.
- Settings: `tmdb_token: SecretStr | None = None`, `tmdb_language: str = "pt-BR"`.

- [ ] **Step 1: Move the dependency**

Run: `uv remove --dev httpx2 && uv add "httpx2>=2.13.1"`
Expected: `httpx2` under `[project] dependencies`, lock updated, `uv run pytest -q` still green.

- [ ] **Step 2: Write the failing tests** (`tests/unit/test_tmdb.py`)

```python
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


def client(routes: dict[str, object], requests: list[httpx2.Request] | None = None) -> TmdbClient:
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
        with TmdbClient(TOKEN, "pt-BR", transport=httpx2.MockTransport(handler)) as tmdb:
            with pytest.raises(TmdbError) as error:
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
        with TmdbClient(TOKEN, "pt-BR", transport=httpx2.MockTransport(handler)) as tmdb:
            with pytest.raises(TmdbError) as error:
                tmdb.image("/a.jpg")
        assert error.value.message == BAD_IMAGE
```

(add to `tests/unit/test_config.py`)

```python
def test_tmdb_token_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_TOKEN", "abc123")
    monkeypatch.delenv("TMDB_LANGUAGE", raising=False)

    settings = Settings()

    assert settings.tmdb_token is not None
    assert settings.tmdb_token.get_secret_value() == "abc123"
    assert "abc123" not in repr(settings)
    assert settings.tmdb_language == "pt-BR"


def test_tmdb_token_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMDB_TOKEN", raising=False)

    assert Settings().tmdb_token is None
```

- [ ] **Step 3: Run to verify they fail.**

- [ ] **Step 4: Implement** (`config.py`: add `from pydantic import SecretStr` and the two
  fields, with the comment "# TMDB API Read Access Token (Bearer). Phase 2."). Then
  `src/projeto_dvd/metadata/tmdb.py`:

```python
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
```

- [ ] **Step 5: Run to verify they pass**, `make lint && make test`.

- [ ] **Step 6: Commit** `feat: add a TMDB client with the token in the header`

### Task 5: Matching

**Files:**
- Create: `src/projeto_dvd/metadata/matching.py`
- Test: `tests/unit/test_matching.py`

**Interfaces:**
- Consumes: `Guess` (Task 1), `TmdbClient`, `TmdbError`, `NOT_FOUND` (Task 4),
  `movie_label`, `episode_label` (Task 2).
- Produces: `Status = Literal["suggested", "doubtful", "confirmed", "not_found"]`;
  `Suggestion(status, kind, tmdb_id, season, episode, episode_end, label, poster_path,
  message)`; `Lookup(client)` with `search(kind, query, year) -> list[SearchResult]` and
  `season(tv_id, number) -> Season | None` (both cached per instance); `suggest(guess: Guess,
  duration: float | None, lookup: Lookup) -> Suggestion`; `suggest_folder(files:
  list[tuple[int, Guess, float | None]], lookup: Lookup) -> dict[int, Suggestion]`; messages
  `NOTHING`, `MANY_GENERIC`, `SHORT_MOVIE`, `NO_EPISODE`, `MISSING_EPISODE`,
  `EPISODE_DURATION`.

- [ ] **Step 1: Write the failing tests**

```python
import httpx2

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
from projeto_dvd.metadata.tmdb import TmdbClient
from tests.tmdb_fakes import router, search_page, season

RING = {"id": 101, "title": "Anel Mágico", "original_title": "The Magic Ring",
        "release_date": "2001-12-19", "poster_path": "/p.jpg"}  # fmt: skip
RING_REMAKE = {"id": 102, "title": "Anel Mágico", "release_date": "2019-01-01"}
FRIENDS = {"id": 202, "name": "Amigos de Sempre", "original_name": "Forever Friends",
           "first_air_date": "1994-09-22"}  # fmt: skip


def lookup(routes: dict[str, object], requests: list[httpx2.Request] | None = None) -> Lookup:
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
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**

```python
"""Turn a guess into a TMDB suggestion. Ambiguous ones are 'doubtful', never confirmed in bulk."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from projeto_dvd.metadata.art import episode_code
from projeto_dvd.metadata.details import episode_label, movie_label
from projeto_dvd.metadata.filename import Guess, Kind
from projeto_dvd.metadata.tmdb import TmdbClient, TmdbError
from projeto_dvd.metadata.tmdb_models import SearchResult, Season

Status = Literal["suggested", "doubtful", "confirmed", "not_found"]

NOTHING = "Nada encontrado para '{0}'. Use Corrigir."
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
        return Suggestion(status, "movie", best.id, None, None, None,
                          movie_label(best.display_title, best.year), best.poster_path, message)  # fmt: skip
    return _episode(guess, best, sure, duration, lookup)


def suggest_folder(
    files: list[tuple[int, Guess, float | None]], lookup: Lookup
) -> dict[int, Suggestion]:
    """Several generic names that all became the folder title cannot tell the movies apart."""
    generic = Counter(g.title for _, g, _ in files if g.from_folder and g.kind == "movie")
    found: dict[int, Suggestion] = {}
    for file_id, guess, duration in files:
        if guess.from_folder and guess.kind == "movie" and generic[guess.title] > 1:
            found[file_id] = _not_found(guess, MANY_GENERIC)
        else:
            found[file_id] = suggest(guess, duration, lookup)
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
        if abs(duration / 60 - episode.runtime) > EPISODE_TOLERANCE * episode.runtime:
            message = EPISODE_DURATION
    return result(status, label, message)


def _not_found(guess: Guess, message: str) -> Suggestion:
    return Suggestion("not_found", guess.kind, None, guess.season, guess.episode,
                      guess.episode_end, "", None, message)  # fmt: skip
```

(`NOT_FOUND` is imported from `projeto_dvd.metadata.tmdb` too.)

- [ ] **Step 4: Run to verify they pass**, `make lint && make test`.

- [ ] **Step 5: Commit** `feat: suggest a TMDB match for each video, doubtful when ambiguous`

---

## Group 3: database

### Task 6: Title table, cascade, purge guard and changed files

**Files:**
- Modify: `src/projeto_dvd/db/models.py`, `src/projeto_dvd/library/scan.py`,
  `src/projeto_dvd/api/library.py`
- Create: `src/projeto_dvd/db/migrations/versions/0003_create_title.py`
- Test: `tests/unit/test_db.py`, `tests/unit/test_scan.py`, `tests/unit/test_library_routes.py`

**Interfaces:**
- Produces: `Title` table (`media_file_id` pk/FK, `status`, `kind`, `tmdb_id`, `season`,
  `episode`, `episode_end`, `label`, `poster_path`, `message`, `tmdb_json`);
  `MediaFile.title: Title | None` (ORM cascade delete); `CHANGED_FILE` message in `scan.py`.

- [ ] **Step 1: Write the failing tests**

(`tests/unit/test_db.py`, add)

```python
def make_title(session: Session, status: str = "confirmed") -> MediaFile:
    row = MediaFile(folder="F", path="F/a.mkv", size=1, mtime_ns=1, scanned_at=datetime.now(UTC))
    row.title = Title(status=status, kind="movie", label="Anel (2001)", tmdb_id=101)
    session.add(row)
    session.commit()
    return row


def test_deleting_a_media_file_deletes_its_title(session: Session) -> None:
    row = make_title(session)

    session.delete(row)
    session.commit()

    assert session.exec(select(Title)).all() == []


def test_migration_0003_keeps_existing_rows(database_url: str) -> None:
    from alembic import command

    from projeto_dvd.db.session import _config

    command.upgrade(_config(database_url), "0002")
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO media_file (folder, path, size, mtime_ns, scanned_at)"
            " VALUES ('F', 'F/a.mkv', 1, 1, '2026-10-16 00:00:00')"
        ))  # fmt: skip
    migrate(database_url)
    with Session(engine) as session:
        assert len(session.exec(select(MediaFile)).all()) == 1
        assert session.exec(select(Title)).all() == []
    engine.dispose()
```

(`tests/unit/test_scan.py`, add; reuse the module's existing fake prober and folder helpers)

```python
def test_changed_file_unconfirms_title(session: Session, tmp_path: Path) -> None:
    media = tmp_path / "media"
    video = make_file(media / "F" / "title_t00.mkv", b"a")
    scan_folder(session, media, "F", media / "F", fake_probe)
    row = session.exec(select(MediaFile)).one()
    row.title = Title(status="confirmed", kind="movie", label="Anel (2001)", tmdb_id=101)
    session.commit()

    video.write_bytes(b"another disc")
    scan_folder(session, media, "F", media / "F", fake_probe)

    session.refresh(row)
    assert row.title is not None
    assert (row.title.status, row.title.message) == ("suggested", CHANGED_FILE)
    assert row.title.tmdb_id == 101
```

(`tests/unit/test_library_routes.py`, add)

```python
def test_library_without_drive_keeps_titles(
    client: TestClient, probes: list[str], media: Path
) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    shutil.rmtree(media)  # the drive is unplugged: /media is empty

    client.get("/")

    engine = client.app.state.engine  # type: ignore[attr-defined]
    with Session(engine) as session:
        assert len(session.exec(select(MediaFile)).all()) == 1


def test_library_purges_a_removed_folder_when_others_exist(
    client: TestClient, probes: list[str], media: Path
) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    make_file(media / "Outra" / "a.mkv")
    shutil.rmtree(media / "Senhor dos Aneis")

    client.get("/")

    engine = client.app.state.engine  # type: ignore[attr-defined]
    with Session(engine) as session:
        assert session.exec(select(MediaFile)).all() == []
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**

`models.py` (add `Relationship` to the `sqlmodel` import; `Optional` from `typing` is needed
for the forward reference that SQLModel resolves):

```python
class MediaFile(SQLModel, table=True):
    ...  # existing fields unchanged
    # One TMDB match per video; deleting the video row (scan, purge) deletes it too. ORM
    # cascade, not PRAGMA foreign_keys: a future Alembic batch copy cannot wipe the titles.
    title: Optional["Title"] = Relationship(
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )


class Title(SQLModel, table=True):
    """The TMDB match of one video: a suggestion until the Vini confirms it."""

    __tablename__ = "title"

    media_file_id: int | None = Field(default=None, foreign_key="media_file.id", primary_key=True)
    status: str  # suggested, doubtful, confirmed, not_found
    kind: str  # movie or episode
    tmdb_id: int | None = None  # the movie, or the show of an episode
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None  # a file with two episodes
    label: str = ""  # what the card shows; a suggestion has no tmdb_json yet
    poster_path: str | None = None  # TMDB path, for the thumbnail
    message: str | None = None  # warning or the reason of not_found (Portuguese)
    tmdb_json: str | None = None  # stored details (Details), only when confirmed
```

`0003_create_title.py`:

```python
"""Create the title table (TMDB matches)."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "title",
        sa.Column("media_file_id", sa.Integer(), sa.ForeignKey("media_file.id"), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("episode_end", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("poster_path", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("tmdb_json", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("title")
```

Also add a comment at the engine creation in `db/migrations/env.py`: "# No PRAGMA
foreign_keys here: a batch migration copies and drops tables, and a cascade would wipe titles."

`scan.py`, inside the loop, right after `row = row or MediaFile(...)`:

```python
        if row.title is not None and row.title.status == "confirmed" and not _unchanged(row, video):
            # MakeMKV repeats title_t00.mkv across discs: a new file needs a new look.
            row.title.status, row.title.message = "suggested", CHANGED_FILE
```

with `CHANGED_FILE = "O arquivo mudou desde a confirmação. Confira antes de confirmar de novo."`
(the check must run before `row.size, row.mtime_ns = ...`; a brand-new row has `size=0` and no
title).

`api/library.py`, `library_page`:

```python
    folders = list_disc_folders(media_dir)
    # An unplugged drive lists nothing: purging then would wipe every confirmed match.
    if folders:
        purge_missing_folders(session, folders)
```

- [ ] **Step 4: Run to verify they pass**, `make lint && make test`.

- [ ] **Step 5: Commit** `feat: store TMDB matches and keep them when the drive is unplugged`

---

## Group 4: confirmation

### Task 7: Curation service (suggest, confirm, art again)

**Files:**
- Create: `src/projeto_dvd/metadata/curation.py`
- Test: `tests/unit/test_curation.py`

**Interfaces:**
- Consumes: everything above; `cannot_write` from `projeto_dvd.jobs.pipeline`; `summarize`
  from `projeto_dvd.library.probe`.
- Produces:
  - `Choice(kind: Kind, tmdb_id: int, season: int | None = None, episode: int | None = None,
    episode_end: int | None = None)`;
  - `run_suggestions(session: Session, folder: str, client: TmdbClient, max_year: int) -> int`
    (suggests for every `media_file` of the folder whose title is not confirmed; returns how
    many rows got a suggestion);
  - `fetch_details(choice: Choice, client: TmdbClient) -> Details` (raises `TmdbError`);
  - `confirm(session: Session, media_file_id: int, choice: Choice, client: TmdbClient,
    output_dir: Path) -> Title`;
  - `confirm_all(session: Session, folder: str, client: TmdbClient, output_dir: Path) -> int`;
  - `download_again(session: Session, media_file_id: int, client: TmdbClient, output_dir:
    Path) -> Title`;
  - `confirmed_counts(session: Session) -> dict[str, int]`;
  - `original_language(session: Session, path: str) -> str | None`;
  - `file_guess(row: MediaFile, max_year: int) -> Guess`;
  - messages `MOVIE_DURATION`, `ART_FAILED`.

- [ ] **Step 1: Write the failing tests**

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from sqlmodel import Session, select

from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.metadata.curation import (
    ART_FAILED,
    MOVIE_DURATION,
    Choice,
    confirm,
    confirm_all,
    confirmed_counts,
    download_again,
    original_language,
    run_suggestions,
)
from projeto_dvd.metadata.details import title_info
from projeto_dvd.metadata.tmdb import TmdbClient, TmdbError
from projeto_dvd.metadata.tmdb_models import DETAILS
from tests.tmdb_fakes import MOVIE, SHOW, router, search_page, season

RING = {"id": 101, "title": "Anel Mágico", "original_title": "The Magic Ring",
        "release_date": "2001-12-19", "poster_path": "/posterpt.jpg"}  # fmt: skip
IMAGES = {f"/t/p/original{p}": b"img" for p in
          ("/posterpt.jpg", "/backnull2.jpg", "/logoen.png", "/showposter.jpg", "/still3.jpg",
           "/still1.jpg")}  # fmt: skip


def tmdb(routes: dict[str, object], requests: list[httpx2.Request] | None = None) -> TmdbClient:
    return TmdbClient("t", "pt-BR", transport=httpx2.MockTransport(router(routes, requests)))


def add_file(session: Session, path: str, seconds: float = 10680.0) -> MediaFile:
    probe = {"streams": [], "format": {"duration": str(seconds)}}
    row = MediaFile(folder=path.split("/")[0], path=path, size=1, mtime_ns=1,
                    probe_json=json.dumps(probe), scanned_at=datetime.now(UTC))  # fmt: skip
    session.add(row)
    session.commit()
    return row


def test_run_suggestions_skips_confirmed(session: Session) -> None:
    first = add_file(session, "Anel/Anel Mágico (2001).mkv")
    done = add_file(session, "Anel/Outro.mkv")
    done.title = Title(status="confirmed", kind="movie", label="Outro", tmdb_id=5)
    session.commit()

    count = run_suggestions(session, "Anel", tmdb({"/3/search/movie": search_page(RING)}), 2026)

    assert count == 1
    assert first.title is not None
    assert (first.title.status, first.title.tmdb_id, first.title.label) == (
        "suggested", 101, "Anel Mágico (2001)",
    )  # fmt: skip
    assert done.title is not None and done.title.label == "Outro"


def test_run_suggestions_writes_nothing_when_tmdb_fails(session: Session) -> None:
    add_file(session, "Anel/Anel Mágico (2001).mkv")

    with pytest.raises(TmdbError):
        run_suggestions(session, "Anel", tmdb({"/3/search/movie": 401}), 2026)

    assert session.exec(select(Title)).all() == []


def test_confirm_movie_downloads_art_and_metadata(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)  # fmt: skip

    folder = tmp_path / "covers" / "Anel" / "Anel Mágico (2001)"
    assert sorted(p.name for p in folder.iterdir()) == [
        "backdrop.jpg", "logo.png", "metadata.json", "poster.jpg",
    ]  # fmt: skip
    assert json.loads((folder / "metadata.json").read_text())["title"] == "Anel Mágico"
    assert (title.status, title.label, title.message) == ("confirmed", "Anel Mágico (2001)", None)
    assert title.tmdb_json is not None
    assert title_info(DETAILS.validate_json(title.tmdb_json)).collection_id == 900


def test_confirm_movie_with_colon_in_title(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Disco: 1/a.mkv")
    assert row.id is not None
    routes = {"/3/movie/101": {**MOVIE, "title": "Anel: Parte 1"}, **IMAGES}

    confirm(session, row.id, Choice("movie", 101), tmdb(routes), tmp_path)

    folder = tmp_path / "covers" / "Disco - 1" / "Anel - Parte 1 (2001)"
    assert (folder / "poster.jpg").exists()


def test_confirm_warns_about_the_movie_duration(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv", seconds=228 * 60)
    assert row.id is not None

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)  # fmt: skip

    assert title.message == MOVIE_DURATION


def test_confirm_episode_fills_english_and_saves_the_still(
    session: Session, tmp_path: Path
) -> None:
    row = add_file(session, "Amigos/S01E02.mkv", seconds=22 * 60)
    assert row.id is not None
    routes = {"/3/tv/202": SHOW, "/3/tv/202/season/1": season(),
              "/3/tv/202/season/1?language=en-US": season("en"), **IMAGES,
              "/t/p/original/still2.jpg": b"img"}  # fmt: skip

    title = confirm(session, row.id, Choice("episode", 202, 1, 2), tmdb(routes), tmp_path)

    info = title_info(DETAILS.validate_json(title.tmdb_json or ""))
    assert (info.title, info.overview) == ("The Middle", "Resumo 2")
    assert title.label == "Amigos de Sempre · S01E02 · The Middle"
    folder = tmp_path / "covers" / "Amigos" / "Amigos de Sempre"
    assert (folder / "S01E02.jpg").exists()
    assert json.loads((folder / "S01E02.json").read_text())["episode"] == 2


def test_confirm_missing_episode_changes_nothing(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Amigos/S01E09.mkv")
    assert row.id is not None
    routes = {"/3/tv/202": SHOW, "/3/tv/202/season/1": season()}

    with pytest.raises(TmdbError):
        confirm(session, row.id, Choice("episode", 202, 1, 9), tmdb(routes), tmp_path)

    assert session.exec(select(Title)).all() == []


def test_art_failure_keeps_the_confirmation(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    routes = {"/3/movie/101": MOVIE, "/t/p/original/posterpt.jpg": b"img"}

    title = confirm(session, row.id, Choice("movie", 101), tmdb(routes), tmp_path)

    assert title.status == "confirmed"
    assert title.message is not None and title.message.startswith(ART_FAILED)


def test_unwritable_output_keeps_the_confirmation(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    blocked = tmp_path / "out"
    blocked.write_text("a file, not a folder")

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), blocked)  # fmt: skip

    assert title.status == "confirmed"
    assert title.message is not None and "chown" in title.message


def test_download_again_overwrites(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    client = tmdb({"/3/movie/101": MOVIE, **IMAGES})
    confirm(session, row.id, Choice("movie", 101), client, tmp_path)
    poster = tmp_path / "covers" / "Anel" / "Anel Mágico (2001)" / "poster.jpg"
    poster.write_bytes(b"old")

    download_again(session, row.id, client, tmp_path)

    assert poster.read_bytes() == b"img"


def test_confirm_all_skips_doubtful(session: Session, tmp_path: Path) -> None:
    sure = add_file(session, "Anel/a.mkv")
    doubtful = add_file(session, "Anel/b.mkv")
    sure.title = Title(status="suggested", kind="movie", label="Anel", tmdb_id=101)
    doubtful.title = Title(status="doubtful", kind="movie", label="Anel", tmdb_id=101)
    session.commit()

    count = confirm_all(session, "Anel", tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)

    assert count == 1
    assert (sure.title.status, doubtful.title.status) == ("confirmed", "doubtful")


def test_counts_and_original_language(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    add_file(session, "Anel/b.mkv")
    assert row.id is not None
    confirm(session, row.id, Choice("movie", 101), tmdb({"/3/movie/101": MOVIE, **IMAGES}),
            tmp_path)  # fmt: skip

    assert confirmed_counts(session) == {"Anel": 1}
    assert original_language(session, "Anel/a.mkv") == "en"
    assert original_language(session, "Anel/b.mkv") is None
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**

```python
"""The database and disk side of the curation: network first, then a short transaction."""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, col, select

from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.jobs.pipeline import cannot_write
from projeto_dvd.library.probe import summarize
from projeto_dvd.metadata.art import episode_code, pick_art, save_art
from projeto_dvd.metadata.details import (
    episode_label,
    generic_episode_name,
    movie_label,
    title_info,
)
from projeto_dvd.metadata.filename import Guess, Kind, guess
from projeto_dvd.metadata.matching import MISSING_EPISODE, Lookup, suggest_folder
from projeto_dvd.metadata.names import art_dir
from projeto_dvd.metadata.tmdb import NOT_FOUND, TmdbClient, TmdbError
from projeto_dvd.metadata.tmdb_models import (
    DETAILS,
    Details,
    Episode,
    EpisodeDetails,
    MovieDetails,
)

MOVIE_DURATION = "Duração bem diferente da do TMDB: versão estendida ou filme errado?"
ART_FAILED = "Arte não baixada: "
MOVIE_TOLERANCE = 0.15


@dataclass(frozen=True)
class Choice:
    kind: Kind
    tmdb_id: int
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None


def file_guess(row: MediaFile, max_year: int) -> Guess:
    relative = row.path.split("/", 1)[1]
    return guess(relative, row.folder, max_year)


def run_suggestions(session: Session, folder: str, client: TmdbClient, max_year: int) -> int:
    rows = [row for row in _folder_rows(session, folder)
            if row.title is None or row.title.status != "confirmed"]  # fmt: skip
    files = [(_id(row), file_guess(row, max_year), _duration(row)) for row in rows]
    found = suggest_folder(files, Lookup(client))  # network; raises before any write
    for row in rows:
        s = found[_id(row)]
        title = row.title or Title(status=s.status, kind=s.kind)
        title.status, title.kind, title.tmdb_id = s.status, s.kind, s.tmdb_id
        title.season, title.episode, title.episode_end = s.season, s.episode, s.episode_end
        title.label, title.poster_path, title.message = s.label, s.poster_path, s.message
        title.tmdb_json = None
        row.title = title
    session.commit()
    return sum(1 for row in rows if found[_id(row)].status != "not_found")


def fetch_details(choice: Choice, client: TmdbClient) -> Details:
    if choice.kind == "movie":
        return MovieDetails(kind="movie", movie=client.movie(choice.tmdb_id))
    if choice.season is None or choice.episode is None:
        raise TmdbError(MISSING_EPISODE.format("?"))
    show = client.tv(choice.tmdb_id)
    episode = _episode(client, choice.tmdb_id, choice.season, choice.episode)
    end = None
    if choice.episode_end:
        end = _episode(client, choice.tmdb_id, choice.season, choice.episode_end)
    return EpisodeDetails(kind="episode", show=show, episode=episode, episode_end=end)


def confirm(
    session: Session, media_file_id: int, choice: Choice, client: TmdbClient, output_dir: Path
) -> Title:
    row = _row(session, media_file_id)
    details = fetch_details(choice, client)
    warnings = _save(details, row.folder, client, output_dir, overwrite=False)
    warnings += _duration_warning(details, _duration(row))
    title = row.title or Title(status="confirmed", kind=choice.kind)
    info = title_info(details)
    title.status, title.kind, title.tmdb_id = "confirmed", choice.kind, choice.tmdb_id
    title.season, title.episode, title.episode_end = info.season, info.episode, info.episode_end
    title.label = _label(details)
    title.poster_path = details.movie.poster_path if details.kind == "movie" else (
        details.show.poster_path
    )  # fmt: skip
    title.message = " ".join(warnings) or None
    title.tmdb_json = DETAILS.dump_json(details).decode()
    row.title = title
    session.commit()
    return title


def confirm_all(session: Session, folder: str, client: TmdbClient, output_dir: Path) -> int:
    rows = [r for r in _folder_rows(session, folder) if r.title and r.title.status == "suggested"]
    for row in rows:
        assert row.title is not None and row.title.tmdb_id is not None
        choice = Choice(row.title.kind, row.title.tmdb_id, row.title.season,  # type: ignore[arg-type]
                        row.title.episode, row.title.episode_end)  # fmt: skip
        confirm(session, _id(row), choice, client, output_dir)  # one commit per title
    return len(rows)


def download_again(
    session: Session, media_file_id: int, client: TmdbClient, output_dir: Path
) -> Title:
    row = _row(session, media_file_id)
    title = row.title
    if title is None or title.tmdb_json is None:
        raise TmdbError(NOT_FOUND)
    details = DETAILS.validate_json(title.tmdb_json)
    warnings = _save(details, row.folder, client, output_dir, overwrite=True)
    title.message = " ".join(warnings) or None
    session.commit()
    return title


def confirmed_counts(session: Session) -> dict[str, int]:
    query = (
        select(MediaFile.folder, func.count())
        .join(Title)
        .where(Title.status == "confirmed")
        .group_by(MediaFile.folder)
    )
    return {folder: count for folder, count in session.exec(query).all()}


def original_language(session: Session, path: str) -> str | None:
    row = session.exec(select(MediaFile).where(MediaFile.path == path)).first()
    if row is None or row.title is None or row.title.tmdb_json is None:
        return None
    if row.title.status != "confirmed":
        return None
    return title_info(DETAILS.validate_json(row.title.tmdb_json)).original_language or None


def _save(
    details: Details, folder: str, client: TmdbClient, output_dir: Path, overwrite: bool
) -> list[str]:
    """Art and metadata.json; failures become warnings, never undo the confirmation."""
    info = title_info(details)
    if details.kind == "movie":
        name, metadata = movie_label(info.title, info.year), "metadata.json"
    else:
        code = episode_code(details.episode.season_number, details.episode.episode_number)
        name, metadata = details.show.name, f"{code}.json"
    warnings: list[str] = []
    try:
        directory = art_dir(output_dir, folder, name)
        directory.mkdir(parents=True, exist_ok=True)
        save_art(info.model_dump_json(indent=2).encode(), directory / metadata)
    except (OSError, ValueError):
        return [cannot_write("pasta de saída", output_dir)]
    for pick in pick_art(details):
        if pick.warning:
            warnings.append(pick.warning)
        target = directory / pick.name
        if target.exists() and not overwrite:
            continue
        try:
            save_art(client.image(pick.path), target)
        except TmdbError as error:
            warnings.append(f"{ART_FAILED}{pick.name} ({error.message})")
        except OSError:
            warnings.append(cannot_write("pasta de saída", output_dir))
            break
    return warnings


def _episode(client: TmdbClient, tv_id: int, season: int, number: int) -> Episode:
    code = episode_code(season, number)
    try:
        episodes = client.season(tv_id, season).episodes
    except TmdbError as error:
        raise TmdbError(MISSING_EPISODE.format(code)) if error.message == NOT_FOUND else error
    episode = next((e for e in episodes if e.episode_number == number), None)
    if episode is None:
        raise TmdbError(MISSING_EPISODE.format(code))
    if generic_episode_name(episode.name) or not episode.overview:
        english = client.season(tv_id, season, language="en-US").episodes
        en = next((e for e in english if e.episode_number == number), None)
        if en is not None:
            episode = episode.model_copy(update={
                "name": en.name if generic_episode_name(episode.name) else episode.name,
                "overview": episode.overview or en.overview,
            })  # fmt: skip
    return episode


def _label(details: Details) -> str:
    info = title_info(details)
    if details.kind == "movie":
        return movie_label(info.title, info.year)
    assert info.season is not None and info.episode is not None
    return episode_label(details.show.name, info.season, info.episode, info.title)


def _duration_warning(details: Details, duration: float | None) -> list[str]:
    runtime = details.movie.runtime if details.kind == "movie" else None
    if duration and runtime and abs(duration / 60 - runtime) > MOVIE_TOLERANCE * runtime:
        return [MOVIE_DURATION]
    return []


def _folder_rows(session: Session, folder: str) -> list[MediaFile]:
    query = select(MediaFile).where(MediaFile.folder == folder).order_by(col(MediaFile.path))
    return list(session.exec(query).all())


def _row(session: Session, media_file_id: int) -> MediaFile:
    row = session.get(MediaFile, media_file_id)
    if row is None:
        raise LookupError(media_file_id)
    return row


def _id(row: MediaFile) -> int:
    assert row.id is not None
    return row.id


def _duration(row: MediaFile) -> float | None:
    if row.probe_json is None:
        return None
    return summarize(json.loads(row.probe_json)).duration
```

Notes for the implementer: the `en-US` season call happens at most once per confirmation; in
`confirm_all`, keep a single `Lookup`-style cache if the test with many episodes shows repeated
season calls (not required by the spec). `confirm_all` must order rows by path (natural order is
not needed here). Remove the `type: ignore` in `confirm_all` by casting `row.title.kind` with a
small helper `_kind(value: str) -> Kind` that asserts the value.

- [ ] **Step 4: Run to verify they pass**, `make lint && make test`.

- [ ] **Step 5: Commit** `feat: confirm TMDB matches and download the default art`

---

## Group 5: screens

### Task 8: Match routes and templates

**Files:**
- Create: `src/projeto_dvd/api/curation.py`, `src/projeto_dvd/web/templates/_tmdb_section.html`,
  `_title_card.html`, `_title_search.html`
- Modify: `src/projeto_dvd/api/deps.py` (`get_tmdb`, `TmdbDep`), `src/projeto_dvd/app.py`
  (router), `src/projeto_dvd/api/library.py` (folder context `tmdb`),
  `src/projeto_dvd/web/templates/_folder_body.html` (order: summary, TMDB section, table, DVD
  block), `src/projeto_dvd/web/static/app.css` (`.button.small`, `.title-cards`,
  `.title-card`, `.thumb`, `.results`)
- Test: `tests/unit/test_curation_routes.py`

**Interfaces:**
- Consumes: Task 7 service; `Settings.tmdb_token`, `tmdb_language`.
- Produces: `get_tmdb(settings) -> Iterator[TmdbClient | None]`; `TmdbDep`;
  `tmdb_context(session: Session, folder: FolderView, enabled: bool, max_year: int) -> dict`
  used by `library.folder_page` and `library.scan`; routes of the spec table
  (`match_folder`, `confirm_folder`, `search_title`, `choose_title`, `title_card`,
  `title_art`); messages `BUSY`, `CONFIRMED_N`.

Template contract (the designer review in the spec is the reference):

- `_tmdb_section.html` renders `<section id="tmdb" class="tmdb">` with `<h2>Match no TMDB</h2>`;
  without token the neutral `.banner` with the `TMDB_TOKEN` text and the link; with token and
  scanned rows, the two `.button.secondary` (`hx-post` to `match_folder` / `confirm_folder`,
  `hx-target="#tmdb"`, `hx-swap="outerHTML"`, `hx-disabled-elt="find button"`,
  `hx-sync="this:drop"`, `hx-indicator="#tmdb-busy"`), `<span id="tmdb-busy" class="scanning"
  role="status">Falando com o TMDB e baixando artes... (pode levar alguns minutos)</span>`,
  the optional `banner`/`error`, and `<ul class="title-cards">` including `_title_card.html` per
  card.
- `_title_card.html` renders `<li class="title-card" id="title-{{ card.file_id }}"
  aria-live="polite">` with the thumbnail (`<img class="thumb" src="https://image.tmdb.org/t/p/
  w92{{ poster }}" width="46" height="69" loading="lazy" alt="">` or `<span class="thumb">`),
  the file name (`muted`, small), the badge and label per state, `message` with the warning
  icon, the error line when present, and the buttons (`.button.small`): "Confirmar" is a
  `hx-post` to `choose_title` with `hx-vals` of the suggestion; "Corrigir" a `hx-post` to
  `search_title` without fields; "Baixar artes de novo" when `message` starts with
  `ART_FAILED`. Buttons use `hx-target="closest li"` and `hx-swap="outerHTML"`.
- `_title_search.html` renders the same `<li>` with a `<form hx-post="search_title">`: radios
  `kind` (Filme/Série), `q`, `year`, and for series `season`/`episode` with
  `inputmode="numeric"`; a "Buscar" submit; "Cancelar" (`hx-get` to `title_card`); the results
  as `<button name="tmdb_id" value="..." hx-post="choose_title" hx-include="closest form">`
  with thumbnail, "Título (ano)", original title in `muted` when different and the overview cut
  at 120 characters; an empty result says "Nada encontrado. Tente outro nome ou o título
  original."

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_curation_routes.py`)

```python
import html
import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session, select

from projeto_dvd.api import curation, library
from projeto_dvd.api.deps import get_tmdb
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.library.probe import ProbeResult
from projeto_dvd.metadata.tmdb import TmdbClient
from tests.client import client_for
from tests.tmdb_fakes import MOVIE, router, search_page
from tests.tree import make_file

SAME = {"Sec-Fetch-Site": "same-origin"}
RING = {"id": 101, "title": "Anel Mágico", "original_title": "The Magic Ring",
        "release_date": "2001-12-19", "poster_path": "/posterpt.jpg",
        "overview": "x" * 300}  # fmt: skip
ROUTES: dict[str, object] = {
    "/3/search/movie": search_page(RING),
    "/3/movie/101": MOVIE,
    **{f"/t/p/original{p}": b"img" for p in ("/posterpt.jpg", "/backnull2.jpg", "/logoen.png")},
}
PROBE = json.dumps({"streams": [], "format": {"duration": "10680"}})


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    media = tmp_path / "media"
    make_file(media / "Anel" / "Anel Mágico (2001).mkv")
    (tmp_path / "out").mkdir()
    return Settings(media_dir=media, output_dir=tmp_path / "out", database_url=database_url,
                    tmdb_token=SecretStr("t"))  # fmt: skip


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(library, "run_ffprobe", lambda path: ProbeResult(json=PROBE, error=None))
    app = create_app(settings)

    def fake_tmdb() -> Iterator[TmdbClient]:
        transport = httpx2.MockTransport(router(ROUTES))
        with TmdbClient("t", "pt-BR", transport=transport) as tmdb:
            yield tmdb

    app.dependency_overrides[get_tmdb] = fake_tmdb
    with client_for(app) as test_client:
        test_client.post("/folders/Anel/scan", headers=SAME)
        yield test_client


def file_id(client: TestClient) -> int:
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        row = session.exec(select(MediaFile)).one()
        assert row.id is not None
        return row.id


def test_without_token_shows_how_to_configure(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"tmdb_token": None}))
    with client_for(app) as test_client:
        page = test_client.get("/folders/Anel").text

    assert "Curadoria desligada" in page
    assert "TMDB_TOKEN" in page
    assert "Buscar no TMDB" not in page


def test_empty_token_counts_as_none(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"tmdb_token": SecretStr("")}))
    with client_for(app) as test_client:
        assert "Curadoria desligada" in test_client.get("/folders/Anel").text


def test_folder_page_order_and_button(client: TestClient) -> None:
    page = client.get("/folders/Anel").text

    assert "Buscar no TMDB" in page
    assert page.index("Match no TMDB") < page.index('<table class="files">')
    assert "Ainda não buscado" in page


def test_search_suggests_and_confirm_all(client: TestClient, settings: Settings) -> None:
    found = client.post("/folders/Anel/match", headers=SAME).text

    assert "Sugestão" in found
    assert "Anel Mágico (2001)" in found
    assert "https://image.tmdb.org/t/p/w92/posterpt.jpg" in found
    done = client.post("/folders/Anel/confirm", headers=SAME).text
    assert "1 título confirmado" in done
    assert "Confirmado" in done
    assert (settings.output_dir / "covers" / "Anel" / "Anel Mágico (2001)" / "poster.jpg").exists()


def test_tmdb_error_is_shown_with_200(client: TestClient) -> None:
    ROUTES_BACKUP = dict(ROUTES)
    ROUTES["/3/search/movie"] = 401
    try:
        response = client.post("/folders/Anel/match", headers=SAME)
    finally:
        ROUTES.clear()
        ROUTES.update(ROUTES_BACKUP)

    assert response.status_code == 200
    assert "O TMDB recusou o token" in response.text


def test_correct_opens_the_search_with_the_guess(client: TestClient) -> None:
    response = client.post(f"/files/{file_id(client)}/search", headers=SAME)

    assert response.status_code == 200
    assert 'value="Anel Mágico"' in response.text
    assert "The Magic Ring" in response.text
    assert "x" * 121 not in response.text


def test_choose_confirms_and_returns_the_card(client: TestClient) -> None:
    fid = file_id(client)
    card = client.post(f"/files/{fid}/choose", headers=SAME,
                       data={"kind": "movie", "tmdb_id": "101"}).text  # fmt: skip

    assert f'id="title-{fid}"' in card
    assert "Confirmado" in card
    assert "<section" not in card


def test_choose_with_a_bad_form_shows_the_error(client: TestClient) -> None:
    card = client.post(f"/files/{file_id(client)}/choose", headers=SAME,
                       data={"kind": "movie", "tmdb_id": "abc"}).text  # fmt: skip

    assert "Formulário inválido" in card


def test_cancel_returns_the_card(client: TestClient) -> None:
    assert "Ainda não buscado" in client.get(f"/files/{file_id(client)}/card").text


def test_unknown_file_is_404(client: TestClient) -> None:
    assert client.get("/files/999/card").status_code == 404


def test_cross_site_post_is_refused(client: TestClient) -> None:
    response = client.post("/folders/Anel/match", headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403


def test_second_search_is_refused(client: TestClient) -> None:
    curation._tmdb_lock.acquire()
    try:
        response = client.post("/folders/Anel/match", headers=SAME)
    finally:
        curation._tmdb_lock.release()

    assert curation.BUSY in html.unescape(response.text)


def test_art_again_route(client: TestClient, settings: Settings) -> None:
    fid = file_id(client)
    client.post(f"/files/{fid}/choose", headers=SAME, data={"kind": "movie", "tmdb_id": "101"})

    card = client.post(f"/files/{fid}/art", headers=SAME).text

    assert "Confirmado" in card
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**

`api/deps.py` (add):

```python
def get_tmdb(settings: SettingsDep) -> Iterator[TmdbClient | None]:
    """A client per request (closed after it); None without a token."""
    token = settings.tmdb_token.get_secret_value() if settings.tmdb_token else ""
    if not token:
        yield None
        return
    with TmdbClient(token, settings.tmdb_language) as client:
        yield client


TmdbDep = Annotated[TmdbClient | None, Depends(get_tmdb)]
```

`api/curation.py`:

```python
"""TMDB match on the folder page. Errors come back inside the fragment, with status 200."""

import threading
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from projeto_dvd.api.deps import (
    FolderDep,
    MediaDirDep,
    SessionDep,
    SettingsDep,
    TmdbDep,
    templates,
)
from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.library.scan import FolderView, folder_view
from projeto_dvd.metadata.art import episode_code
from projeto_dvd.metadata.curation import (
    ART_FAILED,
    Choice,
    confirm,
    confirm_all,
    download_again,
    file_guess,
    run_suggestions,
)
from projeto_dvd.metadata.filename import Guess
from projeto_dvd.metadata.tmdb import TmdbClient, TmdbError

router = APIRouter()

# One TMDB action at a time (per process): two clicks would write the same rows.
_tmdb_lock = threading.Lock()
BUSY = "Já existe uma busca no TMDB em andamento. Aguarde ela terminar."
INVALID_FORM = "Formulário inválido. Recarregue a página e tente de novo."
DISABLED = "Curadoria desligada."


@dataclass(frozen=True)
class Card:
    file_id: int
    name: str
    title: Title | None
    guess: Guess


def max_year() -> int:
    return date.today().year + 1


def cards(session: Session, view: FolderView) -> list[Card]:
    rows = {row.path: row for row in session.exec(
        select(MediaFile).where(MediaFile.folder == view.name)
    ).all()}  # fmt: skip
    result = []
    for file in view.files:
        row = rows.get(file.video.path)
        if row is not None and row.id is not None:
            name = file.video.path.split("/", 1)[1]
            result.append(Card(row.id, name, row.title, file_guess(row, max_year())))
    return result


def tmdb_context(session: Session, view: FolderView, enabled: bool) -> dict[str, object]:
    return {"enabled": enabled, "cards": cards(session, view), "banner": None, "error": None,
            "art_failed": ART_FAILED}  # fmt: skip
```

(Add `from sqlmodel import select` to the imports.) The routes:

```python
@router.post("/folders/{name}/match", response_class=HTMLResponse, name="match_folder")
def match_folder(request: Request, name: str, folder: FolderDep, session: SessionDep,
                 media_dir: MediaDirDep, tmdb: TmdbDep) -> HTMLResponse:  # fmt: skip
    return _folder_action(request, name, folder, session, media_dir, tmdb,
                          lambda client: run_suggestions(session, name, client, max_year()),
                          None)  # fmt: skip


@router.post("/folders/{name}/confirm", response_class=HTMLResponse, name="confirm_folder")
def confirm_folder(request: Request, name: str, folder: FolderDep, session: SessionDep,
                   media_dir: MediaDirDep, settings: SettingsDep,
                   tmdb: TmdbDep) -> HTMLResponse:  # fmt: skip
    return _folder_action(
        request, name, folder, session, media_dir, tmdb,
        lambda client: confirm_all(session, name, client, settings.output_dir),
        lambda n: f"{n} título{'s' if n != 1 else ''} confirmado{'s' if n != 1 else ''}.",
    )  # fmt: skip


@router.post("/files/{file_id}/search", response_class=HTMLResponse, name="search_title")
async def search_title(request: Request, file_id: int, session: SessionDep,
                       tmdb: TmdbDep) -> HTMLResponse:  # fmt: skip
    row = _row(session, file_id)
    form = parse_qs((await request.body()).decode(), keep_blank_values=True)
    card = Card(file_id, row.path.split("/", 1)[1], row.title, file_guess(row, max_year()))
    query = _search_query(form, card)
    results, error = [], None
    if tmdb is None:
        error = DISABLED
    elif query is None:
        error = INVALID_FORM
    else:
        try:
            find = tmdb.search_movie if query["kind"] == "movie" else tmdb.search_tv
            results = find(str(query["q"]), query["year"])[:10]  # type: ignore[arg-type]
        except TmdbError as failure:
            error = failure.message
    context = {"card": card, "query": query or _default_query(card), "results": results,
               "error": error}  # fmt: skip
    return templates.TemplateResponse(request, "_title_search.html", context)
```

Implementer notes for the rest of the module (write them with these exact behaviors; the
tests above pin them):

- `_search_query(form, card) -> dict | None`: without any field, the card guess (`kind` from
  the guess, `q` = guess title, `year`, `season`, `episode`); with fields, parse `kind`
  (`movie`/`episode`), `q` (required, stripped), `year`/`season`/`episode` (empty or
  integers); `None` on a bad value. Use a small frozen dataclass `Query(kind, q, year, season,
  episode)` instead of a dict to avoid the `type: ignore`.
- `choose_title` (`POST /files/{file_id}/choose`): parse `kind`, `tmdb_id`, `season`,
  `episode`, `episode_end`; bad form → card with `INVALID_FORM`; else take the lock
  (`acquire(blocking=False)`, else card with `BUSY`), call `confirm(session, file_id, choice,
  tmdb, settings.output_dir)`, catch `TmdbError` → card with the message; render
  `_title_card.html` with the refreshed card.
- `title_card` (`GET /files/{file_id}/card`): the card. `title_art` (`POST
  /files/{file_id}/art`): like `choose_title` with `download_again`.
- `_folder_action(...)`: `tmdb is None` → section with `DISABLED` banner; lock not acquired →
  section with `BUSY`; run the action, catch `TmdbError` → section with `error`; on success
  `banner` = the message function result (or `None`); always 200 with `_tmdb_section.html`
  and the fresh `folder_view`.
- `_row(session, file_id)`: `session.get(MediaFile, file_id)` or `HTTPException(404)`.
- Every route that renders a card passes `{"card": card, "error": error, "art_failed":
  ART_FAILED, "enabled": tmdb is not None}`.

`api/library.py`: `folder_page` and `scan` add `"tmdb": tmdb_context(session, view,
enabled=bool(settings.tmdb_token and settings.tmdb_token.get_secret_value()))` (add
`SettingsDep` to both signatures). `app.py`: `app.include_router(curation.router)`.

`_folder_body.html`: move `{% include "_dvd_block.html" %}` to the end, and add
`{% if folder.status.name not in ("EMPTY", "NOT_SCANNED") %}{% include "_tmdb_section.html"
%}{% endif %}` right before `<div class="table-wrap">`; for `NOT_SCANNED` with a token, the
section shows "Escaneie a pasta para buscar no TMDB." (include it unconditionally and branch
inside the template on `tmdb.cards`).

CSS (append to `app.css`):

```css
.button.small { padding: 4px 12px; font-size: 0.9rem; min-height: 36px; }
.tmdb { margin: 24px 0; }
.title-cards { list-style: none; padding: 0; margin: 12px 0; display: grid; gap: 8px; }
.title-card { display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--surface); }
.title-card .title-text { flex: 1 1 240px; min-width: 0; }
.title-card .file-name { font-size: 0.8rem; overflow-wrap: anywhere; }
.title-card .actions { display: flex; gap: 8px; flex-wrap: wrap; }
.thumb { width: 46px; height: 69px; flex: none; border-radius: 4px; object-fit: cover;
  background: var(--border); display: inline-block; }
.results { list-style: none; padding: 0; margin: 8px 0; display: grid; gap: 6px; width: 100%; }
.results button { display: flex; gap: 12px; width: 100%; text-align: left; padding: 6px;
  background: var(--bg); color: var(--text); border: 1px solid var(--border);
  border-radius: var(--radius); cursor: pointer; }
.results button:hover, .results button:focus { border-color: var(--accent); }
.search-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: end; width: 100%; }
footer.credits { margin: 32px auto 16px; max-width: 1100px; padding: 0 16px;
  font-size: 0.8rem; display: flex; gap: 12px; align-items: center; }
footer.credits img { height: 12px; width: auto; }
```

- [ ] **Step 4: Run to verify they pass**, `make lint && make test`. Then run the app with a
  scratch `.env` without token (`docker compose up -d --build`), open the folder page, check
  the banner and the layout at 375 px wide (designer review); `docker compose down`.

- [ ] **Step 5: Commit** `feat: match videos with TMDB on the folder page`

### Task 9: Library line, TMDB attribution and logo

**Files:**
- Modify: `src/projeto_dvd/api/library.py`, `src/projeto_dvd/web/templates/library.html`,
  `src/projeto_dvd/web/templates/base.html`
- Create: `src/projeto_dvd/web/static/tmdb.svg` (the official TMDB logo from
  https://www.themoviedb.org/about/logos-attribution, downloaded once, checked to be an SVG
  with no script, committed with its sha256 in the README maintenance notes)
- Test: `tests/unit/test_library_routes.py`, `tests/unit/test_curation_routes.py`

- [ ] **Step 1: Write the failing tests**

(`tests/unit/test_curation_routes.py`, add)

```python
def test_library_line_counts_confirmed(client: TestClient) -> None:
    fid = file_id(client)
    assert "TMDB:" not in client.get("/").text
    client.post(f"/files/{fid}/choose", headers=SAME, data={"kind": "movie", "tmdb_id": "101"})

    assert "TMDB: todos confirmados" in client.get("/").text


def test_footer_attribution(client: TestClient) -> None:
    page = client.get("/").text

    assert "Este produto usa a API do TMDB" in page
    assert "/static/tmdb.svg" in page
```

(`tests/unit/test_library_routes.py`, add)

```python
def test_library_line_hidden_without_token(client: TestClient) -> None:
    assert "TMDB:" not in client.get("/").text
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**: `library_page` adds `"confirmed": confirmed_counts(session)` and
  `"tmdb_enabled": <token set>`; in `library.html`, inside the card after the duration line:

```html
      {% set done = confirmed.get(folder.name, 0) %}
      {% if tmdb_enabled and done %}
      {% if done == folder.files | length %}
      <span class="numbers ok-text">TMDB: todos confirmados</span>
      {% else %}
      <span class="muted numbers">TMDB: {{ done }} de {{ folder.files | length }} confirmados</span>
      {% endif %}
      {% endif %}
```

(`.ok-text { color: var(--ok); }` in the CSS.) In `base.html`, after `</main>`:

```html
  <footer class="credits muted">
    <a href="https://www.themoviedb.org/"><img src="{{ url_for('static', path='tmdb.svg') }}" alt="TMDB"></a>
    <span>Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB.</span>
  </footer>
```

Download the logo: `curl -fsSL <the "primary short" SVG URL from the attribution page> -o
src/projeto_dvd/web/static/tmdb.svg`, then `grep -ci "<script" tmdb.svg` must print 0 and
`head -c 200` must start with `<svg` or `<?xml`. If the page cannot be fetched, ask the
`designer` agent; do not invent a logo.

- [ ] **Step 4: Run to verify they pass**, `make lint && make test`.

- [ ] **Step 5: Commit** `feat: show TMDB progress per folder and the TMDB attribution`

---

## Group 6: DVD

### Task 10: Original language from TMDB in the DVD audio suggestion

**Files:**
- Modify: `src/projeto_dvd/planner/dvd_plan.py`, `src/projeto_dvd/api/dvd.py`
- Test: `tests/unit/test_dvd_plan.py`, `tests/unit/test_dvd_routes.py`

**Interfaces:**
- Produces: `suggest_choices(summary, options, duration, original_language: str | None =
  None) -> Choices`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_dvd_plan.py`, reusing the module's
  summary helpers; the summary has audio `eng` (index 1, first) and `jpn` (index 2), no
  Portuguese)

```python
def test_original_language_from_tmdb_when_the_track_exists() -> None:
    summary = summary_with_audio(("eng", 6), ("jpn", 2))  # existing helper or a local one

    choices = suggest_choices(summary, [], 7200.0, original_language="ja")

    assert choices.audio == (2,)


def test_original_language_from_tmdb_without_that_track_is_ignored() -> None:
    summary = summary_with_audio(("eng", 6), ("jpn", 2))

    assert suggest_choices(summary, [], 7200.0, original_language="cn").audio == (1,)
```

(If `test_dvd_plan.py` has no `summary_with_audio`, add a local helper that builds a
`Summary` through `summarize()` from a minimal ffprobe dict with a video stream and the given
audio streams, like the existing tests do.)

(`tests/unit/test_dvd_routes.py`, add) a test that inserts a confirmed `Title` with a
`tmdb_json` whose movie has `original_language="en"` for the "Filme" video whose audio is
`eng` (index 1) and `por` (index 2), opens `GET /folders/Filme/dvd` and checks the form still
selects both and starts with Portuguese; and a second where `original_language="fr"` (no track)
gives the same suggestion as without a title. Use `Movie.model_validate({**MOVIE,
"original_language": "en"})` from `tests.tmdb_fakes` and `DETAILS.dump_json(...)`.

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**

```python
def suggest_choices(
    summary: Summary,
    options: list[SubtitleOption],
    duration: float,
    original_language: str | None = None,
) -> Choices:
    picked = _suggest_audio(summary, original_language)
    ...  # unchanged


def _suggest_audio(summary: Summary, original_language: str | None) -> tuple[int, ...]:
    original = dvd_language(summary.audio[0].language)
    # TMDB knows the original language; use it only if the file has that track (TMDB also
    # has codes like "cn" and "xx").
    tmdb = dvd_language(original_language)
    if tmdb and any(dvd_language(t.language) == tmdb for t in summary.audio):
        original = tmdb
    ...  # unchanged from here
```

`api/dvd.py`: in `dvd_form`, `create_dvd` (the default on an invalid form) and
`_cards_context`, pass `original_language(session, source.video.path)` (import from
`projeto_dvd.metadata.curation`); `_cards_context` gains a `session` parameter (and
`dvd_estimate` passes it).

- [ ] **Step 4: Run to verify they pass**, `make lint && make test`.

- [ ] **Step 5: Commit** `feat: suggest the DVD audio in the original language from TMDB`

---

## Group 7: CI and docs

### Task 11: Compose, CI smoke, documentation and the final checks

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`, `README.md`,
  `README.pt-BR.md`, `CLAUDE.md`, `.claude/agents/curador.md`

- [ ] **Step 1: Compose and env**

`docker-compose.yml`, service `web`, `environment`:

```yaml
      # TMDB API Read Access Token (Bearer); empty turns the curation off. Only the web uses it.
      TMDB_TOKEN: ${TMDB_TOKEN:-}
      TMDB_LANGUAGE: ${TMDB_LANGUAGE:-pt-BR}
```

`.env.example` (append):

```
# TMDB (Phase 2): create a free account at themoviedb.org, then Settings > API and copy the
# "API Read Access Token" (the long one, not the short API key). Empty turns the matching off.
TMDB_TOKEN=
TMDB_LANGUAGE=pt-BR
```

- [ ] **Step 2: CI smoke** (in the existing "Smoke test" step, after the scan check)

```yaml
          curl -fsS "http://127.0.0.1:8000/folders/Disco%20Teste" -o folder.html
          grep -q "Curadoria desligada" folder.html
          grep -q "Este produto usa a API do TMDB" folder.html
```

- [ ] **Step 3: Documentation**, exactly the items of the spec's "Documentação":
  - READMEs (same content): status line (Phase 2, curation); section "Matching with TMDB" /
    "Match no TMDB": get the token, the flow (Buscar, Sugestão, Confira, Confirmar todas,
    Corrigir), where the art lands (`HOST_OUTPUT_DIR\covers\<pasta>\...`), the TMDB
    attribution sentence in English ("This product uses the TMDB API but is not endorsed or
    certified by TMDB."), the logo (`src/projeto_dvd/web/static/tmdb.svg`) and the
    non-commercial use; `httpx2` in the stack; the logo sha256 in maintenance.
  - `CLAUDE.md`: 3.2, 6, 6.1 (`TMDB_TOKEN` replaces `TMDB_API_KEY`), 7 (tree with
    `metadata/`), 7.1 (`Title`), 7.2, 9 (`MockTransport`), 10, 12 (Phase 2 checkbox stays open
    until the final QA with the token? No: mark it done with "QA com token no final", like the
    Phase 3 two-stage note), 13, Estado atual, Log de decisões (the spec's last section plus
    the rulings from the ledger).
  - `.claude/agents/curador.md`: `respx` → `httpx2.MockTransport`.

- [ ] **Step 4: Full verification**

Run: `make lint && make test && make test-slow`
Expected: all green; coverage ≥ 90% (target 100%).

Run: `docker compose up -d --build` with a scratch `.env` (no token), open the library and a
folder page, check the banner and the footer; `docker compose down`.

- [ ] **Step 5: Commit, push, PR**

```bash
git add -A docker-compose.yml .env.example .github README.md README.pt-BR.md CLAUDE.md .claude/agents/curador.md
git commit -m "docs: document the TMDB curation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin feat/fase-2-curadoria
```

  The PR (`gh pr create`) describes the phase, links the spec and the plan, lists the rulings
  and deferred minors, and carries the manual QA checklist for the end of the project (create
  the token, put it in `.env`, `docker compose up -d`, Buscar in a movie folder and in a series
  folder, check "Senhor dos Aneis" finds "Senhor dos Anéis", the pt-BR episode names, Corrigir,
  the art in `covers\`). Ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
  The Vini merges.
