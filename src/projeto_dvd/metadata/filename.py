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
_YEAR = re.compile(r"(?<!\w)(19\d\d|20\d\d)(?!\w)")
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
    text = re.sub(r"\b((?:[A-Za-z]\.){2,})(?=[A-Za-z])", r"\1 ", text)  # "E.T.the" -> "E.T. the"
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
    if _YEAR.fullmatch(title):
        return False  # 1917, 1984, 2012: movies named after a year
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
