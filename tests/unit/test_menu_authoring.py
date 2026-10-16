import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from projeto_dvd.authoring.dvd.dvdauthor import (
    MAX_COMMANDS,
    command_count,
    disc_xml,
    title_dispatcher,
)
from projeto_dvd.authoring.dvd.menus import (
    menu_video_command,
    page_file,
    spumux_buttons_xml,
    spumux_menu_command,
)
from projeto_dvd.menus.layout import layout_page, letterbox_layout, letterbox_y
from projeto_dvd.menus.pages import build_pages
from projeto_dvd.planner.disc_plan import DiscPlan, MenuPlan
from projeto_dvd.planner.dvd_plan import AudioChoice, SubtitleChoice
from tests.plans import make_disc_plan, make_title_plan

JOB = Path("/w")
AUDIO = ("Português", "Inglês")


def disc(kind: str, count: int, subtitles: tuple[str, ...] = (), **title: object) -> DiscPlan:
    names = [f"Título {n}" for n in range(1, count + 1)]
    pages = build_pages(kind, names, "Disco", None, AUDIO, subtitles)  # type: ignore[arg-type]
    titles = tuple(
        make_title_plan(path=f"D/{n}.mkv", menu_name=name, **title)
        for n, name in enumerate(names, 1)
    )
    menu = MenuPlan(aspect="16:9", backdrop=None, accent="#E0A526", side="left", pages=pages)
    return make_disc_plan(titles=titles, menu=menu)


def parse(plan: DiscPlan) -> ET.Element:
    return ET.fromstring(disc_xml(plan, JOB))


def vmgm_pgcs(root: ET.Element) -> list[ET.Element]:
    return root.findall("vmgm/menus/pgc")


def text(element: ET.Element | None) -> str:
    assert element is not None and element.text is not None
    return element.text


def test_first_play_sets_the_registers_and_opens_the_dispatcher() -> None:
    root = parse(make_disc_plan(subtitle_on=1))
    assert text(root.find("vmgm/fpc")) == (
        "g0 = 0; g1 = 1; g2 = 0; g3 = 1024; g5 = 0; jump menu 1;"
    )


def test_the_title_key_always_opens_the_main_page() -> None:
    first = vmgm_pgcs(parse(disc("series", 3)))[0]
    assert first.get("entry") == "title" and first.find("vob") is None
    assert text(first.find("pre")) == "g2 = 0; g3 = 1024; g5 = 0; jump menu 3;"


def test_the_title_dispatcher_clears_g2_before_jumping() -> None:
    second = vmgm_pgcs(parse(disc("series", 3)))[1]
    assert second.get("entry") is None and second.find("vob") is None
    pre = text(second.find("pre"))
    assert pre.startswith("g4 = g2; g2 = 0;")
    assert "if (g4 == 3) jump title 3;" in pre and pre.endswith("jump menu 3;")


def test_the_page_dispatcher_shows_the_page_or_the_current_language() -> None:
    plan = disc("series", 8, ("Português",))
    third = vmgm_pgcs(parse(plan))[2]
    pre = text(third.find("pre"))
    assert third.find("vob") is None
    # pages: 0 main, 1-2 episodes, 3-4 audio, 5-6 subtitles; page p is menu p + 4
    assert "if (g5 == 100) { if (g0 == 0) jump menu 7; if (g0 == 1) jump menu 8; }" in pre
    assert "if (g5 == 101) { if (g1 == 0) jump menu 9; if (g1 == 1) jump menu 10; }" in pre
    assert "if (g5 == 2) jump menu 6;" in pre and pre.endswith("jump menu 4;")


def test_visible_pages_remember_themselves_and_their_button() -> None:
    pgcs = vmgm_pgcs(parse(disc("series", 8, ("Português",))))[3:]  # the visible pages
    assert text(pgcs[0].find("pre")) == "g5 = 0; button = g3;"
    assert pgcs[0].find("vob").attrib == {"file": "/w/menu0.mpg", "pause": "inf"}  # type: ignore[union-attr]
    assert text(pgcs[3].find("pre")) == "g5 = 100; button = 1024;"
    assert text(pgcs[4].find("pre")) == "g5 = 100; button = 2048;"


def buttons(pgc: ET.Element) -> list[str]:
    return [text(b) for b in pgc.findall("button")]


def test_series_buttons() -> None:
    pgcs = vmgm_pgcs(parse(disc("series", 8, ("Português",))))[3:]  # the visible pages
    assert buttons(pgcs[0]) == [
        "g2 = 0; g3 = 1024; g5 = 0; jump title 1;",
        "g3 = 1024; jump menu 5;",
        "g3 = 3072; g5 = 100; jump menu 3;",
        "g3 = 4096; g5 = 101; jump menu 3;",
    ]
    episodes = buttons(pgcs[1])
    assert episodes[0] == "g2 = 0; g3 = 1024; g5 = 1; jump title 1;"
    assert episodes[6:] == ["g3 = 2048; jump menu 4;", "g3 = 1024; jump menu 6;"]
    assert buttons(pgcs[4]) == [
        "g0 = 0; jump menu 7;", "g0 = 1; jump menu 8;", "g3 = 3072; jump menu 4;",
    ]  # fmt: skip
    assert buttons(pgcs[6])[-1] == "g3 = 4096; jump menu 4;"


def test_every_button_targets_an_existing_title_or_menu() -> None:
    for plan in (disc("movies", 1), disc("movies", 4), disc("movies", 7, ("Português",)),
                 disc("series", 13, ("Português", "Inglês"))):  # fmt: skip
        xml = disc_xml(plan, JOB)
        menus = len(vmgm_pgcs(ET.fromstring(xml)))
        for title in map(int, re.findall(r"jump title (\d+)", xml)):
            assert 1 <= title <= len(plan.titles)
        for menu in map(int, re.findall(r"jump menu (\d+)", xml)):
            assert 1 <= menu <= menus


def posts(root: ET.Element) -> list[str]:
    return [text(t.find("titles/pgc/post")) for t in root.findall("titleset")]


def test_a_movie_returns_to_its_page_and_button() -> None:
    assert posts(parse(disc("movies", 7)))[6] == "g2 = 0; g3 = 1024; g5 = 2; call vmgm menu 2;"
    assert posts(parse(disc("movies", 2)))[1] == "g2 = 0; g3 = 2048; g5 = 0; call vmgm menu 2;"


def test_episodes_continue_and_the_last_returns_with_episodes_highlighted() -> None:
    assert posts(parse(disc("series", 3))) == [
        "g2 = 2; call vmgm menu 2;",
        "g2 = 3; call vmgm menu 2;",
        "g2 = 0; g3 = 2048; g5 = 0; call vmgm menu 2;",
    ]


def test_one_titleset_per_title_declares_only_its_tracks() -> None:
    root = parse(make_disc_plan())
    titlesets = root.findall("titleset")
    assert len(titlesets) == 2
    assert [a.get("lang") for a in titlesets[0].findall("titles/audio")] == ["pt", "en"]
    assert text(titlesets[0].find("menus/pgc/pre")) == "g2 = 0; jump vmgm menu 1;"
    assert titlesets[0].find("menus/pgc").get("entry") == "root"  # type: ignore[union-attr]
    assert titlesets[1].find("titles/pgc/vob").get("file") == "/w/title2.mpg"  # type: ignore[union-attr]


def test_a_title_maps_the_disc_choice_to_its_streams() -> None:
    plan = make_disc_plan(titles=(make_title_plan(audio_map=(0, 0), subtitle_map=(None, 0)),))
    pre = text(parse(plan).find("titleset/titles/pgc/pre"))
    assert pre == (
        "audio = 0; if (g0 == 0) audio = 0; if (g0 == 1) audio = 0; subtitle = 0; "
        "if (g1 == 2) subtitle = 64;"
    )


def test_a_title_declares_its_subtitles_and_tracks_without_language() -> None:
    subtitles = (
        SubtitleChoice(key="s3", stream_index=3, file=None, language="pt"),
        SubtitleChoice(key="f:a.srt", stream_index=None, file="D/a.srt", language=None),
    )
    audio = (AudioChoice(index=1, language=None, action="ac3", channels=2, kbps=192,
                         downmix=None, offset=0.0),)  # fmt: skip
    title = make_title_plan(audio=audio, audio_map=(0,), subtitles=subtitles,
                            subtitle_map=(0, 1))  # fmt: skip
    titles = parse(make_disc_plan(titles=(title,))).find("titleset/titles")
    assert titles is not None
    assert [s.attrib for s in titles.findall("subpicture")] == [{"lang": "pt"}, {}]
    assert [a.attrib for a in titles.findall("audio")] == [{}]
    assert "if (g1 == 2) subtitle = 65;" in text(titles.find("pgc/pre"))


def test_menus_are_16_9_with_a_letterbox_subpicture() -> None:
    menus = parse(make_disc_plan()).find("vmgm/menus")
    assert menus is not None and menus.get("lang") == "pt"
    assert menus.find("video").attrib == {  # type: ignore[union-attr]
        "format": "ntsc", "aspect": "16:9", "widescreen": "nopanscan",
    }  # fmt: skip
    modes = [s.get("mode") for s in menus.findall("subpicture/stream")]
    assert modes == ["widescreen", "letterbox"]


def test_4_3_menus_have_one_subpicture_stream() -> None:
    plan = make_disc_plan()
    assert plan.menu is not None
    plan = plan.model_copy(update={"menu": plan.menu.model_copy(update={"aspect": "4:3"})})
    menus = parse(plan).find("vmgm/menus")
    assert menus is not None and menus.find("subpicture") is None
    assert menus.find("video").attrib == {"format": "ntsc", "aspect": "4:3"}  # type: ignore[union-attr]


def test_sixty_titles_fit_in_128_commands() -> None:
    assert command_count(title_dispatcher(60)) <= MAX_COMMANDS
    disc_xml(disc("series", 60), JOB)


def test_a_dispatcher_over_128_commands_raises() -> None:
    with pytest.raises(ValueError, match="128"):
        disc_xml(disc("series", 64), JOB)


def test_a_plan_without_menu_is_refused() -> None:
    with pytest.raises(ValueError, match="without menu"):
        disc_xml(make_disc_plan(menu=None), JOB)


# Menu video and buttons


def test_menu_video_is_interlaced_and_quantizer_based() -> None:
    command = menu_video_command(Path("bg.png"), "16:9", Path("m.mpg"))
    assert command[command.index("-flags") + 1] == "+cgop+ilme+ildct"
    assert command[command.index("-q:v") + 1] == "2"
    assert "-b:v" not in command and command[-1] == "m.mpg"
    # ffmpeg refuses a VBV buffer size without a max rate.
    assert command[command.index("-maxrate") + 1] == "9000k"
    assert "setsar=32/27" in command[command.index("-vf") + 1]
    assert "setsar=8/9" in " ".join(menu_video_command(Path("b"), "4:3", Path("m")))


def measure(label: str, size: int) -> float:
    return len(label) * size * 0.6


def test_spumux_xml_has_explicit_buttons() -> None:
    page = build_pages("series", ["a", "b"], "S", None, AUDIO, ())[0]
    layout = layout_page(page, "16:9", "left", measure)
    root = ET.fromstring(spumux_buttons_xml(layout, Path("hl.png"), Path("sel.png")))
    spu = root.find("stream/spu")
    assert spu is not None
    assert (spu.get("force"), spu.get("highlight"), spu.get("select")) == (
        "yes", "hl.png", "sel.png",
    )  # fmt: skip
    first = spu.findall("button")[0].attrib
    box = layout.buttons[0].box
    assert first == {
        "name": "1", "x0": str(box.x0), "y0": str(box.y0), "x1": str(box.x1),
        "y1": str(box.y1), "up": "1", "down": "2", "left": "1", "right": "1",
    }  # fmt: skip


def test_letterbox_buttons_are_the_widescreen_ones_moved() -> None:
    page = build_pages("series", ["a", "b"], "S", None, AUDIO, ())[0]
    wide = layout_page(page, "16:9", "left", measure)
    narrow = letterbox_layout(wide)
    for w, n in zip(wide.buttons, narrow.buttons, strict=True):
        assert (n.box.x0, n.box.x1) == (w.box.x0, w.box.x1)
        assert (n.box.y0, n.box.y1) == (letterbox_y(w.box.y0), letterbox_y(w.box.y1))
        assert n.marker.y0 == letterbox_y(w.marker.y0)


def test_spumux_and_page_file() -> None:
    assert spumux_menu_command(Path("b.xml"), 1) == ["spumux", "-m", "dvd", "-s", "1", "b.xml"]
    assert page_file(JOB, 3) == JOB / "menu3.mpg"
