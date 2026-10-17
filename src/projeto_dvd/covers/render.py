"""Draw the printed cover and the disc labels with Pillow, and save them as one PDF.

Everything is placed in mm and converted at the DPI of the render: 300 for the PDF, 50 for the
preview. Text sizes are decided in mm, so both break the lines the same way.
"""

from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from projeto_dvd.covers.content import CoverContent, CoverLine
from projeto_dvd.covers.layout import (
    RULER_INSET,
    Measure,
    cover_layout,
    edges_px,
    fit_lines,
    fit_spine,
)
from projeto_dvd.covers.sizes import CASE, LABELS, MARKS, MM_PER_INCH, px
from projeto_dvd.menus import render as menu
from projeto_dvd.menus.render import NEUTRAL_NEAR, Font, Fonts, cover_crop, neutral

PDF_DPI = 300
POINT = MM_PER_INCH / 72  # one point in mm
CAP = 0.72  # cap height of DejaVu Sans, in em
WHITE, SECONDARY, SOFT, FAINT = "#FFFFFF", "#C8C8C8", "#E1E1E1", "#B4B4B4"
RULE, INK, BLACK = "#6E6E6E", "#5A5A5A", "#000000"
NAME_SIZES = tuple(float(size) for size in range(28, 19, -1))
LABEL_SIZES = tuple(float(size) for size in range(16, 10, -1))
TOP_SHADE, BOTTOM_SHADE, SHADE_FADE = 0.80, 0.85, 30.0
BACK_BRIGHTNESS = 0.22
BLUR_MM = 4.0
LABEL_COLOR, LABEL_BRIGHTNESS = 0.85, 0.35
EPISODE_COLUMNS_FROM = 13
NOTICE = "Imprima em tamanho real (100%, sem ajustar à página)."
ATTRIBUTION = (
    "Dados e imagens: TMDB. Este produto usa a API do TMDB, mas não é endossado nem "
    "certificado pelo TMDB."
)


class _Pen:
    """Draws on one image in mm (from its top left corner) at a DPI."""

    def __init__(self, image: Image.Image, dpi: int, fonts: Fonts) -> None:
        self.image, self.dpi, self.fonts = image, dpi, fonts
        self.draw = ImageDraw.Draw(image)

    def px(self, mm: float) -> int:
        return px(mm, self.dpi)

    def font(self, pt: float, bold: bool) -> Font:
        return self.fonts(max(1, round(pt * self.dpi / 72)), bold)

    def width(self, text: str, pt: float, bold: bool = False) -> float:
        return self.font(pt, bold).getlength(text) * MM_PER_INCH / self.dpi

    def measure(self, bold: bool = False) -> Measure:
        return lambda text, pt: self.width(text, pt, bold)

    def text(self, x: float, y: float, text: str, pt: float, bold: bool = False,
             fill: str = WHITE, anchor: str = "ls") -> None:  # fmt: skip
        self.draw.text((self.px(x), self.px(y)), text, font=self.font(pt, bold), fill=fill,
                       anchor=anchor)  # fmt: skip

    def rect(self, x: float, y: float, w: float, h: float, fill: str) -> None:
        top, left = self.px(y), self.px(x)
        box = (left, top, max(left, self.px(x + w) - 1), max(top, self.px(y + h) - 1))
        self.draw.rectangle(box, fill=fill)

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float, fill: str) -> None:
        points = (self.px(x1), self.px(y1), self.px(x2), self.px(y2))
        self.draw.line(points, fill=fill, width=max(1, self.px(width)))


def render_cover(
    content: CoverContent,
    front: Image.Image | None,
    back: Image.Image | None,
    accent: str,
    show_name: bool,
    dpi: int,
    fonts: Fonts | None = None,
) -> Image.Image:
    """The A4 turned: back | spine | front with the bleed, the marks, the ruler and the notice."""
    fonts = fonts or menu.dejavu  # looked up at call time, so tests can swap the font
    layout = cover_layout()
    page = Image.new("RGB", (px(layout.page[0], dpi), px(layout.page[1], dpi)), WHITE)
    edges = edges_px([layout.back.x, layout.spine.x, layout.front.x,
                      layout.front.x + layout.front.w], dpi)  # fmt: skip
    top, bottom = px(layout.bleed.y, dpi), px(layout.bleed.y + layout.bleed.h, dpi)
    sizes = [(right - left, bottom - top) for left, right in pairwise(edges)]
    panels = (
        _back(content, back or front, accent, sizes[0], dpi, fonts),
        _spine(content, accent, sizes[1], dpi, fonts),
        _front(content, front, accent, show_name, sizes[2], dpi, fonts),
    )
    for left, panel in zip(edges, panels, strict=False):
        page.paste(panel, (left, top))
    pen = _Pen(page, dpi, fonts)
    for x1, y1, x2, y2 in (*layout.crop_marks, *layout.fold_marks):
        pen.line(x1, y1, x2, y2, MARKS.width, BLACK)
    x, y = layout.ruler
    pen.line(x, y, x + 50, y, MARKS.width, INK)
    for tick in range(0, 51, 10):
        pen.line(x + tick, y, x + tick, y - (2.5 if tick in (0, 50) else 1.5), MARKS.width, INK)
    pen.text(x + 52, y, "50 mm", 6, fill=INK)
    # On the ruler line, right of the fold marks: at the top it would cross them.
    pen.text(layout.cut.x + layout.cut.w - RULER_INSET, y, NOTICE, 7, fill=INK, anchor="rs")
    return page


def render_labels(
    content: CoverContent, art: Image.Image | None, accent: str, dpi: int,
    fonts: Fonts | None = None,
) -> Image.Image:  # fmt: skip
    """The A4 sheet of round labels, the art from the hole out to the bleed of each one."""
    fonts = fonts or menu.dejavu
    page = Image.new("RGB", (px(210, dpi), px(297, dpi)), WHITE)
    outer = LABELS.diameter / 2 + LABELS.bleed
    inner = LABELS.hole / 2 - LABELS.hole_bleed
    side = px(2 * outer, dpi)
    if art is None:
        disc = neutral((side, side), accent, "left")
    else:
        disc = ImageEnhance.Color(cover_crop(art, (side, side))).enhance(LABEL_COLOR)
        disc = ImageEnhance.Brightness(disc).enhance(LABEL_BRIGHTNESS)
    mask = Image.new("L", (side, side), 0)
    ring = ImageDraw.Draw(mask)
    ring.ellipse((0, 0, side - 1, side - 1), fill=255)
    pen = _Pen(page, dpi, fonts)
    hole = inner * dpi / MM_PER_INCH + 1  # one pixel more: the paste rounds to whole pixels
    for cx, cy in LABELS.centers:
        page.paste(disc, (px(cx - outer, dpi), px(cy - outer, dpi)), mask)
        x, y = cx * dpi / MM_PER_INCH, cy * dpi / MM_PER_INCH
        pen.draw.ellipse((x - hole, y - hole, x + hole, y + hole), fill=WHITE)
        name, size = fit_spine(content.disc_name, 80.0, pen.measure(True), LABEL_SIZES)
        pen.text(cx, cy - 33, name, size, bold=True, anchor="ms")
        if content.secondary:
            pen.text(cx, cy - 27, content.secondary, 9, anchor="ms")
        pen.text(cx, cy + 30, content.profile, 9, bold=True, anchor="ms")
    return page


def write_pdf(cover: Image.Image, labels: Image.Image, target: Path) -> None:
    """Two pages at 300 DPI; JPEG at quality 95 without chroma subsampling keeps text sharp."""
    part = target.with_name(target.name + ".part")
    try:
        cover.save(part, "PDF", save_all=True, append_images=[labels], resolution=PDF_DPI,
                   quality=95, subsampling=0)  # fmt: skip
        part.replace(target)
    except OSError:
        part.unlink(missing_ok=True)
        raise


def load_art(path: Path | None) -> Image.Image | None:
    if path is None:
        return None
    try:
        with Image.open(path) as image:
            return image.convert("RGB")
    except (OSError, Image.DecompressionBombError):
        return None


def _front(
    content: CoverContent, art: Image.Image | None, accent: str, show_name: bool,
    size: tuple[int, int], dpi: int, fonts: Fonts,
) -> Image.Image:  # fmt: skip
    image = cover_crop(art, size) if art else neutral(size, accent, "left")
    pen = _Pen(image, dpi, fonts)
    top, bottom, center = CASE.bleed, CASE.bleed + CASE.height, CASE.panel_width / 2
    if show_name:
        lines, pt = _fit_name(content.disc_name, pen)
        baselines = [top + 16 + CAP * pt * POINT + n * (pt + 3) * POINT for n in range(len(lines))]
        end = baselines[-1]
        if content.secondary:
            end += (8 + CAP * 12) * POINT
        _shade(image, pen.px(end + 6), pen.px(SHADE_FADE), TOP_SHADE, from_top=True)
        for line, y in zip(lines, baselines, strict=True):
            pen.text(center, y, line, pt, bold=True, anchor="ms")
        if content.secondary:
            pen.text(center, end, content.secondary, 12, fill=SECONDARY, anchor="ms")
    solid = image.height - pen.px(bottom - 24)
    _shade(image, solid, pen.px(SHADE_FADE), BOTTOM_SHADE, from_top=False)
    if content.front_text:
        baseline = bottom - 12
        pen.text(center, baseline, content.front_text, 11, bold=True, anchor="ms")
        pen.rect(center - 6, baseline - CAP * 11 * POINT - 4 - 0.7, 12, 0.7, accent)
    return image


def _fit_name(name: str, pen: _Pen) -> tuple[list[str], float]:
    width = CASE.panel_width - 2 * CASE.text_margin
    lines: list[str] = []
    for pt in NAME_SIZES:
        lines = fit_lines(name, width, 2, pt, pen.measure(True))
        if " ".join(lines) == " ".join(name.split()):
            return lines, pt
    return lines, NAME_SIZES[-1]


def _shade(image: Image.Image, solid: int, fade: int, alpha: float, from_top: bool) -> None:
    """Black over the art, solid near one edge and fading out linearly."""
    width, height = image.size
    column = [
        round(alpha * 255 * (1.0 if d <= solid else max(0.0, 1 - (d - solid) / max(1, fade))))
        for d in range(height)
    ]
    mask = Image.new("L", (1, height))
    mask.putdata(column if from_top else column[::-1])
    image.paste((0, 0, 0), (0, 0, width, height), mask.resize((width, height)))


def _spine(
    content: CoverContent, accent: str, size: tuple[int, int], dpi: int, fonts: Fonts
) -> Image.Image:
    """Drawn lying down and turned, so it reads from the bottom up."""
    width, length = size
    image = Image.new("RGB", (length, width), NEUTRAL_NEAR)
    pen = _Pen(image, dpi, fonts)
    start, end = CASE.bleed + CASE.spine_end, CASE.bleed + CASE.height - CASE.spine_end
    middle = CASE.spine / 2
    room = end - start
    if content.spine_extra:
        pen.text(end, middle, content.spine_extra, 12, bold=True, fill=accent, anchor="rm")
        room -= pen.width(content.spine_extra, 12, True) + 6
    if content.spine_text:
        name, pt = fit_spine(content.spine_text, room, pen.measure(True))
        pen.text(start, middle, name, pt, bold=True, anchor="lm")
    return image.rotate(90, expand=True)


def _back(
    content: CoverContent, art: Image.Image | None, accent: str, size: tuple[int, int],
    dpi: int, fonts: Fonts,
) -> Image.Image:  # fmt: skip
    if art is None:
        image = neutral(size, accent, "right")
    else:
        small = cover_crop(art, (max(1, size[0] // 4), max(1, size[1] // 4)))
        blurred = small.filter(ImageFilter.GaussianBlur(px(BLUR_MM, dpi) / 4))
        image = blurred.resize(size, Image.Resampling.BILINEAR)
        image = ImageEnhance.Brightness(image).enhance(BACK_BRIGHTNESS)
    pen = _Pen(image, dpi, fonts)
    left = CASE.bleed + CASE.text_margin
    width = CASE.panel_width - 2 * CASE.text_margin
    y = CASE.bleed + 12 + CAP * 16 * POINT
    for line in fit_lines(content.disc_name, width, 2, 16, pen.measure(True)):
        pen.text(left, y, line, 16, bold=True)
        y += 19 * POINT
    y -= 19 * POINT
    if content.secondary:
        y += 13 * POINT
        pen.text(left, y, content.secondary, 10, fill=SECONDARY)
    pen.rect(left, y + 3, 12, 0.7, accent)
    floor = _foot(content, pen, left, width, accent)
    _body(content, pen, left, width, y + 3 + 0.7 + 5, floor, accent)
    return image


def _foot(content: CoverContent, pen: _Pen, left: float, width: float, accent: str) -> float:
    """The attribution and the technical box at the bottom; returns where the body must end."""
    baseline = CASE.bleed + CASE.height - 10
    top = baseline
    if content.tmdb:
        lines = fit_lines(ATTRIBUTION, width, 3, 7, pen.measure())
        first = baseline - (len(lines) - 1) * 9 * POINT
        for n, line in enumerate(lines):
            pen.text(left, first + n * 9 * POINT, line, 7, fill=FAINT)
        top = first - CAP * 7 * POINT
    last = top - 4
    rows = len(content.tech)
    first_row = last - (rows - 1) * 11.5 * POINT
    for n, (label, value) in enumerate(content.tech):
        y = first_row + n * 11.5 * POINT
        pen.text(left, y, label, 7.5, bold=True, fill=accent)
        shown = fit_lines(value, width - 20, 1, 8.5, pen.measure())
        pen.text(left + 20, y, shown[0] if shown else "", 8.5)
    rule = first_row - CAP * 8.5 * POINT - 3
    pen.rect(left, rule, width, 0.35, RULE)
    return rule - 4


def _body(
    content: CoverContent, pen: _Pen, left: float, width: float, top: float, floor: float,
    accent: str,
) -> None:  # fmt: skip
    y = top
    if content.synopsis:
        cast = fit_lines(", ".join(content.cast), width, 2, 8.5, pen.measure())
        reserve = (3 + (1 + len(cast)) * 11.5 * POINT) if cast else 0.0
        limit = 5 if content.lines else 99
        room = int((floor - reserve - y) / (13.5 * POINT))
        for line in fit_lines(content.synopsis, width, max(1, min(limit, room)), 9.5,
                              pen.measure()):  # fmt: skip
            y += 13.5 * POINT
            pen.text(left, y, line, 9.5)
        if cast:
            y += 3 + 11.5 * POINT
            pen.text(left, y, "Elenco", 7.5, bold=True, fill=accent)
            for line in cast:
                y += 11.5 * POINT
                pen.text(left, y, line, 8.5)
        y += 4
    if any(line.synopsis for line in content.lines):
        _movies(content.lines, pen, left, width, y, floor)
    elif content.lines:
        _episodes(content.lines, pen, left, width, y, floor)


def _movies(
    lines: Sequence[CoverLine], pen: _Pen, left: float, width: float, y: float, floor: float
) -> None:
    for line in lines:
        synopsis = fit_lines(line.synopsis or "", width, 2, 8.5, pen.measure())
        height = (10 + len(synopsis) * 11.5) * POINT
        if y + height > floor:
            return
        y += 10 * POINT
        _row(pen, left, width, y, line, 10, True)
        for text in synopsis:
            y += 11.5 * POINT
            pen.text(left, y, text, 8.5, fill=SOFT)
        y += 4


def _episodes(
    lines: Sequence[CoverLine], pen: _Pen, left: float, width: float, y: float, floor: float
) -> None:
    lead = 12.5 * POINT
    rows = max(1, int((floor - y) / lead))
    columns = 2 if len(lines) >= EPISODE_COLUMNS_FROM else 1
    column = (width - 6 * (columns - 1)) / columns
    shown: list[CoverLine | str] = list(lines)
    if len(lines) > rows * columns:
        shown = [*lines[: rows * columns - 1], f"e mais {len(lines) - rows * columns + 1}"]
    per_column = max(rows if columns == 1 else -(-len(shown) // columns), 1)
    for n, item in enumerate(shown):
        x = left + (n // per_column) * (column + 6)
        baseline = y + (n % per_column + 1) * lead
        if isinstance(item, str):
            pen.text(x, baseline, item, 9, fill=SECONDARY)
        else:
            _row(pen, x, column, baseline, item, 9, False)


def _row(
    pen: _Pen, x: float, width: float, y: float, line: CoverLine, pt: float, bold: bool
) -> None:
    """A title on the left, cut to leave room for its detail on the right."""
    room = width
    if line.detail:
        pen.text(x + width, y, line.detail, 8.5, fill=SECONDARY, anchor="rs")
        room -= pen.width(line.detail, 8.5) + 2
    title = fit_lines(line.title, room, 1, pt, pen.measure(bold))
    pen.text(x, y, title[0] if title else "", pt, bold=bold)
