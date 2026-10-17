"""The art a cover can use: TMDB options from the saved details, the default and the chosen one.

No API call lists the options: the posters and backdrops came with the confirmed details.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image as PILImage

from projeto_dvd.metadata.curation import title_art_dir
from projeto_dvd.metadata.details import title_info
from projeto_dvd.metadata.names import safe_name
from projeto_dvd.metadata.tmdb_models import CollectionRef, Details, Image, Images
from projeto_dvd.planner.disc import DiscTitle

FRONT_PX = (1600, 2232)  # the front panel with its bleed at 300 DPI
PRINT_DPI = 300
MIN_DPI = 150
POSTER_LANGUAGES = ("pt", None, "en")
FRONT_NAMES = ("front.jpg", "front.png")
Kind = Literal["poster", "backdrop"]


@dataclass(frozen=True)
class ArtOption:
    path: str  # TMDB path, .jpg or .png only
    kind: Kind
    language: str | None
    dpi: int | None  # None: unknown resolution
    owner: str  # the work it belongs to, for the grid


def print_dpi(width: int, height: int) -> int:
    """The resolution of an image covering the front panel: its weaker side decides."""
    return int(PRINT_DPI / max(FRONT_PX[0] / width, FRONT_PX[1] / height))


def art_options(titles: Sequence[DiscTitle], details: Mapping[str, Details]) -> list[ArtOption]:
    """Season or collection posters, then the posters of each work, then every backdrop."""
    found = [details[t.path] for t in titles if t.path in details]
    works: dict[tuple[str, int], Details] = {}
    for detail in found:
        works.setdefault(_work(detail), detail)  # the episodes of a series share the art
    options = _shared_posters(found)
    for detail in works.values():
        posters = _images(detail).posters
        for language in POSTER_LANGUAGES:
            chosen = [i for i in posters if i.iso_639_1 == language]
            options += _sorted(chosen, "poster", _owner(detail))
    for with_text in (False, True):  # a backdrop with a language may carry text
        for detail in works.values():
            chosen = [i for i in _images(detail).backdrops if bool(i.iso_639_1) == with_text]
            options += _sorted(chosen, "backdrop", _owner(detail))
    seen: set[str] = set()
    unique = []
    for option in options:
        if option.path not in seen and _usable(option):
            seen.add(option.path)
            unique.append(option)
    return unique


def default_front(
    output_dir: Path, folder: str, titles: Sequence[DiscTitle], details: Mapping[str, Details]
) -> Path | None:
    """The poster the curation already downloaded, of the first title in disc order that has one."""
    for title in titles:
        if title.path not in details:
            continue
        poster = title_art_dir(output_dir, folder, details[title.path]) / "poster.jpg"
        if poster.is_file():
            return poster
    return None


def front_file(output_dir: Path, folder: str) -> Path | None:
    """The chosen art of the folder, if it is there and opens."""
    for name in FRONT_NAMES:
        path = output_dir / "covers" / safe_name(folder) / name
        if path.is_file() and _opens(path):
            return path
    return None


def _shared_posters(found: Sequence[Details]) -> list[ArtOption]:
    episodes = [d for d in found if d.kind == "episode"]
    if episodes and len(episodes) == len(found):
        seasons = {(d.show.id, d.episode.season_number) for d in episodes}
        poster = episodes[0].season_poster_path
        if len(seasons) == 1 and poster:
            season = episodes[0].episode.season_number
            name = f"{_owner(episodes[0])}: Temporada {season}"
            return [ArtOption(poster, "poster", None, None, name)]
        return []
    counts: dict[int, int] = {}
    collections: dict[int, CollectionRef] = {}
    for detail in found:
        if detail.kind == "movie" and detail.movie.belongs_to_collection:
            collection = detail.movie.belongs_to_collection
            counts[collection.id] = counts.get(collection.id, 0) + 1
            collections.setdefault(collection.id, collection)
    return [
        ArtOption(c.poster_path, "poster", None, None, c.name)
        for c in collections.values()
        if counts[c.id] >= 2 and c.poster_path
    ]


def _sorted(images: Sequence[Image], kind: Kind, owner: str) -> list[ArtOption]:
    options = [
        ArtOption(i.file_path, kind, i.iso_639_1, _dpi(i, kind), owner)
        for i in images
        if i.file_path
    ]
    votes = {i.file_path: (i.vote_average, i.width) for i in images}
    return sorted(
        options,
        key=lambda o: ((o.dpi or 0) >= PRINT_DPI, *votes[o.path]),
        reverse=True,
    )


def _dpi(image: Image, kind: Kind) -> int | None:
    if not image.width:
        return None
    height = image.height or round(image.width * (1.5 if kind == "poster" else 9 / 16))
    return print_dpi(image.width, height)


def _usable(option: ArtOption) -> bool:
    if not option.path.lower().endswith((".jpg", ".png")):
        return False
    return option.dpi is None or option.dpi >= MIN_DPI


def _work(detail: Details) -> tuple[str, int]:
    return ("movie", detail.movie.id) if detail.kind == "movie" else ("tv", detail.show.id)


def _images(detail: Details) -> Images:
    return detail.movie.images if detail.kind == "movie" else detail.show.images


def _owner(detail: Details) -> str:
    info = title_info(detail)
    return info.title if detail.kind == "movie" else info.show or detail.show.name


def _opens(path: Path) -> bool:
    try:
        with PILImage.open(path) as image:
            image.verify()
    except (OSError, SyntaxError, PILImage.DecompressionBombError):
        return False
    return True
