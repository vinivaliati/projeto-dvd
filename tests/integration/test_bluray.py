"""The Blu-ray job with the real tools: run inside the Docker image (make test-slow)."""

from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.authoring.bluray.libs import bd_info
from projeto_dvd.authoring.bluray.meta import bd_meta
from projeto_dvd.authoring.dvd.qa import QaReport
from projeto_dvd.jobs import bluray
from projeto_dvd.jobs.pipeline import PipelineResult, QaFailed
from projeto_dvd.jobs.runner import ProcessRunner
from projeto_dvd.planner.disc_plan import DiscPlan
from tests.integration import clips

pytestmark = pytest.mark.slow


def generate(media: Path, plan: DiscPlan, tmp_path: Path) -> PipelineResult:
    job = tmp_path / "work" / "jobs" / "1"
    job.mkdir(parents=True, exist_ok=True)
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: False, cwd=job)
    return bluray.run_bluray(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                             tools=runner, report=lambda step, fraction, title: None,
                             should_cancel=lambda: False)  # fmt: skip


def test_a_1080p_movie_becomes_a_blu_ray(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv")
    clips.srt_cp1252(media / "Filme" / "Filme.pt-BR.srt")
    plan = clips.bd_plan_for(media, "Filme", audio=("pt", "en"), subtitles=("pt",),
                             subtitle_on="pt")  # fmt: skip

    iso = generate(media, plan, tmp_path).iso_path

    assert iso == tmp_path / "out" / "iso" / "Filme (BD).iso"
    assert not plan.titles[0].copy_video
    info = bd_info(iso)
    assert [(s.coding_type, s.language) for s in info.audio] == [(0x81, "por"), (0x81, "eng")]
    assert [s.language for s in info.pg] == ["por"]
    assert [round(c) for c in info.chapters] == [0, 4, 8]


def test_a_remux_is_copied_byte_for_byte(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.bd_remux(media / "Remux" / "Remux.mkv")
    plan = clips.bd_plan_for(media, "Remux", audio=("pt",), subtitles=())

    result = generate(media, plan, tmp_path)

    assert plan.titles[0].copy_video
    assert result.qa_json is not None
    checks = {c.name: c.ok for c in QaReport.model_validate_json(result.qa_json).checks}
    assert checks["es"] and checks["coverage"]


def test_delayed_lpcm_is_padded_in_place(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.bd_remux(media / "Pcm" / "Pcm.mkv", delay=0.5, lpcm=True)
    plan = clips.bd_plan_for(media, "Pcm", audio=("pt",), subtitles=(), reencode_rips=True)

    generate(media, plan, tmp_path)  # the coverage check would fail a misaligned track

    track = plan.titles[0].audio[0]
    assert (track.action, track.codec, track.offset) == ("copy", "pcm_s24le", 0.5)


def test_a_disc_missing_a_track_fails_the_qa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv")
    plan = clips.bd_plan_for(media, "Filme", audio=("pt", "en"), subtitles=())

    def without_english(p: DiscPlan, inputs: Any) -> str:
        return "".join(line for line in bd_meta(p, inputs).splitlines(keepends=True)
                       if "lang=eng" not in line)  # fmt: skip

    monkeypatch.setattr(bluray, "bd_meta", without_english)

    with pytest.raises(QaFailed) as error:
        generate(media, plan, tmp_path)

    assert not error.value.report.passed
