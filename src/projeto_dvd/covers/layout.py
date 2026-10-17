"""Where everything goes on the printed sheets, in millimeters. Pure: the render measures text."""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from projeto_dvd.covers.sizes import A4, CASE, LABELS, MARKS, CaseSize, LabelSheet, Marks, px

Measure = Callable[[str, float], float]  # (text, size in pt) -> width in mm
SPINE_SIZES = (18.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0)
ELLIPSIS = "…"
RULER_INSET = 10.0  # from the left cut
RULER_FROM_BOTTOM = 6.0
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class CoverLayout:
    page: tuple[float, float]  # the A4 turned
    cut: Rect
    bleed: Rect
    back: Rect  # each panel with the bleed on its outer edges
    spine: Rect
    front: Rect
    fold_x: tuple[float, float]
    crop_marks: tuple[tuple[float, float, float, float], ...]  # segments (x1, y1, x2, y2)
    fold_marks: tuple[tuple[float, float, float, float], ...]
    ruler: tuple[float, float]  # where the 50 mm ruler starts, and its y


def cover_layout(case: CaseSize = CASE, marks: Marks = MARKS) -> CoverLayout:
    page = (A4[1], A4[0])
    width = 2 * case.panel_width + case.spine
    cut = Rect((page[0] - width) / 2, (page[1] - case.height) / 2, width, case.height)
    b = case.bleed
    bleed = Rect(cut.x - b, cut.y - b, cut.w + 2 * b, cut.h + 2 * b)
    folds = (cut.x + case.panel_width, cut.x + case.panel_width + case.spine)
    right, bottom = cut.x + cut.w, cut.y + cut.h
    near, far = marks.offset, marks.offset + marks.length
    crop = []
    for x, side in ((cut.x, -1), (right, 1)):
        for y, up in ((cut.y, -1), (bottom, 1)):
            crop.append((x + side * far, y, x + side * near, y))
            crop.append((x, y + up * far, x, y + up * near))
    fold_far = marks.offset + marks.fold_length
    fold = tuple(
        segment
        for x in folds
        for segment in (
            (x, cut.y - fold_far, x, cut.y - near),
            (x, bottom + near, x, bottom + fold_far),
        )
    )
    return CoverLayout(
        page=page, cut=cut, bleed=bleed,
        back=Rect(bleed.x, bleed.y, folds[0] - bleed.x, bleed.h),
        spine=Rect(folds[0], bleed.y, case.spine, bleed.h),
        front=Rect(folds[1], bleed.y, bleed.x + bleed.w - folds[1], bleed.h),
        fold_x=folds, crop_marks=tuple(sorted(crop)), fold_marks=fold,
        ruler=(cut.x + RULER_INSET, page[1] - RULER_FROM_BOTTOM),
    )  # fmt: skip


def edges_px(xs: Sequence[float], dpi: int) -> list[int]:
    """Panel edges rounded once from their accumulated mm, so neighbors share a pixel edge."""
    return [px(x, dpi) for x in xs]


def fit_spine(text: str, length_mm: float, measure_mm: Measure) -> tuple[str, float]:
    """The name on the spine: from 18 pt down to 12 pt, then cut with an ellipsis."""
    for size in SPINE_SIZES:
        if measure_mm(text, size) <= length_mm:
            return text, size
    size = SPINE_SIZES[-1]
    cut = text
    while cut and measure_mm(cut.rstrip() + ELLIPSIS, size) > length_mm:
        cut = cut[:-1]
    return cut.rstrip() + ELLIPSIS, size


def fit_lines(
    text: str, width_mm: float, max_lines: int, size_pt: float, measure_mm: Measure
) -> list[str]:
    """Wrapped text, cut after the last sentence that fits, or at a word with an ellipsis."""
    lines = _wrap(text, width_mm, size_pt, measure_mm)
    if len(lines) <= max_lines:
        return lines
    sentences = _SENTENCE_END.split(text.strip())
    for count in range(len(sentences) - 1, 0, -1):
        shorter = _wrap(" ".join(sentences[:count]), width_mm, size_pt, measure_mm)
        if len(shorter) <= max_lines:
            return shorter
    kept, words = lines[: max_lines - 1], lines[max_lines - 1].split()
    while len(words) > 1 and measure_mm(" ".join(words) + ELLIPSIS, size_pt) > width_mm:
        words.pop()
    return [*kept, " ".join(words) + ELLIPSIS]


def label_centers(sheet: LabelSheet = LABELS) -> tuple[tuple[float, float], ...]:
    """The centers of the round labels on the A4 sheet (portrait), in mm."""
    return sheet.centers


def _wrap(text: str, width_mm: float, size_pt: float, measure_mm: Measure) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        candidate = f"{lines[-1]} {word}" if lines else word
        if lines and measure_mm(candidate, size_pt) <= width_mm:
            lines[-1] = candidate
        else:
            lines.append(word)
    return lines
