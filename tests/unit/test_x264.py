from pathlib import Path

import pytest

from projeto_dvd.encode.x264 import X264_PARAMS, x264_pass_command
from projeto_dvd.planner.disc_plan import TitlePlan
from projeto_dvd.planner.source import VideoMode

SOURCE = Path("/media/F/a.mkv")


def plan(width: int = 1920, height: int = 1080, scale: bool = False) -> TitlePlan:
    return TitlePlan(path="F/a.mkv", video_index=0, size=1, mtime_ns=1, duration=60.0,
                     mode=VideoMode.FILM, top_field_first=True, aspect="16:9", width=width,
                     height=height, scale=scale, hd_color=True, audio=(), subtitles=(),
                     chapters=(0.0,), audio_map=(), subtitle_map=(), menu_name="A")  # fmt: skip


def test_second_pass_with_the_blu_ray_parameters() -> None:
    command = x264_pass_command(SOURCE, plan(), 20_000, 35_000, 2, Path("/job/x264"),
                                Path("/job/video.h264"))  # fmt: skip

    assert command == [
        "ffmpeg", "-y", "-nostdin", "-i", "/media/F/a.mkv", "-map", "0:0",
        "-r", "24000/1001", "-fps_mode", "cfr",
        "-vf", "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
        "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-b:v", "20000k", "-maxrate", "35000k", "-bufsize", "30000k",
        "-x264-params", X264_PARAMS, "-an", "-sn", "-dn",
        "-pass", "2", "-passlogfile", "/job/x264", "-progress", "pipe:1", "-nostats",
        "-f", "h264", "/job/video.h264",
    ]  # fmt: skip
    assert "vbv" not in X264_PARAMS and "open-gop=0" in X264_PARAMS


def test_first_pass_goes_to_null() -> None:
    command = x264_pass_command(SOURCE, plan(), 20_000, 35_000, 1, Path("/job/x264"),
                                Path("/job/video.h264"))  # fmt: skip

    assert command[-3:] == ["-f", "null", "-"] and command[command.index("-pass") + 1] == "1"


@pytest.mark.parametrize(
    ("shape", "filters"),
    [((1920, 1080, True), "scale=1920:1080:flags=lanczos,setsar=1"),
     ((1280, 720, False), "pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,setsar=1")],
)  # fmt: skip
def test_geometry(shape: tuple[int, int, bool], filters: str) -> None:
    command = x264_pass_command(SOURCE, plan(*shape), 9_000, 35_000, 2, Path("/j/x"),
                                Path("/j/v.h264"))  # fmt: skip

    assert command[command.index("-vf") + 1] == filters
