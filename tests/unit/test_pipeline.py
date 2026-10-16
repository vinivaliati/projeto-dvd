import json
import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from projeto_dvd.authoring.dvd.qa import QaReport, required_tree
from projeto_dvd.encode.mpeg2 import PulldownError, StreamReport
from projeto_dvd.jobs import pipeline
from projeto_dvd.jobs.files import cannot_write
from projeto_dvd.jobs.pipeline import (
    PipelineError,
    QaFailed,
    Step,
    overall_progress,
    preflight,
    run_pipeline,
)
from projeto_dvd.jobs.runner import Canceled, RunResult, ToolError
from projeto_dvd.library.probe import ProbeResult
from projeto_dvd.planner.disc_plan import DiscPlan, TitlePlan
from projeto_dvd.planner.dvd_plan import SubtitleChoice
from projeto_dvd.planner.source import VideoMode
from tests.plans import make_disc_plan, make_movie, movie_title
from tests.tree import make_file

MOVIE = json.dumps({
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
         "r_frame_rate": "24000/1001", "avg_frame_rate": "24000/1001",
         "display_aspect_ratio": "16:9"},
        {"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 2,
         "sample_rate": "48000", "bit_rate": "192000", "tags": {"language": "por"}},
    ],
    "format": {"duration": "600"},
})  # fmt: skip


def listing(titles: int) -> str:
    return "\n".join(f"{path};1" for path in required_tree(titles, menus=True))


THREE_LETTERS = {"pt": "por", "en": "eng", None: "und"}


def disc_probe(plan: TitlePlan) -> str:
    """What ffprobe -f dvdvideo would say about a disc made exactly as planned."""
    streams: list[dict[str, object]] = [
        {"codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 480,
         "display_aspect_ratio": plan.aspect, "r_frame_rate": "30000/1001"},
    ]  # fmt: skip
    streams += [{"codec_type": "audio", "codec_name": "ac3", "nb_read_packets": "10",
                 "tags": {"language": THREE_LETTERS[a.language]}} for a in plan.audio]  # fmt: skip
    streams += [{"codec_type": "subtitle", "codec_name": "dvd_subtitle", "nb_read_packets": "3",
                 "tags": {"language": THREE_LETTERS[s.language]}}
                for s in plan.subtitles]  # fmt: skip
    chapters = [{"start_time": str(start)} for start in plan.chapters]
    return json.dumps({"streams": streams, "chapters": chapters,
                       "format": {"duration": str(plan.duration)}})  # fmt: skip


def menu_probe(aspect: str) -> str:
    return json.dumps({"streams": [
        {"codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 480,
         "display_aspect_ratio": aspect},
        {"codec_type": "audio", "codec_name": "ac3"},
    ]})  # fmt: skip


def mux_packets(plan: TitlePlan) -> str:
    streams = [{"index": 0, "codec_type": "video", "id": "0x1e0"}]
    packets = [{"stream_index": 0, "pts_time": "0.555556"}]
    for number, audio in enumerate(plan.audio, start=1):
        streams.append({"index": number, "codec_type": "audio", "id": hex(0x7F + number)})
        start = 0.555556 + max(audio.offset, 0.0)
        packets.append({"stream_index": number, "pts_time": f"{start:.6f}"})
    return json.dumps({"streams": streams, "packets": packets})


class FakeTools:
    """Records commands; creates the output file of each; can fail at one tool."""

    def __init__(self, fail_at: str | None = None, stderr: str = "",
                 decode_stderr: str = "") -> None:  # fmt: skip
        self.commands: list[list[str]] = []
        self.fail_at = fail_at
        self.stderr = stderr
        self.decode_stderr = decode_stderr
        self.plan: DiscPlan = make_movie()

    def run(self, command: list[str], *, duration: float | None = None,
            on_progress: Callable[[float], None] | None = None, stdin: Path | None = None,
            stdout: Path | None = None) -> RunResult:  # fmt: skip
        self.commands.append(command)
        if self.fail_at and self.fail_at in " ".join(command):
            raise ToolError(command[0], 1, self.stderr)
        if on_progress:
            on_progress(1.0)
        if command[-3:] == ["-f", "null", "-"] and "dvdvideo" in command:
            return RunResult({"progress": "end"}, self.decode_stderr)
        if stdout is not None:
            make_file(stdout, b"spu")
        elif command[0] == "dvdauthor":
            dvd = Path(command[2]).parent / "dvd" / "VIDEO_TS"
            for number in range(1, len(self.plan.titles) + 1):
                make_file(dvd / f"VTS_{number:02d}_1.VOB", b"v" * 100)
        elif command[-1].endswith(".srt"):
            make_file(Path(command[-1]), b"1\n00:00:01,000 --> 00:00:02,000\nOi\n")
        elif command[-1] != "-":
            output = Path(command[-1] if command[0] != "genisoimage" else command[-2])
            make_file(output, b"\x00\x00\x01\xb3" + bytes([0x2D, 0x01, 0xE0, 0x31]) + b"\xff" * 8)
        seconds = str(int(self.plan.titles[0].duration * 1e6))
        return RunResult({"dup_frames": "0", "drop_frames": "0", "out_time_us": seconds,
                          "progress": "end"}, "")  # fmt: skip

    def capture(self, command: list[str]) -> str:
        self.commands.append(command)
        if command[0] == "isoinfo":
            return listing(len(self.plan.titles))
        if "-menu" in command:
            assert self.plan.menu is not None
            return menu_probe(self.plan.menu.aspect)
        if "dvdvideo" in command:
            return disc_probe(self.plan.titles[int(command[command.index("-title") + 1]) - 1])
        if any(arg.startswith("stream=") for arg in command):
            number = int(re.search(r"title(\d+)\.mpg", command[-1]).group(1))  # type: ignore[union-attr]
            return mux_packets(self.plan.titles[number - 1])
        return "0.055556\n"


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    media, job, output = tmp_path / "media", tmp_path / "work" / "jobs" / "1", tmp_path / "out"
    source = make_file(media / "Filme" / "Filme.mkv", b"x" * 100)
    os.utime(source, ns=(200, 200))
    return media, job, output


def run(
    dirs: tuple[Path, Path, Path], tools: FakeTools, plan: DiscPlan | None = None,
    **title_fields: object,
) -> pipeline.PipelineResult:  # fmt: skip
    media, job, output = dirs
    tools.plan = plan or make_movie(movie_title(**title_fields))
    return run_pipeline(tools.plan, media_dir=media, job_dir=job, output_dir=output,
                        tools=tools, report=lambda step, fraction, title: None,
                        should_cancel=lambda: False)  # fmt: skip


GOOD_STREAM = StreamReport(frame_rate_codes={4}, progressive_sequence={0}, aspect_codes={3},
                           pictures=100, repeated=50, max_gop=12)  # fmt: skip


@pytest.fixture(autouse=True)
def stream_report(monkeypatch: pytest.MonkeyPatch) -> list[StreamReport]:
    reports = [GOOD_STREAM]
    monkeypatch.setattr(pipeline, "inspect_stream", lambda path: reports[0])
    return reports


@pytest.fixture(autouse=True)
def no_pulldown(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    patched: list[Path] = []

    def fake(path: Path, checkpoint: Callable[[], None]) -> int:
        patched.append(path)
        return 1

    monkeypatch.setattr(pipeline, "apply_soft_pulldown", fake)
    return patched


def test_runs_the_steps_in_order_and_publishes_the_iso(
    dirs: tuple[Path, Path, Path], no_pulldown: list[Path]
) -> None:
    tools = FakeTools()

    result = run(dirs, tools)

    tools_used = [command[0] for command in tools.commands]
    assert tools_used == [
        "ffmpeg", "ffmpeg", "ffmpeg", "ffmpeg", "ffprobe", "ffmpeg", "ffprobe",  # the title
        "ffmpeg", "spumux", "spumux",  # the menu: still, widescreen and letterbox buttons
        "dvdauthor", "genisoimage", "isoinfo",
        "ffprobe", "ffmpeg", "ffmpeg",  # QA of the title
        "ffprobe", "ffmpeg",  # QA of the menu page
    ]  # fmt: skip
    assert no_pulldown == [dirs[1] / "title1.m2v"]
    assert result.iso_path == dirs[2] / "iso" / "Filme.iso"
    assert result.iso_path.exists()
    job = dirs[1]
    assert sorted(path.name for path in job.iterdir()) == ["dvd.xml"]


def test_interlaced_plan_skips_the_pulldown(
    dirs: tuple[Path, Path, Path], no_pulldown: list[Path]
) -> None:
    run(dirs, FakeTools(), mode=VideoMode.INTERLACED)

    assert no_pulldown == []


def test_changed_source_stops_before_any_tool(dirs: tuple[Path, Path, Path]) -> None:
    tools = FakeTools()
    os.utime(dirs[0] / "Filme" / "Filme.mkv", ns=(999, 999))

    with pytest.raises(PipelineError) as caught:
        run(dirs, tools)

    assert caught.value.message == pipeline.SOURCE_CHANGED.format(name="Filme.mkv")
    assert tools.commands == []


def test_tool_failure_names_the_step(dirs: tuple[Path, Path, Path]) -> None:
    with pytest.raises(PipelineError) as caught:
        run(dirs, FakeTools(fail_at="-pass 2"))

    assert caught.value.step == Step.VIDEO_PASS2
    assert caught.value.message == "Falhou na etapa Vídeo: 2ª passada (codificação)."


def test_no_space_has_its_own_message(dirs: tuple[Path, Path, Path]) -> None:
    tools = FakeTools(fail_at="dvdauthor", stderr="write failed: No space left on device")

    with pytest.raises(PipelineError) as caught:
        run(dirs, tools)

    assert caught.value.message == pipeline.NO_SPACE


def test_cancel_between_steps(dirs: tuple[Path, Path, Path]) -> None:
    media, job, output = dirs
    tools = FakeTools()
    calls = iter([False, False, True])

    with pytest.raises(Canceled):
        run_pipeline(make_movie(), media_dir=media, job_dir=job, output_dir=output, tools=tools,
                     report=lambda s, f, t: None,
                     should_cancel=lambda: next(calls, True))  # fmt: skip

    assert len(tools.commands) == 2


def test_existing_iso_is_not_replaced_without_confirmation(dirs: tuple[Path, Path, Path]) -> None:
    make_file(dirs[2] / "iso" / "Filme.iso", b"old")

    with pytest.raises(PipelineError) as caught:
        run(dirs, FakeTools())

    assert caught.value.message == pipeline.ISO_EXISTS
    assert (dirs[2] / "iso" / "Filme.iso").read_bytes() == b"old"
    assert not (dirs[2] / "iso" / "Filme.iso.part").exists()
    assert (dirs[1] / "disc.iso").exists()  # kept for inspection


def test_existing_iso_is_replaced_when_confirmed(dirs: tuple[Path, Path, Path]) -> None:
    make_file(dirs[2] / "iso" / "Filme.iso", b"old")

    result = run(dirs, FakeTools(), make_movie(replace_existing=True))

    assert result.iso_path.read_bytes() != b"old"


def test_failed_copy_removes_the_part_file(
    dirs: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace

    def broken_replace(source: str, target: str) -> None:
        if str(target).endswith(".iso"):
            raise OSError(28, "No space left on device")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", broken_replace)

    with pytest.raises(PipelineError):
        run(dirs, FakeTools())

    assert not (dirs[2] / "iso" / "Filme.iso.part").exists()
    assert (dirs[1] / "disc.iso").exists()


def test_overall_progress_uses_the_weights() -> None:
    plan = make_movie()
    assert overall_progress(plan, Step.VIDEO_PASS1, 0.0, 1) == 0.0
    assert overall_progress(plan, Step.VIDEO_PASS2, 0.0, 1) == pytest.approx(35 / 103)
    assert overall_progress(plan, Step.MENUS, 0.0, 0) == pytest.approx(93 / 103)
    assert overall_progress(plan, Step.COPY, 1.0, 0) == 1.0


def test_titles_weigh_by_their_duration() -> None:
    plan = make_disc_plan(titles=(movie_title(duration=1000.0), movie_title(duration=3000.0)))
    assert overall_progress(plan, Step.VIDEO_PASS1, 0.0, 2) == pytest.approx(0.25 * 93 / 103)
    assert overall_progress(plan, Step.SUBTITLES, 1.0, 2) == pytest.approx(93 / 103)


def test_a_converted_phase_3_job_is_refused(dirs: tuple[Path, Path, Path]) -> None:
    with pytest.raises(PipelineError) as caught:
        run(dirs, FakeTools(), make_movie(menu=None))
    assert caught.value.message == pipeline.OLD_PLAN


def test_two_titles_are_encoded_authored_and_checked(dirs: tuple[Path, Path, Path]) -> None:
    media, job, output = dirs
    second = make_file(media / "Filme" / "Dois.mkv", b"y" * 100)
    os.utime(second, ns=(200, 200))
    plan = make_disc_plan(folder="Filme", iso_name="Filme.iso", titles=(
        movie_title(), movie_title(path="Filme/Dois.mkv", audio=movie_title().audio[:1],
                                   audio_map=(0, 0)),
    ))  # fmt: skip
    tools = FakeTools()
    steps: list[tuple[Step, int]] = []

    tools.plan = plan
    result = run_pipeline(plan, media_dir=media, job_dir=job, output_dir=output, tools=tools,
                          report=lambda step, fraction, title: steps.append((step, title)),
                          should_cancel=lambda: False)  # fmt: skip

    assert (Step.VIDEO_PASS2, 2) in steps and (Step.MENUS, 0) in steps
    passes = [c for c in tools.commands if "-pass" in c and c[c.index("-pass") + 1] == "2"]
    assert [c[-1] for c in passes] == [str(job / "title1.m2v"), str(job / "title2.m2v")]
    assert [c[c.index("-title") + 1] for c in tools.commands if "-show_chapters" in c] == [
        "1", "2",
    ]  # fmt: skip
    menus = [c for c in tools.commands if "-pgc" in c and c[0] == "ffprobe"]
    assert [c[c.index("-pgc") + 1] for c in menus] == ["4", "5"]  # main and episodes pages
    assert result.qa_json is not None
    names = {c.name for c in QaReport.model_validate_json(result.qa_json).checks}
    assert {"t1-video", "t2-video", "m1-menu", "m2-bitstream"} <= names


def test_preflight_reports_space_and_existing_iso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work, output = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    make_file(output / "iso" / "Filme.iso")
    usage = shutil.disk_usage(tmp_path)
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda path: usage._replace(free=12_000_000_000))  # fmt: skip

    errors = preflight(work, output, 8_500_000_000, "Filme.iso", replace=False)

    assert "Falta espaço na pasta de trabalho: precisa de 18 GB livres e há 12 GB." in errors
    assert pipeline.ISO_EXISTS_FORM in errors
    assert preflight(work, output, 1_000_000, "Filme.iso", replace=True) == []


def test_preflight_reports_a_folder_that_cannot_be_written(tmp_path: Path) -> None:
    errors = preflight(tmp_path / "missing", tmp_path, 1, "F.iso", replace=False)

    assert errors == [cannot_write("pasta de trabalho", tmp_path / "missing")]


def test_main_refuses_an_unknown_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")

    assert pipeline.main(["Nada"]) == 2
    assert "Pasta não encontrada" in capsys.readouterr().err


def test_main_reports_refusals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    make_file(tmp_path / "media" / "Dois" / "a.mkv")
    make_file(tmp_path / "media" / "Dois" / "b.mkv")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    monkeypatch.setattr(pipeline, "run_ffprobe", lambda path: ProbeResult(json=None, error="x"))

    assert pipeline.main(["Dois"]) == 1
    assert "a.mkv: não foi possível ler o arquivo" in capsys.readouterr().err


def test_main_generates_with_the_suggested_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_file(tmp_path / "media" / "Filme" / "Filme.mkv")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    monkeypatch.setattr(pipeline, "run_ffprobe", lambda path: ProbeResult(json=MOVIE, error=None))
    seen: list[DiscPlan] = []

    def fake_run(plan: DiscPlan, **kwargs: object) -> pipeline.PipelineResult:
        seen.append(plan)
        kwargs["report"](Step.VIDEO_PASS1, 0.5, 1)  # type: ignore[operator]
        kwargs["report"](Step.ISO, 0.5, 0)  # type: ignore[operator]
        return pipeline.PipelineResult(
            iso_path=tmp_path / "out" / "iso" / "Filme.iso", qa_json=None
        )

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run)

    assert pipeline.main(["Filme"]) == 0
    assert seen[0].folder == "Filme" and seen[0].menu is not None
    out = capsys.readouterr().out
    assert "Filme.iso" in out and "Título 1: " in out


def test_main_reports_a_pipeline_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    make_file(tmp_path / "media" / "Filme" / "Filme.mkv")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    monkeypatch.setattr(pipeline, "run_ffprobe", lambda path: ProbeResult(json=MOVIE, error=None))

    def failing(plan: DiscPlan, **kwargs: object) -> pipeline.PipelineResult:
        raise PipelineError("Falhou na etapa Áudio.")

    monkeypatch.setattr(pipeline, "run_pipeline", failing)

    assert pipeline.main(["Filme"]) == 1
    err = capsys.readouterr().err
    assert "Falhou na etapa Áudio." in err and "job.log" in err


def test_pass_logs_are_removed(dirs: tuple[Path, Path, Path]) -> None:
    make_file(dirs[1] / "pass-0.log")

    run(dirs, FakeTools())

    assert not (dirs[1] / "pass-0.log").exists()


def test_pulldown_error_is_a_pipeline_error(
    dirs: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: Path, checkpoint: Callable[[], None]) -> int:
        raise PulldownError("O vídeo já tem o ajuste de quadros (pulldown).")

    monkeypatch.setattr(pipeline, "apply_soft_pulldown", broken)

    with pytest.raises(PipelineError) as caught:
        run(dirs, FakeTools())

    assert caught.value.step == Step.PULLDOWN


def test_missing_source_stops(dirs: tuple[Path, Path, Path]) -> None:
    (dirs[0] / "Filme" / "Filme.mkv").unlink()

    with pytest.raises(PipelineError) as caught:
        run(dirs, FakeTools())

    assert caught.value.message == pipeline.SOURCE_CHANGED.format(name="Filme.mkv")


def test_unreadable_first_pts_fails_the_mux(dirs: tuple[Path, Path, Path]) -> None:
    tools = FakeTools()
    tools.capture = lambda command: ""  # type: ignore[method-assign]

    with pytest.raises(PipelineError) as caught:
        run(dirs, tools)

    assert caught.value.step == Step.MUX


def test_iso_that_appears_during_the_copy_is_kept(dirs: tuple[Path, Path, Path]) -> None:
    media, job, output = dirs
    target = output / "iso" / "Filme.iso"

    def appear() -> bool:
        if target.with_name("Filme.iso.part").exists():
            make_file(target, b"other")
        return False

    with pytest.raises(PipelineError) as caught:
        run_pipeline(make_movie(), media_dir=media, job_dir=job, output_dir=output,
                     tools=FakeTools(), report=lambda step, fraction, title: None,
                     should_cancel=appear)  # fmt: skip

    assert caught.value.message == pipeline.ISO_EXISTS
    assert target.read_bytes() == b"other"
    assert not target.with_name("Filme.iso.part").exists()


def test_main_reports_a_frame_scan_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_file(tmp_path / "media" / "Rip" / "Rip.mkv")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    rip = json.loads(MOVIE)
    rip["streams"][0].update(codec_name="mpeg2video", width=720, height=480)
    monkeypatch.setattr(
        pipeline, "run_ffprobe", lambda path: ProbeResult(json=json.dumps(rip), error=None)
    )

    def broken(command: list[str]) -> str:
        raise OSError("no ffprobe")

    monkeypatch.setattr(pipeline, "run_capture", broken)

    assert pipeline.main(["Rip"]) == 1
    assert "quadros" in capsys.readouterr().err


def test_cancel_during_the_copy_removes_the_part_file(dirs: tuple[Path, Path, Path]) -> None:
    media, job, output = dirs
    part = output / "iso" / "Filme.iso.part"

    with pytest.raises(Canceled):
        run_pipeline(make_movie(), media_dir=media, job_dir=job, output_dir=output,
                     tools=FakeTools(), report=lambda step, fraction, title: None,
                     should_cancel=part.exists)  # fmt: skip

    assert not part.exists()
    assert (job / "disc.iso").exists()


def test_subtitles_are_rendered_one_stream_at_a_time(dirs: tuple[Path, Path, Path]) -> None:
    media = dirs[0]
    make_file(media / "Filme" / "Filme.pt.srt", "1\n00:00:01,000 --> 00:00:02,000\nAção\n"
              .encode("cp1252"))  # fmt: skip
    tools = FakeTools()
    subtitles = (
        SubtitleChoice(key="f:Filme.pt.srt", stream_index=None, file="Filme/Filme.pt.srt",
                       language="pt"),
        SubtitleChoice(key="s5", stream_index=5, file=None, language="en"),
    )  # fmt: skip

    run(dirs, tools, subtitles=subtitles, subtitle_map=(0, 1))

    spumux = [c for c in tools.commands if c[0] == "spumux" and "-m" not in c]
    assert [c[2] for c in spumux] == ["0", "1"]
    extract = [c for c in tools.commands if "-c:s" in c]
    assert extract[0][extract[0].index("-map") + 1] == "0:5"
    assert not list(dirs[1].glob("sub*"))  # cleaned after use


def test_empty_external_subtitle_fails_with_its_name(dirs: tuple[Path, Path, Path]) -> None:
    make_file(dirs[0] / "Filme" / "Filme.pt.srt", b"")
    subtitles = (SubtitleChoice(key="f:Filme.pt.srt", stream_index=None,
                                file="Filme/Filme.pt.srt", language="pt"),)  # fmt: skip

    with pytest.raises(PipelineError) as caught:
        run(dirs, FakeTools(), subtitles=subtitles)

    assert caught.value.message == "A legenda Filme.pt.srt está vazia ou inválida."
    assert caught.value.step == Step.SUBTITLES


def test_missing_external_subtitle_fails_with_its_name(dirs: tuple[Path, Path, Path]) -> None:
    subtitles = (SubtitleChoice(key="f:Sumiu.srt", stream_index=None, file="Filme/Sumiu.srt",
                                language="pt"),)  # fmt: skip

    with pytest.raises(PipelineError) as caught:
        run(dirs, FakeTools(), subtitles=subtitles)

    assert caught.value.message == "A legenda Sumiu.srt não foi encontrada."


def test_qa_report_is_returned(dirs: tuple[Path, Path, Path]) -> None:
    result = run(dirs, FakeTools())

    assert result.qa_json is not None
    report = QaReport.model_validate_json(result.qa_json)
    assert report.passed, [c for c in report.checks if not c.ok]
    assert {"size", "vob", "tree", "t1-video", "t1-audio", "t1-chapters", "t1-bitstream",
            "t1-sync", "t1-encode", "t1-decode", "m1-menu", "m1-bitstream"} <= {
        c.name for c in report.checks
    }  # fmt: skip


def test_failed_qa_keeps_the_iso_in_work_and_publishes_nothing(
    dirs: tuple[Path, Path, Path], stream_report: list[StreamReport]
) -> None:
    stream_report[0] = StreamReport(frame_rate_codes={1}, progressive_sequence={0},
                                    aspect_codes={3}, max_gop=12)  # fmt: skip

    with pytest.raises(QaFailed) as caught:
        run(dirs, FakeTools())

    failure = caught.value.report.first_failure
    assert failure is not None and failure.name == "t1-bitstream"
    assert caught.value.step == Step.QA
    assert "O ISO ficou na pasta de trabalho" in caught.value.message
    assert not (dirs[2] / "iso").exists() or not list((dirs[2] / "iso").iterdir())
    assert (dirs[1] / "disc.iso").exists()
    assert not (dirs[1] / "qa.m2v").exists() and not (dirs[1] / "qa-menu.m2v").exists()


def test_decode_errors_fail_the_qa(dirs: tuple[Path, Path, Path]) -> None:
    with pytest.raises(QaFailed) as caught:
        run(dirs, FakeTools(decode_stderr="[mpeg2video @ 0x1] ac-tex damaged\n"))

    failure = caught.value.report.first_failure
    assert failure is not None and failure.name == "t1-decode"


def test_video_seconds_fall_back_to_the_plan(dirs: tuple[Path, Path, Path]) -> None:
    tools = FakeTools()
    original = tools.run

    def run_without_time(command: list[str], **kwargs: object) -> RunResult:
        result = original(command, **kwargs)  # type: ignore[arg-type]
        return RunResult({k: v for k, v in result.progress.items() if k != "out_time_us"},
                         result.stderr)  # fmt: skip

    tools.run = run_without_time  # type: ignore[method-assign]

    assert run(dirs, tools).qa_json is not None


def test_a_4_3_menu_has_no_letterbox_buttons(
    dirs: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    movie = make_movie()
    assert movie.menu is not None
    tools = FakeTools()
    four_three = StreamReport(frame_rate_codes={4}, progressive_sequence={0}, aspect_codes={2},
                              max_gop=12)  # fmt: skip

    def inspect(path: Path) -> StreamReport:
        return four_three if "menu" in path.name else GOOD_STREAM

    monkeypatch.setattr(pipeline, "inspect_stream", inspect)

    run(dirs, tools, movie.model_copy(update={"menu": movie.menu.model_copy(
        update={"aspect": "4:3"})}))  # fmt: skip

    spumux = [c for c in tools.commands if c[0] == "spumux"]
    assert [c[c.index("-s") + 1] for c in spumux] == ["0"]
