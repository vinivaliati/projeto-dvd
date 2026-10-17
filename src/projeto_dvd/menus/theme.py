"""The menu theme: a closed palette, the accent suggested by the backdrop, the backdrops.

A closed palette means no unreadable choice exists: every color is legible on a dark
background and keeps its channels inside the TV range (16 to 235).
"""

import colorsys
from pathlib import Path

from PIL import Image

from projeto_dvd.metadata.names import art_dir, safe_name

PALETTE: dict[str, tuple[str, str]] = {
    "ambar": ("Âmbar", "#E0A526"),
    "vermelho": ("Vermelho", "#D9483B"),
    "azul": ("Azul", "#4C9BE0"),
    "verde": ("Verde", "#3DB894"),
    "lilas": ("Lilás", "#A685E0"),
    "gelo": ("Gelo", "#E6E6E6"),
}
DEFAULT_ACCENT = "ambar"
TEXT = "#EBEBEB"
SECONDARY = "#B4B4B4"
OUTLINE = "#101010"
MIN_VALUE = 0.25
MIN_SATURATION = 0.20


def available_backdrops(output_dir: Path, folder: str) -> tuple[str, ...]:
    """The art folders of this disc that have a backdrop (downloaded by the curation)."""
    covers = output_dir / "covers" / safe_name(folder)
    return tuple(sorted(path.parent.name for path in covers.glob("*/backdrop.jpg")))


def backdrop_path(output_dir: Path, folder: str, name: str) -> Path:
    """Always built here, never taken from a form; ValueError outside the covers folder."""
    return art_dir(output_dir, folder, name) / "backdrop.jpg"


def auto_accent(image: Image.Image | None) -> str:
    """The palette color closest in hue to the dominant color of the backdrop."""
    if image is None:
        return DEFAULT_ACCENT
    small = image.convert("RGB").resize((64, 36)).quantize(8, method=Image.Quantize.MEDIANCUT)
    palette = small.getpalette() or []
    best_weight, best_hue = 0.0, None
    for count, color in small.getcolors() or []:
        index = int(color)  # type: ignore[arg-type]  # a palette image gives indices
        red, green, blue = (channel / 255 for channel in palette[index * 3 : index * 3 + 3])
        hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
        if value < MIN_VALUE or saturation < MIN_SATURATION:
            continue
        if count * saturation > best_weight:
            best_weight, best_hue = count * saturation, hue
    if best_hue is None:
        return DEFAULT_ACCENT
    hue = best_hue
    return min(
        (key for key in PALETTE if key != "gelo"),
        key=lambda key: _hue_distance(hue, _hue(PALETTE[key][1])),
    )


def resolve_accent(accent: str, image: Image.Image | None) -> str:
    key = auto_accent(image) if accent == "auto" else accent
    return PALETTE[key][1]


def _hue(color: str) -> float:
    red, green, blue = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(red, green, blue)[0]


def _hue_distance(a: float, b: float) -> float:
    return min(abs(a - b), 1 - abs(a - b))
