"""The DVD pipeline with the real tools: run inside the Docker image (make test-slow)."""

import json
import re
import subprocess
from pathlib import Path

import pytest

from projeto_dvd.authoring.dvd.qa import QaReport
from projeto_dvd.authoring.dvd.subtitles import FONT
from projeto_dvd.jobs import pipeline as pipeline_module
from projeto_dvd.jobs.pipeline import PipelineResult, QaFailed, Step, run_pipeline
from projeto_dvd.jobs.runner import Canceled, ProcessRunner
from projeto_dvd.planner.profiles import PROFILES, DiscProfile
from projeto_dvd.planner.source import VideoMode
from tests.integration import clips

pytestmark = pytest.mark.slow


def generate(media: Path, folder: str, tmp_path: Path, **overrides: object) -> PipelineResult:
    plan = clips.plan_for(media, folder, **overrides)
    job = tmp_path / "work" / "jobs" / "1"
    job.mkdir(parents=True)
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: False, cwd=job)
    result = run_pipeline(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                          tools=runner, report=lambda step, fraction: None,
                          should_cancel=lambda: False)  # fmt: skip
    return result


def dvd_probe(iso: Path) -> dict[str, object]:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "dvdvideo", "-title", "1", "-show_streams",
         "-show_chapters", "-show_format", "-of", "json", str(iso)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    data: dict[str, object] = json.loads(output)
    return data


def test_1080p_movie_becomes_a_dvd_iso(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv")

    iso = generate(media, "Filme", tmp_path, audio=(1, 2), subtitles=(), subtitle_on=None).iso_path

    assert iso == tmp_path / "out" / "iso" / "Filme.iso"
    streams = dvd_probe(iso)["streams"]
    assert isinstance(streams, list)
    video = streams[0]
    assert (video["codec_name"], video["width"], video["height"]) == ("mpeg2video", 720, 480)
    assert video["r_frame_rate"] == "30000/1001"
    assert [s["codec_name"] for s in streams[1:]] == ["ac3", "ac3"]
    leftovers = sorted(p.name for p in (tmp_path / "work" / "jobs" / "1").iterdir())
    assert leftovers == ["dvd.xml", "job.log"]


def test_external_srt_in_windows_1252_becomes_a_dvd_subtitle(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv")
    clips.srt_cp1252(media / "Filme" / "Filme.pt-BR.srt")

    iso = generate(media, "Filme", tmp_path).iso_path

    streams = dvd_probe(iso)["streams"]
    assert isinstance(streams, list)
    subtitles = [s for s in streams if s["codec_type"] == "subtitle"]
    assert [s["codec_name"] for s in subtitles] == ["dvd_subtitle"]
    assert subtitles[0]["tags"]["language"] == "por"
    assert (FONT).exists()


def passed(qa_json: str | None) -> QaReport:
    assert qa_json is not None
    report = QaReport.model_validate_json(qa_json)
    assert report.passed, [c for c in report.checks if not c.ok]
    return report


def test_1080p_movie_passes_the_qa(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv")
    clips.srt_cp1252(media / "Filme" / "Filme.pt-BR.srt")

    result = generate(media, "Filme", tmp_path, audio=(1, 2), subtitle_on="f:Filme.pt-BR.srt")

    names = {check.name for check in passed(result.qa_json).checks}
    assert {"size", "tree", "video", "audio", "subtitles", "chapters", "bitstream", "fields",
            "sync", "decode"} <= names  # fmt: skip
    crop = subprocess.run(
        ["ffmpeg", "-nostdin", "-f", "dvdvideo", "-title", "1", "-i", str(result.iso_path),
         "-vf", "cropdetect=limit=24:round=2", "-frames:v", "60", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr  # fmt: skip
    height = int(crop.rsplit("crop=", 1)[1].split(":")[1])
    assert abs(height - 356) <= 4


def test_dvd_rip_film_is_not_duplicated(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.dvd_rip_film(media / "Rip" / "Rip.mkv")
    source = clips.disc_source(media, "Rip")
    assert source.mode == VideoMode.FILM

    result = generate(media, "Rip", tmp_path)

    passed(result.qa_json)  # includes dup_frames == 0 and the 3:2 field cadence


def test_480i_source_stays_interlaced(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.interlaced_480i(media / "Serie" / "Ep.mkv")
    source = clips.disc_source(media, "Serie")
    assert source.summary.video is not None
    assert source.summary.video.field_order == "tb"
    assert (source.mode, source.top_field_first) == (VideoMode.INTERLACED, True)

    result = generate(media, "Serie", tmp_path)

    report = passed(result.qa_json)
    assert any(c.name == "video" and "4:3" in c.detail for c in report.checks)


def test_estimate_is_close_to_the_real_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv", noisy=True)
    tiny = DiscProfile(key="dvd5", name="Teste", description="teste", sectors=4800)
    monkeypatch.setitem(PROFILES, "dvd5", tiny)

    result = generate(media, "Filme", tmp_path, profile="dvd5", confirm_low=True,
                      subtitles=(), subtitle_on=None)  # fmt: skip

    passed(result.qa_json)
    listing = subprocess.run(["isoinfo", "-l", "-i", str(result.iso_path)],
                             capture_output=True, text=True, check=True).stdout  # fmt: skip
    vobs = sum(int(size) for size in
               re.findall(r"\s(\d+)\s+\w{3}\s+\d+\s+\d{4}\s+\[[^\]]*\]\s+VTS_01_[1-9]\.VOB",
                          listing))  # fmt: skip
    plan = clips.plan_for(media, "Filme", profile="dvd5", confirm_low=True, subtitles=(),
                          subtitle_on=None)  # fmt: skip
    expected = plan.estimated_bytes - tiny.reserve_bytes
    assert vobs > 0
    assert abs(vobs - expected) / expected < 0.03, (vobs, expected)


def test_qa_rejects_a_disc_without_pulldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv")
    monkeypatch.setattr(pipeline_module, "apply_soft_pulldown", lambda path, checkpoint: 0)

    with pytest.raises(QaFailed) as caught:
        generate(media, "Filme", tmp_path, subtitles=(), subtitle_on=None)

    failure = caught.value.report.first_failure
    assert failure is not None and failure.name == "bitstream"
    assert not (tmp_path / "out" / "iso" / "Filme.iso").exists()


def running_ffmpeg() -> list[str]:
    alive = []
    for process in Path("/proc").iterdir():
        try:
            if process.name.isdecimal() and b"ffmpeg" in (process / "cmdline").read_bytes():
                alive.append(process.name)
        except OSError:  # ended in between
            continue
    return alive


def test_cancel_stops_ffmpeg(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv", seconds=60)
    plan = clips.plan_for(media, "Filme")
    job = tmp_path / "work" / "jobs" / "1"
    job.mkdir(parents=True)
    state: dict[str, float] = {}

    def report(step: Step, fraction: float) -> None:
        if step == Step.VIDEO_PASS1 and fraction > 0:
            state["started"] = fraction

    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: "started" in state,
                           cwd=job, poll_seconds=0.1)  # fmt: skip
    with pytest.raises(Canceled):
        run_pipeline(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                     tools=runner, report=report,
                     should_cancel=lambda: "started" in state)  # fmt: skip

    assert running_ffmpeg() == []
