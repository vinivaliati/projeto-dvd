from collections.abc import Callable

import pytest

from projeto_dvd.covers.layout import (
    Rect,
    cover_layout,
    edges_px,
    fit_lines,
    fit_spine,
    label_centers,
)
from projeto_dvd.covers.sizes import LabelSheet

Measure = Callable[[str, float], float]


def measure_at(dpi: int) -> Measure:
    """A fake font: each character is 0.2 mm per point wide, rounded to whole pixels."""
    return lambda text, size: round(len(text) * size * 0.2 / 25.4 * dpi) * 25.4 / dpi


def test_the_cover_is_centered_on_the_turned_a4() -> None:
    layout = cover_layout()

    assert layout.page == (297.0, 210.0)
    assert layout.cut == Rect(12.0, 13.5, 273.0, 183.0)
    assert layout.bleed == Rect(9.0, 10.5, 279.0, 189.0)


def test_back_spine_and_front_from_the_outside_with_the_bleed_on_the_outer_edges() -> None:
    layout = cover_layout()

    assert layout.back == Rect(9.0, 10.5, 132.5, 189.0)
    assert layout.spine == Rect(141.5, 10.5, 14.0, 189.0)
    assert layout.front == Rect(155.5, 10.5, 132.5, 189.0)
    assert layout.fold_x == (141.5, 155.5)


def test_crop_marks_stay_outside_the_bleed_and_away_from_the_paper_edge() -> None:
    layout = cover_layout()
    width, height = layout.page
    bleed = layout.bleed

    assert len(layout.crop_marks) == 8
    for x1, y1, x2, y2 in layout.crop_marks:
        for x, y in ((x1, y1), (x2, y2)):
            assert 4.0 <= x <= width - 4.0 and 4.0 <= y <= height - 4.0
            outside_x = x <= bleed.x or x >= bleed.x + bleed.w
            outside_y = y <= bleed.y or y >= bleed.y + bleed.h
            assert outside_x or outside_y
        assert x1 == x2 or y1 == y2
    corners = {(x1, y1) for x1, y1, x2, y2 in layout.crop_marks if x1 == x2}
    assert (12.0, 5.5) in corners  # vertical mark of the top left corner, on the cut line


def test_fold_marks_sit_on_the_spine_lines_above_and_below() -> None:
    layout = cover_layout()

    assert layout.fold_marks == (
        (141.5, 6.5, 141.5, 9.5), (141.5, 200.5, 141.5, 203.5),
        (155.5, 6.5, 155.5, 9.5), (155.5, 200.5, 155.5, 203.5),
    )  # fmt: skip
    assert layout.ruler == (22.0, 204.0)


@pytest.mark.parametrize("dpi", [50, 300])
def test_panel_edges_leave_no_gap(dpi: int) -> None:
    layout = cover_layout()
    xs = [layout.back.x, layout.spine.x, layout.front.x, layout.front.x + layout.front.w]

    edges = edges_px(xs, dpi)

    assert edges == sorted(edges) and len(set(edges)) == 4
    assert (edges[0], edges[-1]) == (round(9.0 * dpi / 25.4), round(288.0 * dpi / 25.4))


@pytest.mark.parametrize("dpi", [50, 300])
def test_fit_spine_shrinks_then_cuts_the_same_at_any_scale(dpi: int) -> None:
    measure = measure_at(dpi)

    assert fit_spine("Matrix", 100.0, measure) == ("Matrix", 18.0)
    assert fit_spine("x" * 30, 100.0, measure) == ("x" * 30, 16.0)  # 18 and 17 are too wide
    text, size = fit_spine("x" * 60, 100.0, measure)
    assert size == 12.0 and text.endswith("…")
    assert measure(text, size) <= 100.0 and measure(text + "x", size) > 100.0 - 0.5


def measure_chars(text: str, size: float) -> float:
    return float(len(text))


def test_fit_lines_wraps_by_words() -> None:
    assert fit_lines("um dois tres quatro", 9.0, 3, 9.0, measure_chars) == [
        "um dois",
        "tres",
        "quatro",
    ]


def test_fit_lines_cuts_at_the_last_sentence_that_fits() -> None:
    text = "Um dois. Tres quatro. Cinco seis sete oito nove."

    assert fit_lines(text, 12.0, 2, 9.0, measure_chars) == ["Um dois.", "Tres quatro."]
    assert fit_lines(text, 12.0, 1, 9.0, measure_chars) == ["Um dois."]


def test_fit_lines_cuts_at_a_word_when_no_sentence_fits() -> None:
    text = "Uma frase longa demais para caber em duas linhas curtas."

    lines = fit_lines(text, 12.0, 2, 9.0, measure_chars)

    assert lines == ["Uma frase", "longa…"]
    assert all(len(line) <= 12 for line in lines)
    assert fit_lines("", 12.0, 2, 9.0, measure_chars) == []


def test_label_centers_are_the_two_labels_of_the_sheet() -> None:
    assert label_centers() == ((105.0, 78.5), (105.0, 218.5))
    assert label_centers(LabelSheet(centers=((1.0, 2.0),))) == ((1.0, 2.0),)
