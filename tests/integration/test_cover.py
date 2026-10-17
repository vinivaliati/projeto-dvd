"""The cover with the real DejaVu fonts: run inside the Docker image (make test-slow)."""

from pathlib import Path

import pytest
from PIL import Image, ImageFont, PdfParser

from projeto_dvd.covers.layout import fit_spine
from projeto_dvd.covers.render import PDF_DPI, _Pen, render_cover, render_labels, write_pdf
from projeto_dvd.menus import render as menu
from tests.unit.test_cover_render import MOVIE, SEASON

pytestmark = pytest.mark.slow


def test_the_real_fonts_are_used() -> None:
    assert isinstance(menu.dejavu(20, True), ImageFont.FreeTypeFont)


@pytest.mark.parametrize("name", ["Friends", "O Senhor dos Anéis: A Sociedade do Anel " * 3])
def test_the_spine_breaks_the_same_in_the_preview_and_the_pdf(name: str) -> None:
    preview, pdf = (_Pen(Image.new("RGB", (1, 1)), dpi, menu.dejavu) for dpi in (50, PDF_DPI))

    assert fit_spine(name, 150.0, preview.measure(True)) == fit_spine(
        name, 150.0, pdf.measure(True)
    )


def test_the_pdf_with_the_real_fonts(tmp_path: Path) -> None:
    art = Image.new("RGB", (2000, 3000), (40, 60, 90))
    target = tmp_path / "capa.pdf"

    write_pdf(render_cover(SEASON, art, None, "#D9A441", True, PDF_DPI),
              render_labels(MOVIE, art, "#D9A441", PDF_DPI), target)  # fmt: skip

    pdf = PdfParser.PdfParser(str(target))
    boxes = [pdf.read_indirect(page)[b"MediaBox"] for page in pdf.pages]
    pdf.close()
    assert [(round(box[2]), round(box[3])) for box in boxes] == [(842, 595), (595, 842)]
