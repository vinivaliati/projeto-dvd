import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from projeto_dvd.authoring.dvd.dvdauthor import chapter_time, dvdauthor_command, dvdauthor_xml
from projeto_dvd.authoring.dvd.mux import (
    first_pts_command,
    iso_command,
    mux_command,
    parse_first_pts,
)
from projeto_dvd.planner.dvd_plan import AudioChoice, SubtitleChoice
from tests.plans import make_plan

JOB = Path("/work/jobs/7")


def test_first_pts_command_reads_one_frame_with_generated_timestamps() -> None:
    command = first_pts_command(JOB / "video.m2v")

    assert command[command.index("-fflags") + 1] == "+genpts"
    assert command[command.index("-read_intervals") + 1] == "%+#1"
    assert command[-1] == str(JOB / "video.m2v")


def test_parse_first_pts() -> None:
    assert parse_first_pts("\n0.055556\n") == pytest.approx(0.055556)
    # ffprobe 7.1 adds an empty column for the frame side data.
    assert parse_first_pts("0.041708,\n") == pytest.approx(0.041708)
    with pytest.raises(ValueError):
        parse_first_pts("")


def test_mux_shifts_each_audio_to_the_video_start() -> None:
    command = mux_command(make_plan(), JOB, 0.055556)

    assert command[:6] == ["ffmpeg", "-y", "-nostdin", "-fflags", "+genpts", "-i"]
    offsets = [command[i + 1] for i, arg in enumerate(command) if arg == "-itsoffset"]
    assert offsets == ["0.055556", "0.105556"]  # second audio started 50 ms late in the source
    inputs = [command[i + 1] for i, arg in enumerate(command) if arg == "-i"]
    assert inputs == [str(JOB / "video.m2v"), str(JOB / "audio1.ac3"), str(JOB / "audio2.ac3")]
    assert command[command.index("-f") + 1] == "dvd"
    assert command[command.index("-muxrate") + 1] == "10080k"
    assert command[command.index("-packetsize") + 1] == "2048"
    assert command[-1] == str(JOB / "movie.mpg")


def test_negative_offset_is_not_applied_in_the_mux() -> None:
    plan = make_plan(audio=(AudioChoice(index=1, language="pt", action="copy", channels=2,
                                        kbps=192, downmix=None, offset=-0.3),))  # fmt: skip

    command = mux_command(plan, JOB, 0.05)

    assert command[command.index("-itsoffset") + 1] == "0.050000"


def test_iso_command() -> None:
    assert iso_command(make_plan(), JOB) == [
        "genisoimage", "-quiet", "-dvd-video", "-udf", "-V", "FILME",
        "-o", str(JOB / "disc.iso"), str(JOB / "dvd"),
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("seconds", "text"), [(0.0, "0:00:00.000"), (300.0, "0:05:00.000"), (3725.5, "1:02:05.500")]
)
def test_chapter_time(seconds: float, text: str) -> None:
    assert chapter_time(seconds) == text


def parse(plan_xml: str) -> ET.Element:
    return ET.fromstring(plan_xml)


def test_xml_plays_the_title_at_once() -> None:
    root = parse(dvdauthor_xml(make_plan(), JOB))

    assert root.get("dest") == str(JOB / "dvd")
    assert root.findtext("vmgm/fpc") == "jump title 1;"
    assert root.find("vmgm/menus/video").attrib == {"format": "ntsc", "aspect": "16:9"}  # type: ignore[union-attr]
    video = root.find("titleset/titles/video")
    assert video is not None
    assert video.attrib == {"format": "ntsc", "aspect": "16:9", "widescreen": "nopanscan"}
    assert [a.get("lang") for a in root.findall("titleset/titles/audio")] == ["pt", "en"]
    assert root.findtext("titleset/titles/pgc/pre") == "audio=0;subtitle=0;"
    assert root.findtext("titleset/titles/pgc/post") == "exit;"
    vob = root.find("titleset/titles/pgc/vob")
    assert vob is not None
    assert vob.get("file") == str(JOB / "movie.mpg")
    assert vob.get("chapters") == "0:00:00.000,0:05:00.000"


def test_xml_turns_the_first_subtitle_on() -> None:
    plan = make_plan(
        subtitles=(SubtitleChoice(key="s3", stream_index=3, file=None, language="pt"),
                   SubtitleChoice(key="f:x.srt", stream_index=None, file="F/x.srt",
                                  language=None)),
        subtitle_on=True,
    )  # fmt: skip

    root = parse(dvdauthor_xml(plan, JOB))

    subpictures = root.findall("titleset/titles/subpicture")
    assert [s.attrib for s in subpictures] == [{"lang": "pt"}, {}]
    assert root.findtext("titleset/titles/pgc/pre") == "audio=0;subtitle=64;"


def test_xml_for_4_3_has_no_widescreen_and_escapes_paths() -> None:
    root = parse(dvdauthor_xml(make_plan(aspect="4:3"), Path("/work/jobs/<&>")))

    video = root.find("titleset/titles/video")
    assert video is not None and "widescreen" not in video.attrib
    assert root.get("dest") == "/work/jobs/<&>/dvd"


def test_audio_without_language() -> None:
    plan = make_plan(audio=(AudioChoice(index=1, language=None, action="copy", channels=2,
                                        kbps=192, downmix=None, offset=0.0),))  # fmt: skip

    root = parse(dvdauthor_xml(plan, JOB))

    assert [a.attrib for a in root.findall("titleset/titles/audio")] == [{}]


def test_dvdauthor_command() -> None:
    assert dvdauthor_command(JOB / "dvd.xml") == ["dvdauthor", "-x", str(JOB / "dvd.xml")]
