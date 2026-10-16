import json
import sys
from pathlib import Path
from typing import Any

from projeto_dvd.library.files import VideoFile
from projeto_dvd.library.probe import summarize
from projeto_dvd.library.scan import FileView, FolderView, Status
from projeto_dvd.planner import disc_source, source
from projeto_dvd.planner.disc_source import folder_reasons, prepare, suggested_plan
from projeto_dvd.planner.source import VideoMode

VIDEO = VideoFile(path="F/f.mkv", absolute=Path("/media/F/f.mkv"), size=10, mtime_ns=20)
H264 = {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
        "r_frame_rate": "24000/1001", "avg_frame_rate": "24000/1001",
        "display_aspect_ratio": "16:9"}  # fmt: skip
MPEG2 = {**H264, "codec_name": "mpeg2video", "width": 720, "height": 480,
         "r_frame_rate": "30000/1001", "avg_frame_rate": "30000/1001"}  # fmt: skip
AUDIO = {"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 2,
         "sample_rate": "48000", "bit_rate": "192000", "tags": {"language": "por"}}  # fmt: skip


def summary(*streams: dict[str, Any]) -> Any:
    return summarize({"streams": list(streams), "format": {"duration": "600"}})


def view(status: Status, files: tuple[FileView, ...]) -> FolderView:
    return FolderView(name="F", status=status, files=files, size=10, duration=600.0)


def test_folder_reasons() -> None:
    good = FileView(video=VIDEO, summary=summary(H264, AUDIO), error=None)

    assert folder_reasons(view(Status.EMPTY, ())) == ()
    assert folder_reasons(view(Status.NOT_SCANNED, (good,))) == (disc_source.SCAN_FIRST,)
    assert folder_reasons(view(Status.CHANGED, (good,))) == (disc_source.CHANGED,)
    assert folder_reasons(view(Status.OK, (good, good))) == (disc_source.ONE_VIDEO,)
    broken = FileView(video=VIDEO, summary=None, error="x")
    assert folder_reasons(view(Status.WARNINGS, (broken,))) == (disc_source.READ_ERROR,)
    assert folder_reasons(view(Status.OK, (good,))) == ()


def test_prepare_h264_film_without_frame_scan() -> None:
    def capture(command: list[str]) -> str:
        raise AssertionError("no frame scan for H.264")

    result = prepare("F", VIDEO, summary(H264, AUDIO), capture)

    assert isinstance(result, disc_source.DiscSource)
    assert result.mode == VideoMode.FILM


def test_prepare_mpeg2_uses_the_frames() -> None:
    frames = [{"repeat_pict": r, "interlaced_frame": 0, "top_field_first": t}
              for r, t in [(1, 1), (0, 0), (1, 0), (0, 1)] * 20]  # fmt: skip
    calls: list[list[str]] = []

    def capture(command: list[str]) -> str:
        calls.append(command)
        return json.dumps({"frames": frames})

    result = prepare("F", VIDEO, summary(MPEG2, AUDIO), capture)

    assert isinstance(result, disc_source.DiscSource)
    assert result.mode == VideoMode.FILM
    assert calls[0][0] == "ffprobe"


def test_prepare_returns_refusals() -> None:
    result = prepare("F", VIDEO, summary(AUDIO), lambda command: "")

    assert result == (source.NO_VIDEO,)


def test_prepare_turns_a_failed_frame_scan_into_a_refusal() -> None:
    def capture(command: list[str]) -> str:
        raise OSError("boom")

    assert prepare("F", VIDEO, summary(MPEG2, AUDIO), capture) == (source.FRAMES_UNREADABLE,)


def test_suggested_plan() -> None:
    result = prepare("F", VIDEO, summary(H264, AUDIO), lambda command: "")
    assert isinstance(result, disc_source.DiscSource)

    plan = suggested_plan(result)

    assert plan.profile == "dvd5"
    assert plan.audio[0].action == "copy"
    assert plan.path == "F/f.mkv"


def test_scanned_folder_without_summary_asks_for_a_scan() -> None:
    pending = FileView(video=VIDEO, summary=None, error=None)

    assert folder_reasons(view(Status.OK, (pending,))) == (disc_source.SCAN_FIRST,)


def test_prepare_refuses_progressive_2997_mpeg2() -> None:
    frames = [{"repeat_pict": 0, "interlaced_frame": 0, "top_field_first": 1}] * 50

    result = prepare("F", VIDEO, summary(MPEG2, AUDIO), lambda c: json.dumps({"frames": frames}))

    assert result == (source.PROGRESSIVE_2997,)


def test_run_capture_returns_stdout() -> None:
    assert disc_source.run_capture([sys.executable, "-c", "print('ok')"]).strip() == "ok"
