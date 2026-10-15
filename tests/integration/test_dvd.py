"""The DVD pipeline with the real tools: run inside the Docker image (make test-slow)."""

import json
import subprocess
from pathlib import Path

import pytest

from projeto_dvd.jobs.pipeline import run_pipeline
from projeto_dvd.jobs.runner import ProcessRunner
from tests.integration import clips

pytestmark = pytest.mark.slow


def generate(media: Path, folder: str, tmp_path: Path, **overrides: object) -> Path:
    plan = clips.plan_for(media, folder, **overrides)
    job = tmp_path / "work" / "jobs" / "1"
    job.mkdir(parents=True)
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: False, cwd=job)
    result = run_pipeline(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                          tools=runner, report=lambda step, fraction: None,
                          should_cancel=lambda: False)  # fmt: skip
    return result.iso_path


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

    iso = generate(media, "Filme", tmp_path, audio=(1, 2), subtitles=(), subtitle_on=None)

    assert iso == tmp_path / "out" / "iso" / "Filme.iso"
    streams = dvd_probe(iso)["streams"]
    assert isinstance(streams, list)
    video = streams[0]
    assert (video["codec_name"], video["width"], video["height"]) == ("mpeg2video", 720, 480)
    assert video["r_frame_rate"] == "30000/1001"
    assert [s["codec_name"] for s in streams[1:]] == ["ac3", "ac3"]
    leftovers = sorted(p.name for p in (tmp_path / "work" / "jobs" / "1").iterdir())
    assert leftovers == ["dvd.xml", "job.log"]
