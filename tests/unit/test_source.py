import json
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library.probe import summarize
from projeto_dvd.planner import source
from projeto_dvd.planner.source import VideoMode, check_video, classify_frames, geometry


def stream(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920,
        "height": 1080, "r_frame_rate": "24000/1001", "avg_frame_rate": "24000/1001",
        "display_aspect_ratio": "16:9", "field_order": "progressive",
    }  # fmt: skip
    base.update(fields)
    return base


AUDIO = {"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6}


def check(*streams: dict[str, Any], duration: str | None = "7200") -> source.SourceCheck:
    fmt = {} if duration is None else {"duration": duration}
    return check_video(summarize({"streams": list(streams), "format": fmt}))


def test_bluray_1080p_film_is_supported() -> None:
    result = check(stream(), AUDIO)

    assert result.reasons == ()
    assert result.mode == VideoMode.FILM
    assert not result.needs_frame_scan


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"r_frame_rate": "25/1", "avg_frame_rate": "25/1"}, source.PAL),
        ({"r_frame_rate": "50/1", "avg_frame_rate": "50/1"}, source.PAL),
        ({"r_frame_rate": "24/1", "avg_frame_rate": "24/1"}, source.EXACT_24),
        ({"r_frame_rate": "24000/1001", "avg_frame_rate": "23000/1001"}, source.VARIABLE_FPS),
        ({"r_frame_rate": "30000/1001", "avg_frame_rate": "30000/1001"}, source.PROGRESSIVE_2997),
        ({"r_frame_rate": "60000/1001", "avg_frame_rate": "60000/1001"}, source.FPS_5994),
        ({"r_frame_rate": "30000/1001", "avg_frame_rate": "30000/1001", "field_order": "tt"},
         source.INTERLACED_HD),
        ({"r_frame_rate": "15/1", "avg_frame_rate": "15/1"}, source.other_rate("15")),
        ({"color_transfer": "smpte2084"}, source.HDR),
        ({"width": 3840, "height": 2160}, source.ABOVE_1080P),
    ],
)  # fmt: skip
def test_refusals(fields: dict[str, Any], reason: str) -> None:
    assert reason in check(stream(**fields), AUDIO).reasons


def test_missing_rate_is_refused_with_the_generic_text() -> None:
    result = check(stream(r_frame_rate="0/0", avg_frame_rate="0/0"), AUDIO)

    assert result.reasons == (source.other_rate("?"),)


def test_no_audio_no_duration_and_all_reasons_at_once() -> None:
    result = check(stream(color_transfer="smpte2084", width=3840, height=2160), duration=None)

    assert set(result.reasons) == {source.NO_AUDIO, source.NO_DURATION, source.HDR,
                                   source.ABOVE_1080P}  # fmt: skip


def test_no_video() -> None:
    assert check(AUDIO).reasons == (source.NO_VIDEO,)


@pytest.mark.parametrize(
    ("order", "tff"), [("tt", True), ("tb", True), ("bb", False), ("bt", False)]
)
def test_480i_h264_is_interlaced_by_the_first_letter(order: str, tff: bool) -> None:
    result = check(
        stream(width=720, height=480, r_frame_rate="30000/1001", avg_frame_rate="30000/1001",
               field_order=order, display_aspect_ratio="4:3"),
        AUDIO,
    )  # fmt: skip

    assert result.reasons == ()
    assert (result.mode, result.top_field_first) == (VideoMode.INTERLACED, tff)


def test_interlaced_outside_720x480_is_refused() -> None:
    result = check(
        stream(width=640, height=480, r_frame_rate="30000/1001",
               avg_frame_rate="30000/1001", field_order="tt"),
        AUDIO,
    )  # fmt: skip

    assert result.reasons == (source.INTERLACED_OTHER,)


@pytest.mark.parametrize("width", [720, 704])
def test_mpeg2_sd_needs_a_frame_scan_whatever_its_rate(width: int) -> None:
    result = check(
        stream(codec_name="mpeg2video", width=width, height=480, r_frame_rate="179/6",
               avg_frame_rate="24000/1001"),
        AUDIO,
    )  # fmt: skip

    assert result.reasons == ()
    assert result.needs_frame_scan
    assert result.mode is None


def frames(*items: tuple[int, int, int]) -> str:
    return json.dumps(
        {"frames": [
            {"repeat_pict": r, "interlaced_frame": i, "top_field_first": t} for r, i, t in items
        ]}
    )  # fmt: skip


def test_soft_telecine_is_film() -> None:
    cadence = [(1, 0, 1), (0, 0, 0), (1, 0, 0), (0, 0, 1)] * 30

    assert classify_frames(frames(*cadence)) == VideoMode.FILM


def test_true_interlaced_is_interlaced() -> None:
    assert classify_frames(frames(*[(0, 1, 1)] * 120)) == VideoMode.INTERLACED


def test_mixed_is_hybrid() -> None:
    mixed = [(1, 0, 1), (0, 0, 0), (1, 0, 0), (0, 0, 1)] * 15 + [(0, 1, 1)] * 60

    assert classify_frames(frames(*mixed)) == VideoMode.HYBRID


def test_progressive_2997_mpeg2_is_refused() -> None:
    assert classify_frames(frames(*[(0, 0, 1)] * 120)) == source.PROGRESSIVE_2997


def test_no_frames_is_refused() -> None:
    assert classify_frames(json.dumps({"frames": []})) == source.FRAMES_UNREADABLE


def test_frame_scan_command_reads_three_windows() -> None:
    command = source.frame_scan_command(Path("/media/a/b.mkv"), 1000.0)

    assert command[:3] == ["ffprobe", "-v", "error"]
    assert "100.000%+20,500.000%+20,900.000%+20" in command
    assert command[-1] == "/media/a/b.mkv"


@pytest.mark.parametrize(
    ("size", "dar", "expected"),
    [
        ((1920, 800), "12:5", ("16:9", 720, 356, True)),
        ((1920, 1080), "16:9", ("16:9", 720, 480, True)),
        ((1920, 1038), "1.85", ("16:9", 720, 460, True)),
        ((1992, 1200), "1.66", ("16:9", 672, 480, True)),
        ((1440, 1080), "4:3", ("4:3", 720, 480, True)),
        ((1440, 1080), "16:9", ("16:9", 720, 480, True)),
        ((1080, 1080), "1:1", ("4:3", 540, 480, True)),
        ((720, 480), "16:9", ("16:9", 720, 480, False)),
        ((720, 480), "4:3", ("4:3", 720, 480, False)),
        ((704, 480), "4:3", ("4:3", 704, 480, False)),
    ],
)
def test_geometry(size: tuple[int, int], dar: str, expected: tuple[str, int, int, bool]) -> None:
    width, height = size
    ratio = dar if ":" in dar else f"{float(dar) * 1000:.0f}:1000"
    summary = summarize(
        {"streams": [stream(width=width, height=height, display_aspect_ratio=ratio)], "format": {}}
    )
    assert summary.video is not None

    result = geometry(summary.video)

    assert (result.aspect, result.width, result.height, result.scale) == expected
    assert result.height % 4 == 0 and result.width % 2 == 0


@pytest.mark.parametrize(("tops", "expected"), [((1, 1, 0), True), ((0, 0, 1), False)])
def test_top_field_first_from_frames(tops: tuple[int, ...], expected: bool) -> None:
    probe = json.dumps({"frames": [{"top_field_first": top} for top in tops]})

    assert source.top_field_first_from_frames(probe) is expected
