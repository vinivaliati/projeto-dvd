from pathlib import Path

import pytest

from projeto_dvd.api.formatting import (
    format_aspect,
    format_duration,
    format_fps,
    format_size,
    last_line,
    probe_reason,
    video_label,
)
from projeto_dvd.library.probe import Video


def test_last_line() -> None:
    error = "[matroska,webm @ 0x5945] EBML header parsing failed\nx.mkv: Invalid data found"

    assert last_line(error) == "x.mkv: Invalid data found"
    assert last_line("") == ""


def test_probe_reason_drops_the_file_path() -> None:
    path = Path("/media/Senhor dos Aneis/ruim.mkv")
    error = f"[mov @ 0x1] moov atom not found\n{path}: Invalid data found"

    assert probe_reason(error, path) == "Invalid data found"
    assert probe_reason("Permission denied", path) == "Permission denied"


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (38_000_000_000, "38 GB"),
        (12_340_000_000, "12 GB"),
        (4_230_000_000, "4,2 GB"),
        (1_000_000_000, "1 GB"),
        (512_000_000, "512 MB"),
        (2_500, "2,5 KB"),
        (0, "0 KB"),
        (1_200_000_000_000, "1,2 TB"),
    ],
)
def test_format_size(size: int, text: str) -> None:
    assert format_size(size) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (10680, "2h58"),
        (3600, "1h00"),
        (3599, "1h00"),
        (2700, "45 min"),
        (2690, "45 min"),
        (20, "0 min"),
        (None, "?"),
    ],
)
def test_format_duration(seconds: float | None, text: str) -> None:
    assert format_duration(seconds) == text


@pytest.mark.parametrize(
    ("fps", "text"),
    [(24000 / 1001, "23,976"), (24.0, "24"), (30000 / 1001, "29,97"), (25.0, "25"), (None, "?")],
)
def test_format_fps(fps: float | None, text: str) -> None:
    assert format_fps(fps) == text


@pytest.mark.parametrize(
    ("ratio", "text"),
    [(16 / 9, None), (1.77, None), (None, None), (4 / 3, "1,33:1"), (2.4, "2,40:1")],
)
def test_format_aspect_hides_16_9(ratio: float | None, text: str | None) -> None:
    assert format_aspect(ratio) == text


def make_video(codec: str, width: int, height: int, fps: float | None = 24.0) -> Video:
    return Video(
        codec=codec,
        width=width,
        height=height,
        fps=fps,
        aspect=None,
        hdr=False,
        dolby_vision_5=False,
    )


@pytest.mark.parametrize(
    ("video", "text"),
    [
        (make_video("h264", 1920, 800, 24000 / 1001), "1080p · H.264 · 23,976"),
        (make_video("hevc", 3840, 2160), "2160p · HEVC · 24"),
        (make_video("hevc", 3832, 1600), "2160p · HEVC · 24"),
        (make_video("hevc", 4096, 1716), "2160p · HEVC · 24"),
        (make_video("hevc", 2048, 858), "2048x858 · HEVC · 24"),
        (make_video("mpeg2video", 720, 480, 30000 / 1001), "720x480 · MPEG-2 · 29,97"),
        (make_video("h264", 1280, 720), "720p · H.264 · 24"),
        (make_video("vp9", 1920, 1080, None), "1080p · VP9 · ?"),
    ],
)
def test_video_label(video: Video, text: str) -> None:
    assert video_label(video) == text
