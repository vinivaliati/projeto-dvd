import io
from pathlib import Path

import pytest
from PIL import Image, ImageFont, ImageStat

from projeto_dvd.authoring.dvd.subtitles import FONT, FONT_BOLD
from projeto_dvd.menus.layout import layout_page, to_720
from projeto_dvd.menus.pages import build_pages, subtitle_variant
from projeto_dvd.menus.render import (
    Font,
    background,
    dejavu,
    highlight,
    preview,
    render_page,
)
from projeto_dvd.planner.disc_plan import MenuPage, MenuPlan

ACCENT = "#4C9BE0"


def fonts(size: int, bold: bool) -> Font:
    return ImageFont.load_default(size=size)


def measure(text: str, size: int) -> float:
    return fonts(size, True).getlength(text)


def plan(backdrop: str | None = None, aspect: str = "16:9", side: str = "left") -> MenuPlan:
    pages = build_pages("series", [f"{n}. Episódio" for n in range(1, 8)], "Friends",
                        "Temporada 1", ("Português", "Inglês"), ("Português",))  # fmt: skip
    return MenuPlan(aspect=aspect, backdrop=backdrop, accent=ACCENT, side=side,  # type: ignore[arg-type]
                    pages=pages)  # fmt: skip


def rgba_values(image: Image.Image) -> set[tuple[int, int, int, int]]:
    colors = image.convert("RGBA").getcolors(720 * 480) or []
    return {color for _, color in colors}  # type: ignore[misc]


def test_highlight_has_at_most_four_colors_without_antialias() -> None:
    menu = plan()
    layout = layout_page(menu.pages[1], "16:9", "left", measure)

    for select, partial in ((False, 85), (True, 153)):
        values = rgba_values(highlight(layout, ACCENT, select=select))
        assert len(values) <= 4
        assert {alpha for *_, alpha in values} <= {0, partial, 255}


def test_highlight_draws_only_inside_the_buttons() -> None:
    layout = layout_page(plan().pages[1], "16:9", "left", measure)
    image = highlight(layout, ACCENT, select=False).convert("RGBA")
    inside = Image.new("L", image.size, 0)
    for button in layout.buttons:
        box = button.box
        inside.paste(255, (box.x0 - 2, box.y0, box.x1 + 2, box.y1))
    alpha = image.getchannel("A")
    outside = Image.composite(Image.new("L", image.size, 0), alpha, inside)
    assert outside.getbbox() is None


def test_select_uses_the_light_marker() -> None:
    layout = layout_page(plan().pages[1], "16:9", "left", measure)
    values = rgba_values(highlight(layout, ACCENT, select=True))
    assert (0xEB, 0xEB, 0xEB, 255) in values


def write_image(path: Path, color: tuple[int, int, int]) -> str:
    Image.new("RGB", (1280, 720), color).save(path)
    return str(path)


def test_text_stays_readable_on_a_white_backdrop(tmp_path: Path) -> None:
    white = Image.new("RGB", (1280, 720), (255, 255, 255))
    for page in plan().pages[:2]:
        bare = MenuPage(kind=page.kind, heading="", items=())
        empty = layout_page(bare, "16:9", "left", measure)
        image = background(bare, empty, white, ACCENT, "left", fonts)
        assert image.size == (720, 480) and image.mode == "RGB"
        column = (to_720(85, 854), 48, to_720(565, 854), 432)
        assert p95_luma(image, column) <= 64  # 7:1 for the light text, on any art


def p95_luma(image: Image.Image, box: tuple[int, int, int, int]) -> int:
    histogram = image.crop(box).convert("L").histogram()
    limit, seen = sum(histogram) * 0.95, 0
    for luma, count in enumerate(histogram):
        seen += count
        if seen >= limit:
            return luma
    raise AssertionError("empty box")


def test_dejavu_loads_the_bold_or_regular_file(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(ImageFont, "truetype", lambda path, size: calls.append((path, size)))
    dejavu(28, True)
    dejavu(22, False)
    assert calls == [(str(FONT_BOLD), 28), (str(FONT), 22)]


def test_the_gradient_darkens_the_side_of_the_buttons(tmp_path: Path) -> None:
    menu = plan(write_image(tmp_path / "white.jpg", (250, 250, 250)), side="right")
    rendered = render_page(menu, 0, fonts)
    gray = rendered.background.convert("L")
    far, under = gray.getpixel((20, 240)), gray.getpixel((700, 300))
    assert isinstance(far, int) and isinstance(under, int)
    assert far > 150  # far from the buttons: the art shows
    assert under < 40  # under the buttons: 15% of the dimmed art


def test_neutral_background_without_art() -> None:
    rendered = render_page(plan(), 0, fonts)
    assert rendered.background.size == (720, 480)
    gray = rendered.background.convert("L")
    assert ImageStat.Stat(gray).mean[0] < 80  # dark, so the light text reads


def test_a_missing_backdrop_file_falls_back_to_neutral(tmp_path: Path) -> None:
    rendered = render_page(plan(str(tmp_path / "gone.jpg")), 0, fonts)
    assert rendered.background.size == (720, 480)


def test_the_check_mark_changes_the_checked_line() -> None:
    menu = plan()
    on = render_page(menu, subtitle_variant(menu.pages, 0), fonts).background
    off = render_page(menu, subtitle_variant(menu.pages, 1), fonts).background
    assert on.tobytes() != off.tobytes()


def test_4_3_pages_render_too() -> None:
    rendered = render_page(plan(aspect="4:3"), 1, fonts)
    assert rendered.layout.width == 640 and rendered.background.size == (720, 480)


def test_preview_is_a_720x480_png_with_the_focus_highlighted() -> None:
    data = preview(plan(), 0, fonts)
    image = Image.open(io.BytesIO(data))
    plain = render_page(plan(), 0, fonts).background
    assert (image.format, image.size) == ("PNG", (720, 480))
    assert image.convert("RGB").tobytes() != plain.tobytes()


def test_a_movie_menu_with_art_has_no_secondary_line(tmp_path: Path) -> None:
    pages = build_pages("movies", ["Up"], "Up", None, ("Português",), ())
    menu = MenuPlan(aspect="16:9", backdrop=write_image(tmp_path / "a.jpg", (90, 60, 30)),
                    accent=ACCENT, side="left", pages=pages)  # fmt: skip
    assert render_page(menu, 0, fonts).background.size == (720, 480)
