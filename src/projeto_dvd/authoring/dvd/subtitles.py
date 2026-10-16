"""Text subtitles (SRT) drawn as DVD subpictures by spumux."""

import codecs
import re
import xml.etree.ElementTree as ET
from pathlib import Path

FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD = FONT.with_name("DejaVuSans-Bold.ttf")
TIMING = re.compile(
    r"^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}", re.MULTILINE
)


class SubtitleError(Exception):
    """The subtitle cannot be used (message in Portuguese, shown on the job page)."""


def decode_srt(data: bytes) -> str:
    """Brazilian subtitles come in UTF-8, Windows-1252 or UTF-16: never fail, keep accents."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = data.decode("utf-16")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def count_cues(text: str) -> int:
    return len(TIMING.findall(text))


def prepare_srt(data: bytes, name: str) -> str:
    text = decode_srt(data)
    if count_cues(text) == 0:
        # spumux would succeed with no subtitle at all: refuse before it runs.
        raise SubtitleError(f"A legenda {name} está vazia ou inválida.")
    return text


def extract_command(source: Path, stream_index: int, output: Path) -> list[str]:
    return [
        "ffmpeg", "-y", "-nostdin", "-i", str(source.absolute()),
        "-map", f"0:{stream_index}", "-c:s", "srt", str(output),
    ]  # fmt: skip


def spumux_xml(srt: Path, aspect: str) -> str:
    """DejaVu Sans 26 with an outline, inside a ~10% safe area.

    movie-height 478, not 480: a known spumux workaround (480 can push the last line out of
    the subpicture area). Both fps are 29.97 because SRT times are absolute; a different
    subtitle-fps would stretch them.
    """
    root = ET.Element("subpictures", format="NTSC")
    ET.SubElement(
        ET.SubElement(root, "stream"),
        "textsub",
        {
            "filename": str(srt), "characterset": "UTF-8", "font": str(FONT),
            "fontsize": "26.0", "fill-color": "white", "outline-color": "black",
            "outline-thickness": "2.5", "horizontal-alignment": "center",
            "vertical-alignment": "bottom", "left-margin": "72", "right-margin": "72",
            "top-margin": "48", "bottom-margin": "48", "movie-fps": "29.97",
            "subtitle-fps": "29.97", "movie-width": "720", "movie-height": "478",
            "aspect": aspect,
        },
    )  # fmt: skip
    return ET.tostring(root, encoding="unicode")


def spumux_command(xml: Path, stream_number: int) -> list[str]:
    """Reads the program stream on stdin and writes it, with one more stream, on stdout."""
    return ["spumux", "-s", str(stream_number), str(xml)]
