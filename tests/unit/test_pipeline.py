import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from projeto_dvd.encode.mpeg2 import PulldownError
from projeto_dvd.jobs import pipeline
from projeto_dvd.jobs.pipeline import (
    PipelineError,
    Step,
    overall_progress,
    preflight,
    run_pipeline,
)
from projeto_dvd.jobs.runner import Canceled, RunResult, ToolError
from projeto_dvd.library.probe import ProbeResult
from projeto_dvd.planner.dvd_plan import DvdPlan
from projeto_dvd.planner.source import VideoMode
from tests.plans import make_plan
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


class FakeTools:
    """Records commands; creates the output file of each; can fail at one tool."""

    def __init__(self, fail_at: str | None = None, stderr: str = "") -> None:
        self.commands: list[list[str]] = []
        self.fail_at = fail_at
        self.stderr = stderr

    def run(self, command: list[str], *, duration: float | None = None,
            on_progress: Callable[[float], None] | None = None, stdin: Path | None = None,
            stdout: Path | None = None) -> RunResult:  # fmt: skip
        self.commands.append(command)
        if self.fail_at and self.fail_at in " ".join(command):
            raise ToolError(command[0], 1, self.stderr)
        if on_progress:
            on_progress(1.0)
        if stdout is not None:
            make_file(stdout, b"spu")
        elif command[0] == "dvdauthor":
            dvd = Path(command[2]).parent / "dvd" / "VIDEO_TS"
            make_file(dvd / "VTS_01_1.VOB", b"v" * 100)
        elif command[-1] != "-":
            output = Path(command[-1] if command[0] != "genisoimage" else command[-2])
            make_file(output, b"\x00\x00\x01\xb3" + bytes([0x2D, 0x01, 0xE0, 0x31]) + b"\xff" * 8)
        return RunResult({"dup_frames": "0", "drop_frames": "0", "progress": "end"}, "")

    def capture(self, command: list[str]) -> str:
        self.commands.append(command)
        return "0.055556\n"


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    media, job, output = tmp_path / "media", tmp_path / "work" / "jobs" / "1", tmp_path / "out"
    source = make_file(media / "Filme" / "Filme.mkv", b"x" * 100)
    os.utime(source, ns=(200, 200))
    return media, job, output


def run(
    dirs: tuple[Path, Path, Path], tools: FakeTools, **plan_fields: object
) -> pipeline.PipelineResult:
    media, job, output = dirs
    return run_pipeline(make_plan(**plan_fields), media_dir=media, job_dir=job, output_dir=output,
                        tools=tools, report=lambda step, fraction: None,
                        should_cancel=lambda: False)  # fmt: skip


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
    assert tools_used == ["ffmpeg", "ffmpeg", "ffmpeg", "ffmpeg", "ffprobe", "ffmpeg",
                          "dvdauthor", "genisoimage"]  # fmt: skip
    assert no_pulldown == [dirs[1] / "video.m2v"]
    assert result.iso_path == dirs[2] / "iso" / "Filme.iso"
    assert result.iso_path.exists()
    job = dirs[1]
    for leftover in ("video.m2v", "audio1.ac3", "audio2.ac3", "movie.mpg", "dvd", "disc.iso"):
        assert not (job / leftover).exists(), leftover
    assert (job / "dvd.xml").exists()


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

    assert caught.value.message == pipeline.SOURCE_CHANGED
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
        run_pipeline(make_plan(), media_dir=media, job_dir=job, output_dir=output, tools=tools,
                     report=lambda s, f: None, should_cancel=lambda: next(calls, True))  # fmt: skip

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

    result = run(dirs, FakeTools(), replace_existing=True)

    assert result.iso_path.read_bytes() != b"old"


def test_failed_copy_removes_the_part_file(
    dirs: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_replace(source: object, target: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", broken_replace)

    with pytest.raises(PipelineError):
        run(dirs, FakeTools())

    assert not (dirs[2] / "iso" / "Filme.iso.part").exists()
    assert (dirs[1] / "disc.iso").exists()


def test_overall_progress_uses_the_weights() -> None:
    assert overall_progress(Step.VIDEO_PASS1, 0.0) == 0.0
    assert overall_progress(Step.VIDEO_PASS2, 0.0) == pytest.approx(35 / 102)
    assert overall_progress(Step.COPY, 1.0) == 1.0


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

    assert errors == [pipeline.cannot_write("pasta de trabalho", tmp_path / "missing")]


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
    assert "vídeo só" in capsys.readouterr().err


def test_main_generates_with_the_suggested_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_file(tmp_path / "media" / "Filme" / "Filme.mkv")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    monkeypatch.setattr(pipeline, "run_ffprobe", lambda path: ProbeResult(json=MOVIE, error=None))
    seen: list[DvdPlan] = []

    def fake_run(plan: DvdPlan, **kwargs: object) -> pipeline.PipelineResult:
        seen.append(plan)
        kwargs["report"](Step.VIDEO_PASS1, 0.5)  # type: ignore[operator]
        return pipeline.PipelineResult(
            iso_path=tmp_path / "out" / "iso" / "Filme.iso", qa_json=None
        )

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run)

    assert pipeline.main(["Filme"]) == 0
    assert seen[0].folder == "Filme"
    assert "Filme.iso" in capsys.readouterr().out


def test_main_reports_a_pipeline_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    make_file(tmp_path / "media" / "Filme" / "Filme.mkv")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    monkeypatch.setattr(pipeline, "run_ffprobe", lambda path: ProbeResult(json=MOVIE, error=None))

    def failing(plan: DvdPlan, **kwargs: object) -> pipeline.PipelineResult:
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

    assert caught.value.message == pipeline.SOURCE_CHANGED


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
        run_pipeline(make_plan(), media_dir=media, job_dir=job, output_dir=output,
                     tools=FakeTools(), report=lambda step, fraction: None,
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
        run_pipeline(make_plan(), media_dir=media, job_dir=job, output_dir=output,
                     tools=FakeTools(), report=lambda step, fraction: None,
                     should_cancel=part.exists)  # fmt: skip

    assert not part.exists()
    assert (job / "disc.iso").exists()
