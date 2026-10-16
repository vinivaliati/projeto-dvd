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
