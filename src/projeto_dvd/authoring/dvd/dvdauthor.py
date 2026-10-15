"""dvdauthor XML for a disc without menu: the title starts as soon as the disc is inserted."""

import xml.etree.ElementTree as ET
from pathlib import Path

from projeto_dvd.planner.dvd_plan import DvdPlan

SHOW_FIRST_SUBTITLE = 64  # bit 6 = display, plus track 0


def chapter_time(seconds: float) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:06.3f}"


def dvdauthor_xml(plan: DvdPlan, job_dir: Path) -> str:
    root = ET.Element("dvdauthor", dest=str(job_dir / "dvd"))
    vmgm = ET.SubElement(root, "vmgm")
    ET.SubElement(vmgm, "fpc").text = "jump title 1;"
    # Without a video format here dvdauthor fails with "no video format specified for VMGM".
    ET.SubElement(ET.SubElement(vmgm, "menus"), "video", format="ntsc", aspect=plan.aspect)
    titles = ET.SubElement(ET.SubElement(root, "titleset"), "titles")
    video = {"format": "ntsc", "aspect": plan.aspect}
    if plan.aspect == "16:9":
        video["widescreen"] = "nopanscan"  # a 4:3 TV letterboxes instead of cropping
    ET.SubElement(titles, "video", video)
    for audio in plan.audio:
        ET.SubElement(titles, "audio", {"lang": audio.language} if audio.language else {})
    for subtitle in plan.subtitles:
        attrs = {"lang": subtitle.language} if subtitle.language else {}
        ET.SubElement(titles, "subpicture", attrs)
    pgc = ET.SubElement(titles, "pgc")
    # audio=0 always: otherwise the player picks by its own language setting (often English).
    shown = SHOW_FIRST_SUBTITLE if plan.subtitle_on else 0
    ET.SubElement(pgc, "pre").text = f"audio=0;subtitle={shown};"
    chapters = ",".join(chapter_time(start) for start in plan.chapters)
    ET.SubElement(pgc, "vob", file=str(job_dir / "movie.mpg"), chapters=chapters)
    ET.SubElement(pgc, "post").text = "exit;"
    return ET.tostring(root, encoding="unicode")


def dvdauthor_command(xml: Path) -> list[str]:
    return ["dvdauthor", "-x", str(xml)]
