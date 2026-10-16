from itertools import combinations

import pytest

from projeto_dvd.menus.layout import (
    Box,
    PageLayout,
    fit_label,
    layout_page,
    letterbox_y,
    square_width,
    to_720,
)
from projeto_dvd.menus.pages import build_pages
from projeto_dvd.planner.disc_plan import MenuPage

AUDIO = ("Português", "Inglês")
SUBS = ("Português", "Inglês", "Espanhol", "Francês")


def measure(text: str, size: int) -> float:
    return len(text) * size * 0.6


def example_pages() -> list[MenuPage]:
    pages: list[MenuPage] = []
    for kind, count in (("movies", 1), ("movies", 4), ("movies", 6), ("movies", 7),
                        ("series", 13)):  # fmt: skip
        names = [f"{n}. Um nome de episódio razoável" for n in range(1, count + 1)]
        pages += build_pages(kind, names, "Um disco", "Temporada 1", AUDIO, SUBS)  # type: ignore[arg-type]
    return pages


LAYOUTS = [
    (page, aspect, side)
    for page in example_pages()
    for aspect in ("16:9", "4:3")
    for side in ("left", "right")
]


def boxes(layout: PageLayout) -> list[Box]:
    return [b.box for b in layout.buttons]


@pytest.mark.parametrize(("page", "aspect", "side"), LAYOUTS)
def test_buttons_stay_inside_the_safe_area(page: MenuPage, aspect: str, side: str) -> None:
    layout = layout_page(page, aspect, side, measure)
    for box in boxes(layout) + [b.marker for b in layout.buttons]:
        assert 72 <= box.x0 < box.x1 <= 648
        assert 48 <= box.y0 < box.y1 <= 432


@pytest.mark.parametrize(("page", "aspect", "side"), LAYOUTS)
def test_coordinates_are_even(page: MenuPage, aspect: str, side: str) -> None:
    layout = layout_page(page, aspect, side, measure)
    for box in boxes(layout) + [b.marker for b in layout.buttons]:
        assert all(value % 2 == 0 for value in (box.x0, box.y0, box.x1, box.y1))
        assert box.y1 - box.y0 >= 2 and box.x1 - box.x0 >= 2


@pytest.mark.parametrize(("page", "aspect", "side"), LAYOUTS)
def test_boxes_keep_four_pixels_apart(page: MenuPage, aspect: str, side: str) -> None:
    for a, b in combinations(boxes(layout_page(page, aspect, side, measure)), 2):
        apart_x = a.x1 + 4 <= b.x0 or b.x1 + 4 <= a.x0
        apart_y = a.y1 + 4 <= b.y0 or b.y1 + 4 <= a.y0
        assert apart_x or apart_y


@pytest.mark.parametrize(("page", "aspect", "side"), LAYOUTS)
def test_arrows_point_to_existing_buttons(page: MenuPage, aspect: str, side: str) -> None:
    layout = layout_page(page, aspect, side, measure)
    numbers = [b.number for b in layout.buttons]
    assert numbers == list(range(1, len(numbers) + 1))
    for button in layout.buttons:
        assert {button.up, button.down, button.left, button.right} <= set(numbers)


def test_list_arrows_do_not_wrap_and_reach_the_footer() -> None:
    # The second episode page: 1 item, footer Anterior and Voltar.
    page = build_pages("series", [f"E{n}" for n in range(1, 8)], "S", None, AUDIO, ())[2]
    layout = layout_page(page, "16:9", "left", measure)
    item, previous, back = layout.buttons
    assert (item.up, item.down) == (1, back.number)
    assert (back.up, back.left, back.right, back.down) == (1, previous.number, 3, 3)
    assert (previous.left, previous.right) == (2, back.number)


def test_list_is_anchored_at_the_bottom() -> None:
    main = build_pages("series", ["a", "b"], "S", None, AUDIO, ())[0]
    layout = layout_page(main, "16:9", "left", measure)
    assert layout.buttons[-1].box.y1 == 432
    assert layout.buttons[0].font_size == 34


def test_the_footer_sits_below_the_list() -> None:
    page = build_pages("series", [f"E{n}" for n in range(1, 8)], "S", None, AUDIO, ())[1]
    layout = layout_page(page, "4:3", "left", measure)
    items = [b for b in layout.buttons if b.anchor == "lm"]
    footer = [b for b in layout.buttons if b.anchor == "mm"]
    assert items[-1].box.y1 == 396
    assert [(b.box.y0, b.box.y1) for b in footer] == [(400, 432), (400, 432)]


def test_right_side_moves_the_column() -> None:
    main = build_pages("series", ["a", "b"], "S", None, AUDIO, ())[0]
    left = layout_page(main, "16:9", "left", measure).buttons[0]
    right = layout_page(main, "16:9", "right", measure).buttons[0]
    assert right.box.x0 > left.box.x0 and right.text_x > left.text_x


def test_square_widths_and_conversion() -> None:
    assert (square_width("16:9"), square_width("4:3")) == (854, 640)
    assert to_720(854, 854) == 720 and to_720(85, 854) == 72 and to_720(64, 640) == 72


def test_letterbox_moves_and_shrinks_vertically() -> None:
    assert letterbox_y(114) == 146
    assert letterbox_y(432) == 384
    assert letterbox_y(48) == 96


def test_fit_label_shrinks_then_cuts() -> None:
    assert fit_label("Curto", 200, 28, measure) == ("Curto", 28)
    assert fit_label("x" * 13, 200, 28, measure) == ("x" * 13, 24)
    text, size = fit_label("x" * 40, 200, 28, measure)
    assert size == 24 and text.endswith("…") and measure(text, 24) <= 200


def test_a_short_heading_is_one_large_line() -> None:
    main = build_pages("series", ["a", "b"], "Friends", None, AUDIO, ())[0]
    layout = layout_page(main, "16:9", "left", measure)
    assert (layout.heading_lines, layout.heading_size) == (("Friends",), 34)


def test_a_long_heading_wraps_into_two_lines_with_ellipsis() -> None:
    name = "Um nome de disco muito longo que não cabe de jeito nenhum em duas linhas da coluna"
    main = build_pages("series", ["a", "b"], name, None, AUDIO, ())[0]
    layout = layout_page(main, "4:3", "left", measure)
    assert layout.heading_size == 28 and len(layout.heading_lines) == 2
    assert layout.heading_lines[1].endswith("…")
    assert all(measure(line, 28) <= 448 - 32 for line in layout.heading_lines)


def heading_of(name: str) -> PageLayout:
    main = build_pages("series", ["a", "b"], name, None, AUDIO, ())[0]
    return layout_page(main, "4:3", "left", measure)


def test_a_heading_that_fits_only_in_the_smaller_size_stays_one_line() -> None:
    layout = heading_of("x" * 22)  # 22 * 34 * 0.6 = 449 > 400; 22 * 28 * 0.6 = 370
    assert (layout.heading_lines, layout.heading_size) == (("x" * 22,), 28)


def test_a_single_huge_word_is_cut() -> None:
    layout = heading_of("x" * 60)
    assert len(layout.heading_lines) == 1 and layout.heading_lines[0].endswith("…")


def test_two_lines_without_cut_when_they_fit() -> None:
    layout = heading_of("palavra " * 6)
    assert len(layout.heading_lines) == 2 and not layout.heading_lines[1].endswith("…")
