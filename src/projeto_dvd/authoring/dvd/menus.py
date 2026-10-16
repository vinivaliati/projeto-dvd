"""Menu pages as DVD video: a still MPEG-2 background and the buttons spumux adds on top."""

import xml.etree.ElementTree as ET
from pathlib import Path

from projeto_dvd.encode.video import CODEC_OPTIONS, COLOR_TAGS
from projeto_dvd.menus.layout import PageLayout


def page_file(job_dir: Path, index: int) -> Path:
    return job_dir / f"menu{index}.mpg"


def menu_video_command(background: Path, aspect: str, output: Path) -> list[str]:
    """One second of the still picture, interlaced as NTSC DVD requires, with silent AC-3.

    A fixed quantizer, not a bitrate: for a still it gives the best last frame, the one that
    stays on screen (about 100 KB, under the 229 KB of the VBV). Without +ilme the stream is
    marked progressive_sequence=1, outside the DVD standard. Some old players stumble on a
    menu without audio, and the silence costs nothing.
    """
    return [
        "ffmpeg", "-y", "-nostdin", "-loop", "1", "-framerate", "30000/1001",
        "-i", str(background), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
        "-vf", f"format=yuv420p,setsar={'32/27' if aspect == '16:9' else '8/9'}",
        *CODEC_OPTIONS, "-q:v", "2", "-maxrate", "9000k", "-flags", "+cgop+ilme+ildct",
        "-top", "1",
        "-aspect", aspect, "-bsf:v", COLOR_TAGS, "-c:a", "ac3", "-b:a", "192k",
        "-f", "dvd", "-muxrate", "10080k", "-packetsize", "2048", str(output),
    ]  # fmt: skip


def spumux_buttons_xml(layout: PageLayout, highlight: Path, select: Path) -> str:
    """Explicit button boxes and arrows (no autodetection, which merges touching areas)."""
    root = ET.Element("subpictures", format="NTSC")
    spu = ET.SubElement(
        ET.SubElement(root, "stream"),
        "spu",
        {"start": "00:00:00.00", "force": "yes", "highlight": str(highlight),
         "select": str(select)},
    )  # fmt: skip
    for button in layout.buttons:
        box = button.box
        ET.SubElement(spu, "button", {
            "name": str(button.number), "x0": str(box.x0), "y0": str(box.y0),
            "x1": str(box.x1), "y1": str(box.y1), "up": str(button.up),
            "down": str(button.down), "left": str(button.left), "right": str(button.right),
        })  # fmt: skip
    return ET.tostring(root, encoding="unicode")


def spumux_menu_command(xml: Path, stream: int) -> list[str]:
    """Reads the menu program stream on stdin and writes it with the buttons on stdout."""
    return ["spumux", "-m", "dvd", "-s", str(stream), str(xml)]
