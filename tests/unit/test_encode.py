from pathlib import Path

import pytest

from projeto_dvd.encode.audio import audio_command
from projeto_dvd.encode.video import video_filters, video_pass_command
from projeto_dvd.planner.dvd_plan import AudioChoice
from projeto_dvd.planner.source import VideoMode
from tests.plans import make_movie, movie_title

SOURCE = Path("/media/Filme/Filme.mkv")
JOB = Path("/work/jobs/7")


def test_filters_for_a_scope_hd_movie() -> None:
    assert video_filters(movie_title()) == (
        "scale=720:356:flags=lanczos+accurate_rnd+full_chroma_int,"
        "colorspace=all=smpte170m:iall=bt709,format=yuv420p,pad=720:480:0:62:black,"
        "setsar=32/27"
    )


def test_filters_for_a_dvd_rip_skip_scale_and_color() -> None:
    plan = movie_title(scale=False, hd_color=False, width=704, height=480, aspect="4:3")

    assert video_filters(plan) == "format=yuv420p,pad=720:480:8:0:black,setsar=8/9"


def test_hybrid_repeats_fields_first() -> None:
    plan = movie_title(mode=VideoMode.HYBRID, scale=False, hd_color=False, width=720, height=480)

    assert video_filters(plan).startswith("repeatfields,format=yuv420p")


def test_film_pass_one() -> None:
    command = video_pass_command(make_movie(), 1, SOURCE, JOB, 1)

    assert command[:6] == ["ffmpeg", "-y", "-nostdin", "-i", str(SOURCE), "-map"]
    assert command[6] == "0:0"
    assert command[command.index("-r") + 1] == "24000/1001"
    assert command[command.index("-fps_mode") + 1] == "cfr"
    assert command[command.index("-b:v") + 1] == "8487k"
    assert command[command.index("-maxrate") + 1] == "9000k"
    assert command[command.index("-bufsize") + 1] == "1835k"
    assert command[command.index("-flags") + 1] == "+cgop"
    assert command[command.index("-aspect") + 1] == "16:9"
    assert command[command.index("-pass") + 1] == "1"
    assert command[command.index("-passlogfile") + 1] == str(JOB / "pass")
    assert "-top" not in command
    assert "-target" not in command
    assert command[-3:] == ["-f", "null", "-"]


def test_pass_two_writes_the_elementary_stream() -> None:
    command = video_pass_command(make_movie(), 1, SOURCE, JOB, 2)

    assert command[-3:] == ["-f", "mpeg2video", str(JOB / "title1.m2v")]
    assert command[command.index("-bsf:v") + 1] == (
        "mpeg2_metadata=colour_primaries=6:transfer_characteristics=6:matrix_coefficients=6"
    )
    assert command[command.index("-progress") + 1] == "pipe:1"


@pytest.mark.parametrize(("tff", "top"), [(True, "1"), (False, "0")])
def test_interlaced_uses_ntsc_rate_and_field_order(tff: bool, top: str) -> None:
    plan = movie_title(mode=VideoMode.INTERLACED, top_field_first=tff, scale=False,
                     hd_color=False, width=720, height=480)  # fmt: skip

    command = video_pass_command(make_movie(plan), 1, SOURCE, JOB, 2)

    assert command[command.index("-r") + 1] == "30000/1001"
    assert command[command.index("-flags") + 1] == "+cgop+ilme+ildct"
    assert command[command.index("-top") + 1] == top


def choice(**fields: object) -> AudioChoice:
    base: dict[str, object] = {"index": 3, "language": "pt", "action": "ac3", "channels": 6,
                               "kbps": 448, "downmix": None, "offset": 0.0}  # fmt: skip
    base.update(fields)
    return AudioChoice.model_validate(base)


def test_copy_audio() -> None:
    command = audio_command(choice(action="copy"), SOURCE, JOB / "audio1.ac3")

    assert command == [
        "ffmpeg", "-y", "-nostdin", "-i", str(SOURCE), "-map", "0:3", "-vn", "-sn", "-dn",
        "-c:a", "copy", "-progress", "pipe:1", "-nostats", "-f", "ac3", str(JOB / "audio1.ac3"),
    ]  # fmt: skip


def test_convert_audio_keeps_the_layout() -> None:
    command = audio_command(choice(), SOURCE, JOB / "a.ac3")

    assert command[command.index("-c:a") : command.index("-c:a") + 6] == [
        "-c:a", "ac3", "-b:a", "448k", "-ar", "48000",
    ]  # fmt: skip
    assert "-ac" not in command


def test_convert_audio_downmixes_when_asked() -> None:
    command = audio_command(choice(downmix=2, kbps=192, channels=2), SOURCE, JOB / "a.ac3")

    assert command[command.index("-ac") + 1] == "2"


def test_audio_that_starts_before_the_video_is_trimmed() -> None:
    command = audio_command(choice(offset=-0.25), SOURCE, JOB / "a.ac3")

    assert command[command.index("-ss") + 1] == "0.250000"
