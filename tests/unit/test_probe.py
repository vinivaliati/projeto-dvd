import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library.probe import (
    ABOVE_1080P,
    DOLBY_VISION_5,
    HDR,
    NO_VIDEO,
    AudioTrack,
    FfprobeMissingError,
    ProbeResult,
    SubtitleTrack,
    ffprobe_command,
    run_ffprobe,
    summarize,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "probe"


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    return data


def video_stream(**fields: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "avg_frame_rate": "24000/1001",
        "r_frame_rate": "24000/1001",
        "display_aspect_ratio": "16:9",
    }
    stream.update(fields)
    return stream


def probe_data(*streams: dict[str, Any], duration: str | None = "60.0") -> dict[str, Any]:
    fmt = {} if duration is None else {"duration": duration}
    return {"streams": list(streams), "format": fmt, "chapters": []}


# ffprobe command and execution


def test_command_uses_the_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    command = ffprobe_command(Path("-weird.mkv"))

    assert command == [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(tmp_path / "-weird.mkv"),
    ]


def fake_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    raises: BaseException | None = None,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, **kwargs})
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_run_returns_the_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_run(monkeypatch, stdout='{"streams": []}')

    result = run_ffprobe(Path("/media/a.mkv"))

    assert result == ProbeResult(json='{"streams": []}', error=None)
    assert calls[0]["timeout"] == 60
    assert "shell" not in calls[0]


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"returncode": 1, "stderr": "a.mkv: Invalid data found\n"}, "a.mkv: Invalid data found"),
        ({"returncode": 1, "stderr": ""}, "ffprobe terminou com código 1"),
        ({"returncode": 1, "stderr": "a" * 100 + "x" * 500}, "x" * 500),
        ({"stdout": "not json"}, "ffprobe devolveu um JSON inválido"),
        (
            {"raises": subprocess.TimeoutExpired(["ffprobe"], 60)},
            "ffprobe não respondeu em 60 s",
        ),
    ],
    ids=["exit-code", "exit-code-silent", "keeps-the-end", "invalid-json", "timeout"],
)
def test_run_reports_errors(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], error: str
) -> None:
    fake_run(monkeypatch, **kwargs)

    assert run_ffprobe(Path("/media/a.mkv")) == ProbeResult(json=None, error=error)


@pytest.mark.parametrize("error", [FileNotFoundError("ffprobe"), PermissionError("ffprobe")])
def test_run_raises_when_ffprobe_cannot_start(
    monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    fake_run(monkeypatch, raises=error)

    with pytest.raises(FfprobeMissingError):
        run_ffprobe(Path("/media/a.mkv"))


# Summary from real ffprobe output (fixtures)


def test_movie_summary() -> None:
    summary = summarize(fixture("movie"))

    assert summary.duration == pytest.approx(4.0, abs=0.1)
    assert summary.video is not None
    assert (summary.video.codec, summary.video.width, summary.video.height) == ("h264", 1920, 800)
    assert summary.video.fps == pytest.approx(23.976, abs=0.001)
    assert summary.video.aspect == pytest.approx(2.4)
    assert summary.video.hdr is False
    assert summary.video.index == 0
    assert summary.video.r_frame_rate == Fraction(24000, 1001)
    assert summary.video.avg_frame_rate == Fraction(24000, 1001)
    assert summary.video.field_order == "progressive"
    assert summary.video.start_time == 0.0
    assert summary.audio == (
        AudioTrack(
            index=1,
            language="por",
            codec="ac3",
            channel_count=6,
            channel_layout="5.1(side)",
            sample_rate=48000,
            bit_rate=448000,
            start_time=-0.005,
            title=None,
            default=False,
            forced=False,
        ),
        AudioTrack(
            index=2,
            language="eng",
            codec="aac",
            channel_count=2,
            channel_layout="stereo",
            sample_rate=48000,
            bit_rate=None,
            start_time=-0.021,
            title="Comentario",
            default=False,
            forced=False,
        ),
    )
    assert summary.subtitles == (
        SubtitleTrack(
            index=3, language="por", kind="text", codec="subrip", title=None, default=False,
            forced=True,
        ),
    )  # fmt: skip
    assert summary.chapters == (0.0, 2.0)
    assert summary.warnings == ()


def test_cover_art_is_not_the_video_track() -> None:
    summary = summarize(fixture("cover"))

    assert summary.video is not None
    assert (summary.video.codec, summary.video.width) == ("h264", 1280)
    assert summary.audio[0].language is None  # "und" in the file
    assert summary.audio[0].channel_layout == "mono"


def test_cover_only_means_no_video() -> None:
    summary = summarize(fixture("cover_only"))

    assert summary.video is None
    assert summary.warnings == (NO_VIDEO,)


def test_hdr10_in_4k() -> None:
    summary = summarize(fixture("hdr10"))

    assert summary.video is not None
    assert summary.video.hdr is True
    assert summary.warnings == (HDR, ABOVE_1080P)


def test_hlg_is_hdr() -> None:
    summary = summarize(fixture("hlg"))

    assert summary.video is not None
    assert summary.video.hdr is True
    assert summary.warnings == (HDR,)


def test_dvd_mpeg2() -> None:
    summary = summarize(fixture("dvd"))

    assert summary.video is not None
    assert summary.video.codec == "mpeg2video"
    assert summary.video.fps == pytest.approx(29.97, abs=0.001)
    assert summary.video.aspect == pytest.approx(16 / 9)
    assert summary.audio[0].language is None  # no tag at all
    assert summary.audio[0].channel_count == 2
    assert summary.audio[0].bit_rate == 192000
    assert len(summary.audio) == 1  # the dvd_nav_packet data stream is ignored
    assert summary.subtitles[0].codec == "dvd_subtitle"
    assert summary.subtitles[0].kind == "image"


def test_dolby_vision_profile_5_with_pgs() -> None:
    summary = summarize(fixture("dv5_pgs"))

    assert summary.video is not None
    assert summary.video.hdr is True
    assert summary.video.dolby_vision_5 is True
    assert summary.warnings == (HDR, DOLBY_VISION_5, ABOVE_1080P)
    assert summary.audio[0].channel_layout == "7.1"
    assert summary.audio[0].default is True
    assert summary.subtitles[0].kind == "image"
    assert summary.subtitles[0].title == "Brazilian"


# Summary edge cases (small dicts)


def test_missing_values_do_not_break_the_summary() -> None:
    stream = video_stream(avg_frame_rate="0/0", r_frame_rate="0/0", display_aspect_ratio="0:1")

    summary = summarize(probe_data(stream, duration=None))

    assert summary.duration is None
    assert summary.video is not None
    assert summary.video.fps is None
    assert summary.video.aspect == pytest.approx(16 / 9)  # from the resolution
    assert summary.chapters == ()


def test_fps_falls_back_to_r_frame_rate() -> None:
    summary = summarize(probe_data(video_stream(avg_frame_rate="0/0", r_frame_rate="25/1")))

    assert summary.video is not None
    assert summary.video.fps == 25


def test_aspect_comes_from_the_sample_aspect_ratio_when_missing() -> None:
    stream = video_stream(width=720, height=480, sample_aspect_ratio="32:27")
    del stream["display_aspect_ratio"]

    summary = summarize(probe_data(stream))

    assert summary.video is not None
    assert summary.video.aspect == pytest.approx(16 / 9)


def test_garbage_values_are_unknown() -> None:
    stream = video_stream(avg_frame_rate="abc", r_frame_rate="", display_aspect_ratio="x")
    del stream["width"]

    summary = summarize(probe_data(stream, duration="N/A"))

    assert summary.duration is None
    assert summary.video is not None
    assert summary.video.fps is None
    assert summary.video.aspect is None


def test_channel_values_are_raw() -> None:
    track = {"codec_type": "audio", "channels": 6, "channel_layout": "5.1(side)"}
    other = {"codec_type": "audio", "channels": "x"}

    first, second = summarize(probe_data(video_stream(), track, other)).audio

    assert (first.channel_count, first.channel_layout) == (6, "5.1(side)")
    assert (second.channel_count, second.channel_layout) == (None, None)


def test_invalid_numbers_become_none() -> None:
    track = {"codec_type": "audio", "sample_rate": "abc", "bit_rate": "N/A"}

    audio = summarize(probe_data(video_stream(), track)).audio[0]

    assert (audio.sample_rate, audio.bit_rate, audio.start_time) == (None, None, 0.0)


def test_invalid_rates_become_none() -> None:
    data = probe_data(video_stream(avg_frame_rate="0/0", r_frame_rate="abc"))

    video = summarize(data).video
    assert video is not None
    assert (video.r_frame_rate, video.avg_frame_rate, video.fps) == (None, None, None)


@pytest.mark.parametrize(
    ("tags", "language"),
    [
        ({"language": "por"}, "por"),
        ({"language": "und"}, None),
        ({}, None),
    ],
)
def test_language(tags: dict[str, str], language: str | None) -> None:
    summary = summarize(probe_data(video_stream(), {"codec_type": "audio", "tags": tags}))

    assert summary.audio[0].language == language


@pytest.mark.parametrize(
    ("codec", "kind"),
    [
        ("subrip", "text"),
        ("ass", "text"),
        ("ssa", "text"),
        ("mov_text", "text"),
        ("webvtt", "text"),
        ("hdmv_pgs_subtitle", "image"),
        ("dvd_subtitle", "image"),
        ("dvb_subtitle", "image"),
        ("xsub", "image"),
        ("eia_608", "unknown"),
    ],
)
def test_subtitle_kind(codec: str, kind: str) -> None:
    summary = summarize(probe_data(video_stream(), {"codec_type": "subtitle", "codec_name": codec}))

    assert summary.subtitles[0].kind == kind


@pytest.mark.parametrize(
    ("width", "height", "above"),
    [(1920, 1080, False), (1920, 800, False), (2048, 858, True), (1440, 1440, True)],
)
def test_above_1080p(width: int, height: int, above: bool) -> None:
    summary = summarize(probe_data(video_stream(width=width, height=height)))

    assert (ABOVE_1080P in summary.warnings) is above


def test_no_streams_at_all() -> None:
    summary = summarize({})

    assert summary.video is None
    assert summary.audio == ()
    assert summary.warnings == (NO_VIDEO,)


def test_stream_index_and_dvd_start_time() -> None:
    summary = summarize(fixture("dvd"))

    assert summary.video is not None
    assert summary.video.index == 1
    assert summary.video.start_time == pytest.approx(0.533, abs=0.01)
    assert summary.audio[0].index == 2


def test_the_size_tag_and_the_dvd_header_of_a_rip() -> None:
    stream = {
        "index": 0, "codec_type": "video", "codec_name": "mpeg2video", "width": 720,
        "height": 480, "tags": {"NUMBER_OF_BYTES-eng": "3000000000", "BPS-eng": "5000000"},
        "side_data_list": [{"side_data_type": "CPB properties", "max_bitrate": 9800000,
                            "buffer_size": 1835008}],
    }  # fmt: skip
    video = summarize({"streams": [stream]}).video
    assert video is not None
    assert (video.stream_bytes, video.dvd_header) == (3_000_000_000, (9_800_000, 1_835_008))


def test_a_stream_without_size_or_header() -> None:
    stream = {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920,
              "height": 1080, "tags": {"NUMBER_OF_BYTES": "abc"}}  # fmt: skip
    video = summarize({"streams": [stream]}).video
    assert video is not None and (video.stream_bytes, video.dvd_header) == (None, None)
