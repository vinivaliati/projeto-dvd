"""Draw the menu pages with Pillow: the background (art, text) and the button subpictures.

The background is drawn in square pixels and squeezed to 720x480 at the end. The subpictures
are drawn straight in 720x480 with at most 4 palette colors and no antialias: spumux turns
each palette entry into one DVD color and contrast, and a resize would invent colors.
"""

import io
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from projeto_dvd.authoring.dvd.subtitles import FONT, FONT_BOLD
from projeto_dvd.menus.layout import PageLayout, layout_page
from projeto_dvd.menus.theme import OUTLINE, SECONDARY, TEXT
from projeto_dvd.planner.disc_plan import MenuPage, MenuPlan

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont
Fonts = Callable[[int, bool], Font]  # (size, bold)
HEIGHT = 480
FRAME = (720, 480)
DIM = 0.85  # brightness and saturation of the art
# The whole column sits under the solid part, so the text area is at most 255 x 0.85 x 0.15
# = 33 of luma: the light text always has a contrast above 7:1, whatever the art.
GRADIENT_ALPHA = 0.85
GRADIENT_PAST_COLUMN = 40
GRADIENT_FADE = 0.35  # of the width
BLUR_RADIUS = 4
NEUTRAL_FAR, NEUTRAL_NEAR = (0x26, 0x2B, 0x3A), (0x12, 0x12, 0x16)
GLOW = 0.12
NOISE = 2
STROKE = 2
SECONDARY_SIZE = 22
CHECK = "✓"
BAND_ALPHA = {False: 85, True: 153}  # about 5/15 and 9/15 of DVD contrast
FLICKER = ImageFilter.Kernel((3, 3), [0, 1, 0, 0, 2, 0, 0, 1, 0], 4)


@dataclass(frozen=True)
class RenderedPage:
    background: Image.Image
    highlight: Image.Image
    select: Image.Image
    layout: PageLayout


def dejavu(size: int, bold: bool) -> Font:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def background(
    page: MenuPage,
    layout: PageLayout,
    backdrop: Image.Image | None,
    accent: str,
    side: str,
    fonts: Fonts,
) -> Image.Image:
    size = (layout.width, HEIGHT)
    canvas = neutral(size, accent, side) if backdrop is None else _art(backdrop, layout, side)
    draw = ImageDraw.Draw(canvas)
    _draw_heading(draw, page, layout, accent, fonts, neutral=backdrop is None)
    for button in layout.buttons:
        font = fonts(button.font_size, True)
        draw.text((button.text_x, button.text_y), button.label, font=font, fill=TEXT,
                  anchor=button.anchor, stroke_width=STROKE, stroke_fill=OUTLINE)  # fmt: skip
        if page.checked is not None and button.number == page.checked + 1:
            end = button.text_x + draw.textlength(button.label, font=font) + 12
            draw.text((end, button.text_y), CHECK, font=font, fill=accent, anchor="lm",
                      stroke_width=STROKE, stroke_fill=OUTLINE)  # fmt: skip
    return canvas.filter(FLICKER).resize(FRAME, Image.Resampling.LANCZOS)


def highlight(layout: PageLayout, accent: str, select: bool) -> Image.Image:
    """Palette image: 0 transparent, 1 the marker, 2 the band behind the text, 3 the outline."""
    marker = TEXT if select else accent
    image = Image.new("P", FRAME, 0)
    image.putpalette([0, 0, 0, *_rgb(marker), *_rgb(accent), *_rgb(OUTLINE)])
    image.info["transparency"] = bytes((0, 255, BAND_ALPHA[select], 255))
    draw = ImageDraw.Draw(image)
    for button in layout.buttons:
        box, mark = button.box, button.marker
        draw.rectangle((box.x0, box.y0, box.x1 - 1, box.y1 - 1), fill=2)
        if button.anchor == "lm":
            draw.rectangle((mark.x0 - 2, mark.y0, mark.x1 + 1, mark.y1 - 1), fill=3)
        draw.rectangle((mark.x0, mark.y0, mark.x1 - 1, mark.y1 - 1), fill=1)
    return image


def render_page(plan: MenuPlan, index: int, fonts: Fonts | None = None) -> RenderedPage:
    fonts = fonts or dejavu  # looked up at call time, so tests can swap the font
    page = plan.pages[index]
    layout = layout_page(page, plan.aspect, plan.side,
                         lambda text, size: fonts(size, True).getlength(text))  # fmt: skip
    art = _load(plan.backdrop)
    return RenderedPage(
        background=background(page, layout, art, plan.accent, plan.side, fonts),
        highlight=highlight(layout, plan.accent, select=False),
        select=highlight(layout, plan.accent, select=True),
        layout=layout,
    )


def preview(plan: MenuPlan, index: int, fonts: Fonts | None = None) -> bytes:
    """The page as the TV shows it when it opens: the background with its focus highlighted."""
    rendered = render_page(plan, index, fonts)
    focus = rendered.layout.buttons[plan.pages[index].focus - 1].box
    mask = Image.new("L", FRAME, 0)
    mask.paste(255, (focus.x0 - 2, focus.y0, focus.x1 + 2, focus.y1))
    lit = rendered.highlight.convert("RGBA")
    lit.putalpha(Image.composite(lit.getchannel("A"), mask, mask))
    image = Image.alpha_composite(rendered.background.convert("RGBA"), lit)
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def _art(backdrop: Image.Image, layout: PageLayout, side: str) -> Image.Image:
    width = layout.width
    art = cover_crop(backdrop.convert("RGB"), (width, HEIGHT))
    art = ImageEnhance.Color(ImageEnhance.Brightness(art).enhance(DIM)).enhance(DIM)
    blurred = art.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    left, right = layout.column
    mask = _gradient(width, left, right, side, GRADIENT_ALPHA)
    soft = Image.composite(blurred, art, mask.point(lambda v: 255 if v else 0))
    return Image.composite(Image.new("RGB", art.size, (0, 0, 0)), soft, mask)


def _gradient(width: int, left: int, right: int, side: str, alpha: float) -> Image.Image:
    """Opacity of the black over the art: solid up to past the column, then fading out."""
    solid = (right if side == "left" else width - left) + GRADIENT_PAST_COLUMN
    fade = GRADIENT_FADE * width
    row = []
    for x in range(width):
        distance = x if side == "left" else width - 1 - x
        faded = max(0.0, alpha * (1 - (distance - solid) / fade))
        row.append(round((alpha if distance <= solid else faded) * 255))
    line = Image.new("L", (width, 1))
    line.putdata(row)
    return line.resize((width, HEIGHT), Image.Resampling.NEAREST)


def neutral(size: tuple[int, int], accent: str, side: str) -> Image.Image:
    """Diagonal gradient, a faint glow of the accent in the far corner, and a little noise."""
    width, height = size
    corners = Image.new("RGB", (2, 2))
    far, near = (1, 0) if side == "left" else (0, 1)  # the column of the far corner
    corners.putpixel((far, 0), NEUTRAL_FAR)
    corners.putpixel((near, 1), NEUTRAL_NEAR)
    middle = tuple((f + n) // 2 for f, n in zip(NEUTRAL_FAR, NEUTRAL_NEAR, strict=True))
    corners.putpixel((near, 0), middle)
    corners.putpixel((far, 1), middle)
    image = corners.resize(size, Image.Resampling.BILINEAR, box=(0.5, 0.5, 1.5, 1.5))
    reach = Image.radial_gradient("L").resize((width * 2, height * 2))
    reach = reach.crop((width - far * width, height, 2 * width - far * width, 2 * height))
    glow = reach.point(lambda v: round((255 - v) * GLOW))
    image = Image.composite(Image.new("RGB", size, _rgb(accent)), image, glow)
    rng = random.Random(0)
    noise = Image.frombytes("L", size, rng.randbytes(width * height))
    noise = Image.merge("RGB", [noise.point(lambda v: v % (2 * NOISE + 1))] * 3)
    return ImageChops.subtract(ImageChops.add(image, noise), Image.new("RGB", size, (NOISE,) * 3))


def _draw_heading(
    draw: ImageDraw.ImageDraw,
    page: MenuPage,
    layout: PageLayout,
    accent: str,
    fonts: Fonts,
    neutral: bool,
) -> None:
    font = fonts(layout.heading_size, True)
    lines = layout.heading_lines
    centers = (84,) if len(lines) == 1 else (66, 102)
    for line, y in zip(lines, centers, strict=True):
        draw.text((layout.text_x, y), line, font=font, fill=TEXT, anchor="lm",
                  stroke_width=STROKE, stroke_fill=OUTLINE)  # fmt: skip
    if page.secondary:
        draw.text((layout.text_x, 136), page.secondary, font=fonts(SECONDARY_SIZE, False),
                  fill=SECONDARY, anchor="lm", stroke_width=STROKE,
                  stroke_fill=OUTLINE)  # fmt: skip
    elif neutral:
        draw.rectangle((layout.text_x, 120, layout.text_x + 119, 123), fill=accent)


def cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)),
                           Image.Resampling.LANCZOS)  # fmt: skip
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _load(path: str | None) -> Image.Image | None:
    if path is None:
        return None
    try:
        with Image.open(Path(path)) as image:
            image.load()
            return image
    except OSError:
        return None


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
