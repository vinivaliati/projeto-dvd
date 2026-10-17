import math
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageFont, PdfParser

from projeto_dvd.covers.content import CoverContent, CoverLine
from projeto_dvd.covers.layout import cover_layout
from projeto_dvd.covers.render import _Pen, load_art, render_cover, render_labels, write_pdf
from projeto_dvd.covers.sizes import LABELS, px

DPI = 50
ACCENT = "#D9A441"
GRAY = (128, 128, 128)
WHITE = (255, 255, 255)
TECH = (("Duração", "2h16"), ("Áudio", "Português"), ("Legendas", "Nenhuma"),
        ("Vídeo", "DVD-Video · NTSC · 16:9"), ("Disco", "DVD-9"))  # fmt: skip
MOVIE = CoverContent(
    disc_name="O Senhor dos Anéis: A Sociedade do Anel", secondary=None, front_text="2001",
    spine_text="O Senhor dos Anéis", spine_extra="2001",
    synopsis="Um hobbit recebe um anel. " * 30, cast=("A", "B", "C"), lines=(), tech=TECH,
    tmdb=True, profile="DVD-9",
)  # fmt: skip
SEASON = replace(
    MOVIE, disc_name="Friends", secondary="Temporada 1", front_text="Temporada 1 · 30 episódios",
    spine_extra="T1", synopsis="Seis amigos.", cast=(),
    lines=tuple(CoverLine(f"{n}. Nome", "22 min", None) for n in range(1, 31)),
)  # fmt: skip
MOVIES = replace(
    MOVIE, disc_name="Trilogia", front_text="3 filmes", spine_extra=None, synopsis=None, cast=(),
    lines=tuple(CoverLine(f"Filme {n}", "2001 · 2h58", "Uma frase. " * 20) for n in range(3)),
)  # fmt: skip


def gray(size: tuple[int, int] = (200, 300)) -> Image.Image:
    return Image.new("RGB", size, GRAY)


@pytest.mark.parametrize("content", [MOVIE, SEASON, MOVIES])
def test_the_cover_page_is_the_turned_a4_with_no_white_column_inside_the_cut(
    content: CoverContent,
) -> None:
    page = render_cover(content, gray(), gray((300, 169)), ACCENT, True, DPI)

    assert page.size == (px(297, DPI), px(210, DPI))
    cut = cover_layout().cut
    top, bottom = px(cut.y, DPI), px(cut.y + cut.h, DPI)
    for x in range(px(cut.x, DPI), px(cut.x + cut.w, DPI)):
        column = page.crop((x, top, x + 1, bottom))
        assert column.getextrema() != ((255, 255),) * 3, f"white column at {x}"


def front_top(page: Image.Image) -> Image.Image:
    """The name zone of the front panel: 5 to 30 mm below the cut, away from the edges."""
    front, cut = cover_layout().front, cover_layout().cut
    left, right = px(front.x + 10, DPI), px(front.x + front.w - 10, DPI)
    return page.crop((left, px(cut.y + 5, DPI), right, px(cut.y + 30, DPI)))


def test_the_name_goes_over_the_art_only_when_asked() -> None:
    without = render_cover(MOVIE, gray(), None, ACCENT, False, DPI)
    named = render_cover(MOVIE, gray(), None, ACCENT, True, DPI)

    assert front_top(without).getcolors() == [(front_top(without).width
                                               * front_top(without).height, GRAY)]  # fmt: skip
    assert len(front_top(named).getcolors(10_000) or []) > 2


def test_without_art_the_front_is_the_dark_neutral_background() -> None:
    page = render_cover(replace(MOVIE, front_text=""), None, None, ACCENT, True, DPI)
    front = cover_layout().front
    zone = page.crop((px(front.x + 5, DPI), px(80, DPI), px(front.x + 60, DPI), px(120, DPI)))

    assert all(value < 90 for value in zone.convert("L").tobytes())


def test_the_labels_leave_the_hole_without_ink() -> None:
    page = render_labels(MOVIE, gray(), ACCENT, DPI)

    assert page.size == (px(210, DPI), px(297, DPI))
    clear = (LABELS.hole / 2 - LABELS.hole_bleed) * DPI / 25.4 - 1
    for cx, cy in LABELS.centers:
        center = (cx * DPI / 25.4, cy * DPI / 25.4)
        for x in range(int(center[0] - clear), int(center[0] + clear) + 1):
            for y in range(int(center[1] - clear), int(center[1] + clear) + 1):
                if math.dist((x, y), center) < clear:
                    assert page.getpixel((x, y)) == WHITE
        ring = page.getpixel((round(center[0] + 40 * DPI / 25.4), round(center[1])))
        assert ring != WHITE


def test_labels_without_art_use_the_neutral_background() -> None:
    page = render_labels(replace(MOVIE, secondary="Disco 1"), None, ACCENT, DPI)
    cx, cy = LABELS.centers[0]

    assert page.getpixel((px(cx + 40, DPI), px(cy, DPI))) != WHITE


def test_load_art(tmp_path: Path) -> None:
    good, bad = tmp_path / "a.jpg", tmp_path / "b.jpg"
    Image.new("L", (4, 4), 9).save(good)
    bad.write_bytes(b"nope")

    loaded = load_art(good)
    assert loaded is not None and loaded.mode == "RGB"
    assert load_art(bad) is None
    assert load_art(tmp_path / "missing.jpg") is None
    assert load_art(None) is None


def test_the_pdf_has_the_cover_and_the_labels_in_real_size(tmp_path: Path) -> None:
    target = tmp_path / "capa.pdf"
    cover = render_cover(MOVIE, gray(), gray((300, 169)), ACCENT, True, 300)
    labels = render_labels(MOVIE, gray(), ACCENT, 300)

    write_pdf(cover, labels, target)

    assert not (tmp_path / "capa.pdf.part").exists()
    pdf = PdfParser.PdfParser(str(target))
    boxes = [pdf.read_indirect(page)[b"MediaBox"] for page in pdf.pages]
    pdf.close()
    expected = [(297, 210), (210, 297)]
    assert len(boxes) == 2
    for box, (width, height) in zip(boxes, expected, strict=True):
        assert box[2] == pytest.approx(width / 25.4 * 72, abs=0.5)
        assert box[3] == pytest.approx(height / 25.4 * 72, abs=0.5)


def test_an_empty_spine_is_just_the_dark_band() -> None:
    page = render_cover(replace(MOVIE, spine_text="", spine_extra=None), gray(), None, ACCENT,
                        True, DPI)  # fmt: skip
    spine, cut = cover_layout().spine, cover_layout().cut
    band = page.crop((px(spine.x, DPI) + 1, px(cut.y, DPI), px(spine.x + spine.w, DPI) - 1,
                      px(cut.y + cut.h, DPI)))  # fmt: skip

    assert band.getextrema() == ((0x12, 0x12), (0x12, 0x12), (0x16, 0x16))


@pytest.mark.parametrize(
    "content",
    [
        replace(MOVIE, disc_name="Palavra " * 40, tmdb=False),
        replace(SEASON, lines=tuple(CoverLine(f"{n}. Nome", None, None) for n in range(90))),
        replace(MOVIES, lines=MOVIES.lines * 8),
    ],
    ids=["huge name without TMDB", "too many episodes", "too many movies"],
)
def test_content_that_does_not_fit_is_cut_inside_the_cut(content: CoverContent) -> None:
    page = render_cover(content, gray(), None, ACCENT, True, DPI)
    cut = cover_layout().cut
    below = page.crop((0, px(cut.y + cut.h + 3, DPI), page.width, px(cut.y + cut.h + 3.5, DPI)))

    assert page.size == (px(297, DPI), px(210, DPI))
    assert below.getextrema() == ((255, 255),) * 3  # nothing spills under the bleed


def test_above_the_bleed_there_are_only_the_marks() -> None:
    page = render_cover(MOVIE, gray(), None, ACCENT, True, DPI)
    layout = cover_layout()
    folds = {px(x, DPI) + d for x in layout.fold_x for d in (-1, 0, 1)}
    top = px(layout.bleed.y, DPI) - 1

    for x in range(px(layout.cut.x, DPI) + 2, px(layout.cut.x + layout.cut.w, DPI) - 2):
        if x not in folds:
            assert page.crop((x, 0, x + 1, top)).getextrema() == ((255, 255),) * 3, x


def test_text_is_measured_the_same_at_any_dpi() -> None:
    def pen(dpi: int) -> _Pen:
        return _Pen(Image.new("RGB", (1, 1)), dpi, lambda size, bold: ImageFont.load_default(size))

    text = "O Senhor dos Anéis: A Sociedade do Anel"

    assert pen(50).measure(True)(text, 12) == pen(300).measure(True)(text, 12)
