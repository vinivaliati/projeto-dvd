"""Where everything goes on a menu page. Pure: text widths come from an injected measure.

Text is placed in square pixels (854x480 for 16:9, 640x480 for 4:3; DVD pixels are not
square). Button boxes are in the 720x480 frame the subpicture uses. Every box coordinate is
even and no box is thinner than 2 lines, because the menu is shown interlaced.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from projeto_dvd.planner.disc_plan import MenuItem, MenuPage

Measure = Callable[[str, int], float]  # (text, size) -> width in square pixels, bold
FRAME_WIDTH = 720
SAFE_TOP, SAFE_BOTTOM = 48, 432
HEADING_BOTTOM = 120
FOOTER_TOP, FOOTER_BOTTOM = 400, 432
LIST_END_WITH_FOOTER = 396
TEXT_INDENT = 32  # from the column edge: the marker (8 px) and its gap (16 px) come first
TEXT_RIGHT = 16
MARKER_LEFT, MARKER_WIDTH = 8, 8
BOX_GAP = 4
NORMAL = (40, 36, 28)  # step, band, font size
LARGE = (56, 48, 34)
FOOTER_SIZE = 24
SMALL_SIZE = 24
HEADING_LARGE, HEADING_SMALL = 34, 28
ELLIPSIS = "…"
COLUMNS = {  # square-pixel column of the buttons, by aspect and side
    ("16:9", "left"): (85, 565), ("16:9", "right"): (289, 769),
    ("4:3", "left"): (64, 512), ("4:3", "right"): (128, 576),
}  # fmt: skip


@dataclass(frozen=True)
class Box:
    x0: int
    y0: int
    x1: int
    y1: int


@dataclass(frozen=True)
class ButtonGeometry:
    number: int  # 1-based: the list items, then the footer from left to right
    item: MenuItem
    box: Box  # the band, in 720x480
    marker: Box  # in 720x480
    label: str  # fitted to the column
    text_x: float  # square pixels; the anchor point of the text
    text_y: float
    anchor: Literal["lm", "mm"]  # Pillow anchors: left-middle (list) or middle-middle (footer)
    font_size: int
    up: int
    down: int
    left: int
    right: int


@dataclass(frozen=True)
class PageLayout:
    width: int  # square-pixel width of the background
    column: tuple[int, int]  # square pixels
    heading_lines: tuple[str, ...]
    heading_size: int
    text_x: float  # left edge of the heading and of the list text
    buttons: tuple[ButtonGeometry, ...]


def square_width(aspect: str) -> int:
    return 854 if aspect == "16:9" else 640


def to_720(x: float, width: int) -> int:
    return round(x * FRAME_WIDTH / width / 2) * 2


def letterbox_y(y: int) -> int:
    """Where a 16:9 line lands on a 4:3 TV that letterboxes it (60 lines of bar on top)."""
    return round((60 + y * 3 / 4) / 2) * 2


def fit_label(text: str, width: float, size: int, measure: Measure) -> tuple[str, int]:
    """One line: the given size, then 24, then cut with an ellipsis."""
    for candidate in dict.fromkeys((size, SMALL_SIZE)):
        if measure(text, candidate) <= width:
            return text, candidate
    return _cut(text, width, SMALL_SIZE, measure), SMALL_SIZE


def layout_page(page: MenuPage, aspect: str, side: str, measure: Measure) -> PageLayout:
    width = square_width(aspect)
    left, right = COLUMNS[(aspect, side)]
    text_x = left + TEXT_INDENT
    text_width = right - left - TEXT_INDENT - TEXT_RIGHT
    lines, heading_size = _heading(page.heading, text_width, measure)
    step, band, size = LARGE if page.large else NORMAL
    footer = [(slot, item) for slot, item in enumerate(page.footer) if item is not None]
    end = LIST_END_WITH_FOOTER if footer else SAFE_BOTTOM
    count = len(page.items)
    x0, x1 = to_720(left, width), to_720(right, width)
    marker_x = (to_720(left + MARKER_LEFT, width), to_720(left + MARKER_LEFT + MARKER_WIDTH, width))
    geometry: list[dict[str, object]] = []
    for index, item in enumerate(page.items):
        y1 = end - (count - 1 - index) * step
        label, font = fit_label(item.label, text_width, size, measure)
        geometry.append({
            "item": item, "box": Box(x0, y1 - band, x1, y1),
            "marker": Box(marker_x[0], y1 - band, marker_x[1], y1), "label": label,
            "text_x": text_x, "text_y": y1 - band / 2, "anchor": "lm", "font_size": font,
        })  # fmt: skip
    third = (x1 - x0) / 3
    square_third = (right - left) / 3
    for slot, item in footer:
        bx0 = _even(x0 + slot * third) + (BOX_GAP // 2 if slot else 0)
        bx1 = _even(x0 + (slot + 1) * third) - (BOX_GAP // 2 if slot < 2 else 0)
        label, font = fit_label(item.label, square_third - 2 * MARKER_LEFT, FOOTER_SIZE, measure)
        geometry.append({
            "item": item, "box": Box(bx0, FOOTER_TOP, bx1, FOOTER_BOTTOM),
            "marker": Box(bx0, FOOTER_BOTTOM - 4, bx1, FOOTER_BOTTOM), "label": label,
            "text_x": left + (slot + 0.5) * square_third,
            "text_y": (FOOTER_TOP + FOOTER_BOTTOM) / 2, "anchor": "mm", "font_size": font,
        })  # fmt: skip
    buttons = tuple(
        ButtonGeometry(number=n, **_arrows(n, count, footer), **fields)  # type: ignore[arg-type]
        for n, fields in enumerate(geometry, 1)
    )
    return PageLayout(width=width, column=(left, right), heading_lines=lines,
                      heading_size=heading_size, text_x=text_x, buttons=buttons)  # fmt: skip


def _arrows(number: int, count: int, footer: list[tuple[int, MenuItem]]) -> dict[str, int]:
    slots = {slot: count + 1 + i for i, (slot, _) in enumerate(footer)}
    if number <= count:
        down = number + 1 if number < count else _nearest(slots, 1, number)
        return {"up": max(number - 1, 1), "down": down, "left": number, "right": number}
    slot = next(s for s, n in slots.items() if n == number)
    lefts = [n for s, n in slots.items() if s < slot]
    rights = [n for s, n in slots.items() if s > slot]
    return {
        "up": count, "down": number,
        "left": lefts[-1] if lefts else number, "right": rights[0] if rights else number,
    }  # fmt: skip


def _nearest(slots: dict[int, int], wanted: int, default: int) -> int:
    for slot in (wanted, wanted - 1, wanted + 1):
        if slot in slots:
            return slots[slot]
    return default


def _heading(text: str, width: float, measure: Measure) -> tuple[tuple[str, ...], int]:
    if measure(text, HEADING_LARGE) <= width:
        return (text,), HEADING_LARGE
    words = text.split()
    first = ""
    while words and measure(f"{first} {words[0]}".strip(), HEADING_SMALL) <= width:
        first = f"{first} {words.pop(0)}".strip()
    if not first:  # a single word wider than the column
        return (_cut(text, width, HEADING_SMALL, measure),), HEADING_SMALL
    rest = " ".join(words)
    if not rest:
        return (first,), HEADING_SMALL
    if measure(rest, HEADING_SMALL) > width:
        rest = _cut(rest, width, HEADING_SMALL, measure)
    return (first, rest), HEADING_SMALL


def _cut(text: str, width: float, size: int, measure: Measure) -> str:
    while text and measure(text + ELLIPSIS, size) > width:
        text = text[:-1]
    return text.rstrip() + ELLIPSIS


def _even(value: float) -> int:
    return round(value / 2) * 2
