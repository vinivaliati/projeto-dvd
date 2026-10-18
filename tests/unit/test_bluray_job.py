import hashlib
import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from projeto_dvd.authoring.bluray import qa as bd_qa
from projeto_dvd.authoring.bluray.libs import BdInfo, BdStream
from projeto_dvd.encode.bd_extract import normalize_srt
from projeto_dvd.jobs import bluray
from projeto_dvd.jobs import cache as jobs_cache
from projeto_dvd.jobs.pipeline import (
    CacheUse,
    PipelineError,
    PipelineResult,
    QaFailed,
    Step,
    overall_progress,
    steps_for,
)
from projeto_dvd.jobs.runner import Canceled, RunResult
from projeto_dvd.planner.disc_plan import DiscPlan
from projeto_dvd.planner.dvd_plan import AudioChoice, SubtitleChoice
from tests.plans import make_disc_plan, make_title_plan
from tests.tree import make_file

VIDEO = b"\x00\x00\x00\x01h264-video"


def plan(copy: bool = False, subtitles: bool = True) -> DiscPlan:
    audio = (AudioChoice(index=1, language="pt", action="copy", channels=6, kbps=640,
                         downmix=None, offset=0.0, codec="ac3"),
             AudioChoice(index=2, language="en", action="ac3", channels=6, kbps=640,
                         downmix=6, offset=0.25, codec="truehd"))  # fmt: skip
    subs = (SubtitleChoice(key="s3", stream_index=3, file=None, language="pt", codec="pgs"),
            SubtitleChoice(key="f:a.en.srt", stream_index=None, file="F/a.en.srt",
                           language="en", codec="text"))  # fmt: skip
    title = make_title_plan(path="F/a.mkv", size=4, mtime_ns=0, duration=600.0,
                            chapters=(0.0, 300.0), audio=audio, width=1920, height=1080,
                            subtitles=subs if subtitles else (), copy_video=copy,
                            video_bytes=len(VIDEO) if copy else None)  # fmt: skip
    return make_disc_plan(profile="bd25", folder="F", volume="F", iso_name="F (BD).iso",
                          titles=(title,), menu=None, subtitle_on=1, video_kbps=20_000,
                          maxrate_kbps=35_000, estimated_bytes=10**6)  # fmt: skip


class FakeTools:
    def __init__(self, tsmuxer_says: str = "100.0% complete\nMux successful complete\n",
                 decode_stderr: str = "") -> None:  # fmt: skip
        self.commands: list[list[str]] = []
        self.tsmuxer_says = tsmuxer_says
        self.decode_stderr = decode_stderr

    def run(self, command: list[str], *, duration: float | None = None,
            on_progress: Callable[[float], None] | None = None, stdin: Path | None = None,
            stdout: Path | None = None) -> RunResult:  # fmt: skip
        self.commands.append(command)
        if on_progress:
            on_progress(1.0)
        if "-passlogfile" in command:
            make_file(Path(command[command.index("-passlogfile") + 1] + "-0.log"), b"stats")
        if command[0] == "tsMuxeR":
            assert stdout is not None
            make_file(stdout, self.tsmuxer_says.encode())
            make_file(Path(command[2]), b"iso" * 100)
        elif command[-1] == "-":
            return RunResult({"progress": "end"}, self.decode_stderr)
        else:
            make_file(Path(command[-1]), VIDEO if command[-1].endswith(".h264") else b"data")
        return RunResult({"progress": "end", "out_time_us": "600000000"}, "")

    def capture(self, command: list[str]) -> str:
        self.commands.append(command)
        return json.dumps({"streams": [
            {"index": 0, "codec_type": "video", "start_time": "1.4", "duration": "600.0"},
            {"index": 1, "codec_type": "audio", "start_time": "1.4", "duration": "600.0"},
            {"index": 2, "codec_type": "audio", "start_time": "1.4", "duration": "600.0"},
        ]})  # fmt: skip


GOOD_INFO = BdInfo(detected=True, first_play=True, duration=600.0, chapters=(0.0, 300.0),
                   video=(BdStream(0x1B, 6, 1, ""),),
                   audio=(BdStream(0x81, 6, 1, "por"), BdStream(0x81, 6, 1, "eng")),
                   pg=(BdStream(0x90, 0, 0, "por"), BdStream(0x90, 0, 0, "eng")))  # fmt: skip


@pytest.fixture
def disc(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    state: dict[str, object] = {"info": GOOD_INFO, "es": hashlib.sha256(VIDEO).hexdigest()}
    monkeypatch.setattr(bluray, "udf_tree", lambda iso: bd_qa.REQUIRED)
    monkeypatch.setattr(bluray, "bd_info", lambda iso: state["info"])
    monkeypatch.setattr(bluray, "udf_copy", lambda iso, inner, target: make_file(target, b"ts"))
    monkeypatch.setattr(bluray, "es_sha256", lambda command: state["es"])
    yield state


def media(tmp_path: Path) -> Path:
    folder = tmp_path / "media"
    make_file(folder / "F" / "a.mkv", b"mkv!")
    make_file(folder / "F" / "a.en.srt", b"\xef\xbb\xbf1\r\n00:00:01,000 --> 00:00:02,000\r\nHi")
    os.utime(folder / "F" / "a.mkv", ns=(0, 0))
    return folder


Steps = list[tuple[Step, int]]


def run(tmp_path: Path, p: DiscPlan, tools: FakeTools, cache: CacheUse | None = None,
        cancel: Callable[[], bool] = lambda: False) -> tuple[PipelineResult, Steps]:  # fmt: skip
    steps: list[tuple[Step, int]] = []
    result = bluray.run_bluray(
        p, media_dir=media(tmp_path), job_dir=tmp_path / "job", output_dir=tmp_path / "out",
        tools=tools, report=lambda step, fraction, title: steps.append((step, title)),
        should_cancel=cancel, cache=cache,
    )  # fmt: skip
    return result, steps


def programs(tools: FakeTools) -> list[str]:
    return [" ".join(c[:1] + [part for part in c if part.startswith(("-f", "libx264"))])
            for c in tools.commands]  # fmt: skip


def test_an_encoded_title_becomes_a_published_iso(tmp_path: Path, disc: object) -> None:
    tools = FakeTools()

    result, steps = run(tmp_path, plan(), tools)

    assert result.iso_path == tmp_path / "out" / "iso" / "F (BD).iso"
    assert result.iso_path.exists()
    commands = [" ".join(c) for c in tools.commands]
    assert sum("libx264" in c for c in commands) == 2
    assert any("adelay=250:all=1" in c for c in commands)
    assert any(c.endswith("-f sup " + str(tmp_path / "job" / "s1.sup")) for c in commands)
    srt = tmp_path / "job" / "s2.srt"
    meta = (tmp_path / "job" / "disc.meta").read_text()
    assert 'S_TEXT/UTF8, "' + str(srt) + '"' in meta and "default=all" in meta
    order = [Step.VIDEO_PASS1, Step.VIDEO_PASS2, Step.AUDIO, Step.SUBTITLES, Step.ISO]
    assert list(dict.fromkeys(s for s, _ in steps))[:5] == order
    assert not list((tmp_path / "job").glob("x264*"))
    assert Step.COPY in [s for s, _ in steps]
    assert not (tmp_path / "job" / "video.h264").exists()


def test_the_external_srt_is_cleaned_for_tsmuxer(
    tmp_path: Path, disc: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bytes] = []

    def spy(data: bytes) -> bytes:
        seen.append(data)
        return normalize_srt(data)

    monkeypatch.setattr(bluray, "normalize_srt", spy)

    run(tmp_path, plan(), FakeTools())

    assert seen and seen[0].startswith(b"\xef\xbb\xbf")


def test_a_remux_is_copied_without_x264(tmp_path: Path, disc: dict[str, object]) -> None:
    disc["info"] = BdInfo(**{**GOOD_INFO.__dict__, "pg": ()})
    tools = FakeTools()

    run(tmp_path, plan(copy=True, subtitles=False), tools)

    commands = [" ".join(c) for c in tools.commands]
    assert not any("libx264" in c for c in commands)
    assert any("h264_mp4toannexb" in c for c in commands)


def test_a_tsmuxer_warning_fails_the_job(tmp_path: Path, disc: object) -> None:
    tools = FakeTools(tsmuxer_says="Warning! MLP codec is not standard for BD disks\n")

    with pytest.raises(PipelineError) as error:
        run(tmp_path, plan(), tools)

    assert "Warning! MLP codec" in error.value.message and error.value.step == Step.ISO
    assert not (tmp_path / "out" / "iso" / "F (BD).iso").exists()


def test_a_disc_that_does_not_match_fails_the_qa(tmp_path: Path, disc: dict[str, object]) -> None:
    disc["es"] = "0" * 64

    with pytest.raises(QaFailed) as error:
        run(tmp_path, plan(), FakeTools())

    assert not error.value.report.passed
    assert error.value.report.first_failure.name == "es"  # type: ignore[union-attr]


def test_a_disc_libbluray_cannot_read_fails_the_qa(
    tmp_path: Path, disc: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(iso: Path) -> BdInfo:
        raise OSError("libbluray could not open")

    monkeypatch.setattr(bluray, "bd_info", unreadable)

    with pytest.raises(QaFailed) as error:
        run(tmp_path, plan(), FakeTools(decode_stderr="corrupt frame"))

    names = [c.name for c in error.value.report.checks if not c.ok]
    assert names == ["read", "decode"]


def test_the_second_encode_comes_from_the_cache(tmp_path: Path, disc: object) -> None:
    use = CacheUse(work_dir=tmp_path / "work", limit_bytes=10**9, ffmpeg="7.1")
    again = plan().model_copy(update={"replace_existing": True})
    tools = FakeTools()

    run(tmp_path, again, FakeTools(), cache=use)
    run(tmp_path, again, tools, cache=use)

    assert not any("libx264" in " ".join(c) for c in tools.commands)
    assert jobs_cache.cache_bytes(use.work_dir) == len(VIDEO)


def test_cancel_stops_before_the_next_step(tmp_path: Path, disc: object) -> None:
    with pytest.raises(Canceled):
        run(tmp_path, plan(), FakeTools(), cancel=lambda: True)


def test_a_source_that_changed_stops_the_job(tmp_path: Path, disc: object) -> None:
    moved = plan()
    moved = moved.model_copy(update={"titles": (moved.titles[0].model_copy(update={"size": 9}),)})

    with pytest.raises(PipelineError):
        run(tmp_path, moved, FakeTools())


def test_blu_ray_steps_and_progress() -> None:
    p = plan()
    title_steps, disc_steps = steps_for(p)

    assert Step.PULLDOWN not in title_steps and disc_steps == (Step.ISO, Step.QA, Step.COPY)
    assert overall_progress(p, Step.VIDEO_COPY, 0.0, 1) == 0.0
    assert overall_progress(p, Step.COPY, 1.0, 0) == pytest.approx(1.0)


def test_a_text_subtitle_of_the_mkv_is_extracted(tmp_path: Path, disc: dict[str, object]) -> None:
    p = plan()
    text = SubtitleChoice(key="s4", stream_index=4, file=None, language="en", codec="text")
    p = p.model_copy(update={"titles": (p.titles[0].model_copy(update={"subtitles": (text,)}),)})
    tools = FakeTools()
    disc["info"] = BdInfo(**{**GOOD_INFO.__dict__, "pg": (BdStream(0x90, 0, 0, "eng"),)})

    run(tmp_path, p, tools)

    srt = tmp_path / "job" / "s1.srt"
    assert ["srt", str(srt)] in [c[-2:] for c in tools.commands]


def test_a_cache_without_room_is_off(tmp_path: Path, disc: object) -> None:
    use = CacheUse(work_dir=tmp_path / "work", limit_bytes=0, ffmpeg="7.1")

    run(tmp_path, plan(), FakeTools(), cache=use)

    assert jobs_cache.cache_bytes(use.work_dir) == 0


def test_cancel_while_copying_the_iso(tmp_path: Path, disc: object) -> None:
    calls: list[int] = []

    def count() -> bool:
        calls.append(1)
        return False

    run(tmp_path, plan().model_copy(update={"replace_existing": True}), FakeTools(), cancel=count)
    total = len(calls)
    late: list[int] = []

    def cancel_last() -> bool:
        late.append(1)
        return len(late) >= total

    with pytest.raises(Canceled):
        run(tmp_path, plan().model_copy(update={"replace_existing": True}), FakeTools(),
            cancel=cancel_last)  # fmt: skip
