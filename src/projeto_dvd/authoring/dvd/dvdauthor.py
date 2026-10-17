"""dvdauthor XML: the VIDEO_TS structure, the menus and the navigation commands."""

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path

from projeto_dvd.authoring.dvd.menus import page_file
from projeto_dvd.menus.pages import audio_variant, page_of_title, subtitle_variant
from projeto_dvd.planner.disc_plan import DiscPlan, MenuItem, MenuPage, TitlePlan

SHOW_FIRST_SUBTITLE = 64  # bit 6 = display, plus track 0


def chapter_time(seconds: float) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:06.3f}"


def dvdauthor_command(xml: Path) -> list[str]:
    return ["dvdauthor", "-x", str(xml)]


# Disc with menus. Every jump goes through the VMGM, which can reach any title:
#   menu 1 (entry title): where the Title key and the Menu key land: the main page, always;
#   menu 2: called at the end of each title: plays the next one (g2), clearing g2 first, or
#           falls through to menu 3;
#   menu 3: shows the page the viewer was on (g5), or the language page of the current g0/g1;
#   menu p + 4: the visible page p.
# Registers: g0 audio, g1 subtitle (0 off), g2 next title, g3 highlighted button (1024 x n),
# g4 scratch, g5 page. g14 and g15 belong to dvdauthor (buttons with several commands).
MAX_COMMANDS = 128  # per PGC (pre, post and cell commands)
TITLE_DISPATCHER = 2
PAGE_DISPATCHER = 3
FIRST_PAGE_MENU = 4
AUDIO_PAGES = 100  # g5 values that mean "the language page of the current choice"
SUBTITLE_PAGES = 101
BUTTON = 1024  # SPRM 8 keeps the button number in its high bits


CHAPTER_REACH = 1.0  # seconds a chapter of a copied title may move to find a closed GOP


def chapters_on_closed_gops(
    chapters: Sequence[float], gops: Sequence[tuple[float, bool]], reach: float = CHAPTER_REACH
) -> tuple[tuple[float, ...], list[float]]:
    """Chapters of copied video moved to the nearest closed GOP; (kept, dropped).

    dvdauthor puts a cell on the nearest GOP without a word, and jumping to an open one shows
    two broken frames. The start stays: the job checks the first GOP on its own.
    """
    closed = [start for start, is_closed in gops if is_closed]
    kept: set[float] = set()
    dropped: list[float] = []
    for chapter in chapters:
        if chapter == 0:
            kept.add(0.0)
            continue
        near = [start for start in closed if abs(start - chapter) <= reach]
        if near:
            kept.add(min(near, key=lambda start: abs(start - chapter)))
        else:
            dropped.append(chapter)
    return tuple(sorted(kept)), dropped


def disc_xml(
    plan: DiscPlan, job_dir: Path, chapters: Mapping[int, tuple[float, ...]] | None = None
) -> str:
    """`chapters` replaces the planned chapters of some titles (copied video, by number)."""
    menu = plan.menu
    if menu is None:
        raise ValueError("a disc plan without menu")
    root = ET.Element("dvdauthor", dest=str(job_dir / "dvd"))
    vmgm = ET.SubElement(root, "vmgm")
    ET.SubElement(
        vmgm, "fpc"
    ).text = f"g0 = 0; g1 = {plan.subtitle_on}; g2 = 0; g3 = {BUTTON}; g5 = 0; jump menu 1;"
    menus = ET.SubElement(vmgm, "menus", lang="pt")
    ET.SubElement(menus, "video", _video(menu.aspect))
    if menu.aspect == "16:9":
        streams = ET.SubElement(menus, "subpicture", lang="pt")
        ET.SubElement(streams, "stream", id="0", mode="widescreen")
        ET.SubElement(streams, "stream", id="1", mode="letterbox")
    _command_pgc(menus, f"g2 = 0; g3 = {BUTTON}; g5 = 0; jump menu {PAGE_DISPATCHER};",
                 entry="title")  # fmt: skip
    _command_pgc(menus, title_dispatcher(len(plan.titles)))
    _command_pgc(menus, page_dispatcher(menu.pages))
    for index, page in enumerate(menu.pages):
        pgc = ET.SubElement(menus, "pgc")
        if page.kind in ("audio", "subtitles"):
            mark = AUDIO_PAGES if page.kind == "audio" else SUBTITLE_PAGES
            pre = f"g5 = {mark}; button = {page.focus * BUTTON};"
        else:
            pre = f"g5 = {index}; button = g3;"
        ET.SubElement(pgc, "pre").text = pre
        ET.SubElement(pgc, "vob", file=str(page_file(job_dir, index)), pause="inf")
        for number, item in enumerate(page_buttons(page), 1):
            command = button_command(menu.pages, index, number, item)
            ET.SubElement(pgc, "button", name=str(number)).text = command
    for number, title in enumerate(plan.titles, 1):
        starts = (chapters or {}).get(number, title.chapters)
        _titleset(root, plan, number, title.model_copy(update={"chapters": starts}), job_dir)
    return ET.tostring(root, encoding="unicode")


def page_buttons(page: MenuPage) -> list[MenuItem]:
    """The buttons of a page in spumux order: the list, then the footer from left to right."""
    return [*page.items, *(item for item in page.footer if item is not None)]


def title_dispatcher(titles: int) -> str:
    jumps = " ".join(f"if (g4 == {n}) jump title {n};" for n in range(1, titles + 1))
    return f"g4 = g2; g2 = 0; {jumps} jump menu {PAGE_DISPATCHER};"


def page_dispatcher(pages: Sequence[MenuPage]) -> str:
    parts = []
    for kind, mark, register in (("audio", AUDIO_PAGES, "g0"), ("subtitles", SUBTITLE_PAGES, "g1")):
        variants = [(i, p) for i, p in enumerate(pages) if p.kind == kind]
        if variants:
            jumps = " ".join(
                f"if ({register} == {p.checked}) jump menu {i + FIRST_PAGE_MENU};"
                for i, p in variants
            )
            parts.append(f"if (g5 == {mark}) {{ {jumps} }}")
    parts += [
        f"if (g5 == {i}) jump menu {i + FIRST_PAGE_MENU};"
        for i, p in enumerate(pages)
        if i > 0 and p.kind not in ("audio", "subtitles")
    ]
    parts.append(f"jump menu {FIRST_PAGE_MENU};")
    return " ".join(parts)


def button_command(pages: Sequence[MenuPage], index: int, number: int, item: MenuItem) -> str:
    here = number * BUTTON
    main = pages[0]
    match item.action:
        case "play":
            return f"g2 = 0; g3 = {here}; g5 = {index}; jump title {item.target};"
        case "play_all":
            return f"g2 = 0; g3 = {here}; g5 = 0; jump title 1;"
        case "page":
            return f"g3 = {BUTTON}; jump menu {item.target + FIRST_PAGE_MENU};"
        case "audio_menu":
            return f"g3 = {here}; g5 = {AUDIO_PAGES}; jump menu {PAGE_DISPATCHER};"
        case "subtitle_menu":
            return f"g3 = {here}; g5 = {SUBTITLE_PAGES}; jump menu {PAGE_DISPATCHER};"
        case "audio":
            target = audio_variant(pages, item.target)
            return f"g0 = {item.target}; jump menu {target + FIRST_PAGE_MENU};"
        case "subtitle":
            target = subtitle_variant(pages, item.target)
            return f"g1 = {item.target}; jump menu {target + FIRST_PAGE_MENU};"
        case _:  # back
            opener = {"audio": "audio_menu", "subtitles": "subtitle_menu"}.get(pages[index].kind)
            button = next(
                n for n, it in enumerate(page_buttons(main), 1)
                if it.action == opener or (opener is None and it.action == "page")
            )  # fmt: skip
            return f"g3 = {button * BUTTON}; jump menu {FIRST_PAGE_MENU};"


def title_post(plan: DiscPlan, number: int) -> str:
    assert plan.menu is not None
    pages = plan.menu.pages
    if any(item.action == "play_all" for item in pages[0].items):  # a series
        if number < len(plan.titles):
            return f"g2 = {number + 1}; call vmgm menu {TITLE_DISPATCHER};"
        episodes = next(n for n, it in enumerate(page_buttons(pages[0]), 1) if it.action == "page")
        return f"g2 = 0; g3 = {episodes * BUTTON}; g5 = 0; call vmgm menu {TITLE_DISPATCHER};"
    page, button = page_of_title(pages, number)
    return f"g2 = 0; g3 = {button * BUTTON}; g5 = {page}; call vmgm menu {TITLE_DISPATCHER};"


def title_pre(title: TitlePlan) -> str:
    """Turn the disc choice (g0, g1) into this title's streams."""
    audio = " ".join(
        f"if (g0 == {k}) audio = {stream};" for k, stream in enumerate(title.audio_map)
    )
    subtitles = " ".join(
        f"if (g1 == {k + 1}) subtitle = {SHOW_FIRST_SUBTITLE + stream};"
        for k, stream in enumerate(title.subtitle_map)
        if stream is not None
    )
    return " ".join(part for part in ("audio = 0;", audio, "subtitle = 0;", subtitles) if part)


def command_count(commands: str) -> int:
    """An estimate of the VM commands: one per statement, one more per condition."""
    return commands.count(";") + commands.count("if (")


def _titleset(
    root: ET.Element, plan: DiscPlan, number: int, title: TitlePlan, job_dir: Path
) -> None:
    titleset = ET.SubElement(root, "titleset")
    menus = ET.SubElement(titleset, "menus", lang="pt")
    ET.SubElement(menus, "video", _video(title.aspect))
    # The Menu key during the title: back to the main menu, never into the next episode.
    _command_pgc(menus, "g2 = 0; jump vmgm menu 1;", entry="root")
    titles = ET.SubElement(titleset, "titles")
    ET.SubElement(titles, "video", _video(title.aspect))
    for audio in title.audio:
        ET.SubElement(titles, "audio", {"lang": audio.language} if audio.language else {})
    for subtitle in title.subtitles:
        attrs = {"lang": subtitle.language} if subtitle.language else {}
        ET.SubElement(titles, "subpicture", attrs)
    pgc = ET.SubElement(titles, "pgc")
    ET.SubElement(pgc, "pre").text = title_pre(title)
    chapters = ",".join(chapter_time(start) for start in title.chapters)
    ET.SubElement(pgc, "vob", file=str(job_dir / f"title{number}.mpg"), chapters=chapters)
    ET.SubElement(pgc, "post").text = title_post(plan, number)


def _command_pgc(parent: ET.Element, commands: str, entry: str | None = None) -> None:
    if command_count(commands) > MAX_COMMANDS:
        raise ValueError(f"more than {MAX_COMMANDS} commands in one PGC")
    pgc = ET.SubElement(parent, "pgc", {"entry": entry} if entry else {})
    ET.SubElement(pgc, "pre").text = commands


def _video(aspect: str) -> dict[str, str]:
    video = {"format": "ntsc", "aspect": aspect}
    if aspect == "16:9":
        video["widescreen"] = "nopanscan"  # a 4:3 TV letterboxes instead of cropping
    return video
