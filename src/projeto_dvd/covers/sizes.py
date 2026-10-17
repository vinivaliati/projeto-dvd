"""The printed measures, in millimeters (the layout is in mm; the render picks the DPI)."""

from dataclasses import dataclass

A4 = (210.0, 297.0)  # portrait; the cover uses the page turned
DPI = 300
MM_PER_INCH = 25.4


@dataclass(frozen=True)
class CaseSize:
    """The insert of a DVD Amaray case, outside first: back | spine | front."""

    panel_width: float = 129.5  # front and back
    spine: float = 14.0
    height: float = 183.0
    bleed: float = 3.0
    safe: float = 5.0  # cut by hand (±1 mm) and the edge of the plastic sleeve
    text_margin: float = 8.0  # side margin of the text on the front and the back
    spine_safe: float = 2.0  # across the spine (the fold slips ±1 mm)
    spine_end: float = 10.0  # at both ends of the spine


@dataclass(frozen=True)
class Marks:
    offset: float = 4.0  # from the cut to the mark (bleed 3 + 1)
    length: float = 4.0  # with 5 the mark comes within 3 mm of the A4 edge and is lost
    fold_length: float = 3.0  # fold marks on both lines of the spine
    width: float = 0.2  # 3 px at 300 DPI


@dataclass(frozen=True)
class LabelSheet:
    """Round A4 labels, 2 per sheet (the common Pimaco layout, to be checked)."""

    diameter: float = 117.0
    hole: float = 41.0
    bleed: float = 2.0  # the art runs 2 mm outside the circle
    hole_bleed: float = 2.0  # no ink only inside r = 41/2 - 2 = 18.5 mm
    safe_outer: float = 4.0  # text inside r = 54.5 mm
    safe_hole: float = 3.0  # text outside r = 23.5 mm
    centers: tuple[tuple[float, float], ...] = ((105.0, 78.5), (105.0, 218.5))


def px(mm: float, dpi: int) -> int:
    return round(mm * dpi / MM_PER_INCH)


CASE = CaseSize()
MARKS = Marks()
LABELS = LabelSheet()
