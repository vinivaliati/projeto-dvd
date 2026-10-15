import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library.probe import (
    ABOVE_1080P,
    DOLBY_VISION_5,
    HDR,
    NO_VIDEO,
    UNDEFINED_LANGUAGE,
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
    assert summary.audio == (
        AudioTrack(
            language="por", channels="5.1", codec="ac3", title=None, default=False, forced=False
        ),
        AudioTrack(
            language="eng",
            channels="estéreo",
            codec="aac",
            title="Comentario",
            default=False,
            forced=False,
        ),
    )
    assert summary.subtitles == (
        SubtitleTrack(
            language="por", kind="texto", codec="subrip", title=None, default=False, forced=True
        ),
    )
    assert summary.chapters == 2
    assert summary.warnings == ()


def test_cover_art_is_not_the_video_track() -> None:
    summary = summarize(fixture("cover"))

    assert summary.video is not None
    assert (summary.video.codec, summary.video.width) == ("h264", 1280)
    assert summary.audio[0].language == UNDEFINED_LANGUAGE  # "und" in the file
    assert summary.audio[0].channels == "mono"


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
    assert summary.audio[0].language == UNDEFINED_LANGUAGE  # no tag at all
    assert summary.audio[0].channels == "estéreo"
    assert len(summary.audio) == 1  # the dvd_nav_packet data stream is ignored
    assert summary.subtitles[0].codec == "dvd_subtitle"
    assert summary.subtitles[0].kind == "imagem"


def test_dolby_vision_profile_5_with_pgs() -> None:
    summary = summarize(fixture("dv5_pgs"))

    assert summary.video is not None
    assert summary.video.hdr is True
    assert summary.video.dolby_vision_5 is True
    assert summary.warnings == (HDR, DOLBY_VISION_5, ABOVE_1080P)
    assert summary.audio[0].channels == "7.1"
    assert summary.audio[0].default is True
    assert summary.subtitles[0].kind == "imagem"
    assert summary.subtitles[0].title == "Brazilian"


# Summary edge cases (small dicts)


def test_missing_values_do_not_break_the_summary() -> None:
    stream = video_stream(avg_frame_rate="0/0", r_frame_rate="0/0", display_aspect_ratio="0:1")

    summary = summarize(probe_data(stream, duration=None))

    assert summary.duration is None
    assert summary.video is not None
    assert summary.video.fps is None
    assert summary.video.aspect == pytest.approx(16 / 9)  # from the resolution
    assert summary.chapters == 0


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


@pytest.mark.parametrize(
    ("fields", "label"),
    [
        ({"channel_layout": "5.1(side)", "channels": 6}, "5.1"),
        ({"channel_layout": "stereo", "channels": 2}, "estéreo"),
        ({"channel_layout": "quad", "channels": 4}, "quad"),
        ({"channels": 1}, "mono"),
        ({"channels": 2}, "estéreo"),
        ({"channels": 6}, "5.1"),
        ({"channels": 8}, "7.1"),
        ({"channels": 3}, "3 canais"),
        ({}, "?"),
    ],
)
def test_channel_labels(fields: dict[str, Any], label: str) -> None:
    summary = summarize(probe_data(video_stream(), {"codec_type": "audio", **fields}))

    assert summary.audio[0].channels == label


@pytest.mark.parametrize(
    ("tags", "language"),
    [
        ({"language": "por"}, "por"),
        ({"language": "und"}, UNDEFINED_LANGUAGE),
        ({}, UNDEFINED_LANGUAGE),
    ],
)
def test_language(tags: dict[str, str], language: str) -> None:
    summary = summarize(probe_data(video_stream(), {"codec_type": "audio", "tags": tags}))

    assert summary.audio[0].language == language


@pytest.mark.parametrize(
    ("codec", "kind"),
    [
        ("subrip", "texto"),
        ("ass", "texto"),
        ("ssa", "texto"),
        ("mov_text", "texto"),
        ("webvtt", "texto"),
        ("hdmv_pgs_subtitle", "imagem"),
        ("dvd_subtitle", "imagem"),
        ("dvb_subtitle", "imagem"),
        ("xsub", "imagem"),
        ("eia_608", "desconhecido"),
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
