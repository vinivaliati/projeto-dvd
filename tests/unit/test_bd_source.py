from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library.probe import summarize
from projeto_dvd.planner.bd_source import (
    HeaderReport,
    bd_copy_reason,
    parse_trace_headers,
    trace_headers_command,
)
from projeto_dvd.planner.disc import DiscTitle
from projeto_dvd.planner.source import bd_frame
from tests.unit.test_disc import VIDEO, audio, choices, title

REMUX = {**VIDEO, "profile": "High", "level": 41, "pix_fmt": "yuv420p",
         "sample_aspect_ratio": "1:1", "tags": {"NUMBER_OF_BYTES": "20000000000"}}  # fmt: skip
GOOD = HeaderReport(hrd=True, slices=4, max_dec_frame_buffering=4)


def line(name: str, value: int) -> str:
    return f"[trace_headers @ 0x1] 157         {name:<40}{value:b} = {value}"


def test_trace_headers_command_reads_the_first_seconds() -> None:
    command = trace_headers_command(Path("/media/a.mkv"), 0, seconds=3)

    assert command == ["ffmpeg", "-hide_banner", "-nostdin", "-v", "info", "-i", "/media/a.mkv",
                       "-map", "0:0", "-t", "3", "-c", "copy", "-bsf:v", "trace_headers",
                       "-f", "null", "-"]  # fmt: skip


def test_parse_trace_headers_counts_slices_per_frame() -> None:
    frame = [line("first_mb_in_slice", mb) for mb in (0, 2040, 4080, 6120)]
    text = "\n".join([line("nal_hrd_parameters_present_flag", 1),
                      line("max_dec_frame_buffering", 4), *frame, *frame,
                      line("first_mb_in_slice", 0)])  # fmt: skip

    assert parse_trace_headers(text) == HeaderReport(hrd=True, slices=1, max_dec_frame_buffering=4)
    assert parse_trace_headers("\n".join(frame * 3)).slices == 4


def test_parse_trace_headers_of_a_web_file() -> None:
    text = "\n".join(["[trace_headers @ 0x1] Sequence Parameter Set",
                      line("nal_hrd_parameters_present_flag", 0),
                      *[line("first_mb_in_slice", 0)] * 5])  # fmt: skip

    assert parse_trace_headers(text) == HeaderReport(hrd=False, slices=1,
                                                     max_dec_frame_buffering=None)  # fmt: skip


@pytest.mark.parametrize(
    ("fields", "frame"),
    [({}, (1920, 1080, False)), ({"height": 800}, (1920, 1080, False)),
     ({"width": 1440, "sample_aspect_ratio": "4:3"}, (1920, 1080, True)),
     ({"width": 1280, "height": 720}, (1280, 720, False)),
     ({"width": 720, "height": 480}, None), ({"sample_aspect_ratio": "4:3"}, None)],
)  # fmt: skip
def test_bd_frame(fields: dict[str, Any], frame: tuple[int, int, bool] | None) -> None:
    video = summarize({"streams": [{**REMUX, **fields}], "format": {}}).video
    assert video is not None

    assert bd_frame(video) == frame


def remux(**fields: Any) -> DiscTitle:
    found = title("P/a.mkv", [audio(1, "por")], video_stream={**REMUX, **fields})
    return replace(found, video=replace(found.video, size=30_000_000_000))


def test_a_blu_ray_remux_is_copied() -> None:
    assert bd_copy_reason(remux(), choices(), GOOD, 24) is None
    assert bd_copy_reason(remux(width=1440, sample_aspect_ratio="4:3"), choices(), GOOD, 24) is None


def test_before_the_sample_the_headers_are_checked_when_generating() -> None:
    assert bd_copy_reason(remux(), choices(), None, None) is None


@pytest.mark.parametrize(
    ("fields", "headers", "gop", "reason"),
    [
        ({"codec_name": "hevc"}, GOOD, 24, "não é H.264"),
        ({"profile": "High 10"}, GOOD, 24, "perfil High 10"),
        ({"level": 51}, GOOD, 24, "level 5.1"),
        ({"pix_fmt": "yuv420p10le"}, GOOD, 24, "10 bits"),
        ({"height": 800}, GOOD, 24, "1920x800"),
        ({"tags": {}}, GOOD, 24, "tamanho do vídeo desconhecido"),
        ({}, replace(GOOD, hrd=False), 24, "sem HRD"),
        ({}, replace(GOOD, slices=1), 24, "1 slice"),
        ({}, replace(GOOD, max_dec_frame_buffering=5), 24, "DPB"),
        ({}, GOOD, 250, "GOP de 250 quadros"),
    ],
)  # fmt: skip
def test_what_is_not_copied(
    fields: dict[str, Any], headers: HeaderReport, gop: int, reason: str
) -> None:
    result = bd_copy_reason(remux(**fields), choices(), headers, gop)

    assert result is not None and reason in result


def test_reencode_checked_is_never_copied() -> None:
    assert bd_copy_reason(remux(), choices(reencode_rips=True), GOOD, 24) == "Recodificar marcado"
