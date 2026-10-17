"""The DVD pipeline with the real tools: run inside the Docker image (make test-slow)."""

import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.authoring.dvd.dvdauthor import disc_xml, dvdauthor_command
from projeto_dvd.authoring.dvd.qa import QaReport
from projeto_dvd.authoring.dvd.subtitles import FONT
from projeto_dvd.encode.mpeg2 import inspect_stream
from projeto_dvd.jobs import pipeline as pipeline_module
from projeto_dvd.jobs.pipeline import CacheUse, PipelineResult, QaFailed, Step, run_pipeline
from projeto_dvd.jobs.runner import Canceled, ProcessRunner
from projeto_dvd.library.probe import run_ffprobe, summarize
from projeto_dvd.menus.layout import letterbox_y
from projeto_dvd.menus.pages import build_pages
from projeto_dvd.planner.calculator import MENU_PAGE_BYTES, menu_bytes
from projeto_dvd.planner.disc_plan import DiscPlan
from projeto_dvd.planner.profiles import PROFILES, DiscProfile
from projeto_dvd.planner.source import VideoMode
from tests.integration import clips, navigation

pytestmark = pytest.mark.slow


def generate(media: Path, folder: str, tmp_path: Path, **overrides: Any) -> PipelineResult:
    plan = clips.plan_for(media, folder, **overrides)
    job = tmp_path / "work" / "jobs" / "1"
    job.mkdir(parents=True)
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: False, cwd=job)
    result = run_pipeline(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                          tools=runner, report=lambda step, fraction, title: None,
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

    iso = generate(media, "Filme", tmp_path, audio=("pt", "en"), subtitles=(),
                   subtitle_on=None).iso_path  # fmt: skip

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

    result = generate(media, "Filme", tmp_path, audio=("pt", "en"), subtitle_on="pt")

    names = {check.name for check in passed(result.qa_json).checks}
    assert {"size", "tree", "t1-video", "t1-audio", "t1-subtitles", "t1-chapters",
            "t1-bitstream", "t1-fields", "t1-sync", "t1-decode", "m1-menu"} <= names  # fmt: skip
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
    source = clips.source_of(media, "Rip")
    assert source.mode == VideoMode.FILM

    result = generate(media, "Rip", tmp_path, reencode_rips=True)

    passed(result.qa_json)  # includes dup_frames == 0 and the 3:2 field cadence


def test_480i_source_stays_interlaced(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.interlaced_480i(media / "Serie" / "Ep.mkv")
    source = clips.source_of(media, "Serie")
    assert source.title.summary.video is not None
    assert source.title.summary.video.field_order == "tb"
    assert (source.mode, source.top_field_first) == (VideoMode.INTERLACED, True)

    result = generate(media, "Serie", tmp_path)

    report = passed(result.qa_json)
    assert any(c.name == "t1-video" and "4:3" in c.detail for c in report.checks)


def test_estimate_is_close_to_the_real_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv", noisy=True)
    # Room for the fixed menu reserve (40 MiB) plus about 8 MB of video.
    tiny = DiscProfile(key="dvd5", name="Teste", description="teste", sectors=26_600)
    monkeypatch.setitem(PROFILES, "dvd5", tiny)

    result = generate(media, "Filme", tmp_path, profile="dvd5", subtitles=(), subtitle_on=None)

    passed(result.qa_json)
    listing = subprocess.run(["isoinfo", "-l", "-i", str(result.iso_path)],
                             capture_output=True, text=True, check=True).stdout  # fmt: skip
    vobs = sum(int(size) for size in
               re.findall(r"\s(\d+)\s+\w{3}\s+\d+\s+\d{4}\s+\[[^\]]*\]\s+VTS_01_[1-9]\.VOB",
                          listing))  # fmt: skip
    plan = clips.plan_for(media, "Filme", profile="dvd5", subtitles=(), subtitle_on=None)
    assert plan.menu is not None
    expected = plan.estimated_bytes - tiny.reserve_bytes - menu_bytes(len(plan.menu.pages))
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
    assert failure is not None and failure.name == "t1-bitstream"
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

    def report(step: Step, fraction: float, title: int) -> None:
        if step == Step.VIDEO_PASS1 and fraction > 0:
            state["started"] = fraction

    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: "started" in state,
                           cwd=job, poll_seconds=0.1)  # fmt: skip
    with pytest.raises(Canceled):
        run_pipeline(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                     tools=runner, report=report,
                     should_cancel=lambda: "started" in state)  # fmt: skip

    assert running_ffmpeg() == []


# Discs with menus


def extract(iso: Path, path: str, target: Path) -> Path:
    """One file of the ISO (isoinfo writes it to stdout)."""
    data = subprocess.run(["isoinfo", "-i", str(iso), "-x", f"{path};1"], capture_output=True,
                          check=True).stdout  # fmt: skip
    target.write_bytes(data)
    return target


def series_disc(tmp_path: Path) -> tuple[PipelineResult, DiscPlan]:
    media = tmp_path / "media"
    folder = clips.series_folder(media)
    plan = clips.plan_for(media, folder, audio=("pt", "en"), subtitles=("pt",))
    job = tmp_path / "work" / "jobs" / "1"
    job.mkdir(parents=True)
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: False, cwd=job)
    result = run_pipeline(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                          tools=runner, report=lambda step, fraction, title: None,
                          should_cancel=lambda: False)  # fmt: skip
    return result, plan


def test_a_series_becomes_a_disc_with_menus(tmp_path: Path) -> None:
    result, plan = series_disc(tmp_path)

    report = passed(result.qa_json)
    names = {check.name for check in report.checks}
    assert plan.menu is not None
    pages = len(plan.menu.pages)
    assert {f"m{n}-menu" for n in range(1, pages + 1)} <= names
    assert {"t1-video", "t2-video", "t3-video"} <= names
    menus = extract(result.iso_path, "/VIDEO_TS/VIDEO_TS.VOB", tmp_path / "menus.vob")
    assert menus.stat().st_size < pages * MENU_PAGE_BYTES
    wide, letterbox = navigation.button_groups(menus)
    assert [letterbox_y(y) for y, _ in wide] == [y for y, _ in letterbox]


def test_the_series_disc_navigates_like_a_remote(tmp_path: Path) -> None:
    result, _ = series_disc(tmp_path)
    nav = navigation.Nav(result.iso_path)

    assert nav.menu_still()[0] == "VMGM" and nav.highlighted() == 1  # inserting opens the menu
    nav.press(1)  # Tocar todos
    nav.playing(1)
    nav.playing(2)  # the next episode starts by itself
    nav.title_key()  # the Title key mid-episode opens the main menu, never the episode again
    assert nav.menu_still()[0] == "VMGM" and nav.highlighted() == 1
    nav.press(3)  # Áudio
    nav.menu_still()
    assert nav.highlighted() == 1  # the option that is on
    nav.press(2)  # Inglês: the check mark moves and the focus stays on it
    nav.menu_still()
    assert nav.highlighted() == 2
    nav.press(3)  # Voltar
    nav.menu_still()
    assert nav.highlighted() == 3  # back on Áudio
    nav.press(2)  # Episódios
    nav.menu_still()
    nav.press(1)
    nav.playing(1)
    assert nav.streams()[0] == 1  # English, the disc choice
    nav.menu_key()  # the Menu key goes back to the main menu
    assert nav.menu_still()[0] == "VMGM" and nav.highlighted() == 1
    nav.press(2)
    nav.menu_still()
    nav.press(3)  # the 4:3 episode has no English: it plays its Portuguese track
    nav.playing(3)
    assert nav.streams()[0] == 0


def test_a_movie_returns_to_its_page_and_button(tmp_path: Path) -> None:
    media = tmp_path / "media"
    for number in range(1, 8):
        clips.episode(media / "Filmes" / f"Filme {number}.mkv", ("por",), seconds=1)
    plan = clips.plan_for(media, "Filmes", kind="movies")
    job = tmp_path / "work" / "jobs" / "1"
    job.mkdir(parents=True)
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: False, cwd=job)
    result = run_pipeline(plan, media_dir=media, job_dir=job, output_dir=tmp_path / "out",
                          tools=runner, report=lambda step, fraction, title: None,
                          should_cancel=lambda: False)  # fmt: skip
    nav = navigation.Nav(result.iso_path)

    nav.menu_still()
    nav.press(1)  # Filmes
    nav.menu_still()
    nav.press(8)  # Próxima (6 movies, then Voltar and Próxima)
    nav.menu_still()
    nav.press(1)  # the 7th movie
    nav.playing(7)
    nav.menu_still()  # it ends and the menu comes back
    assert nav.highlighted() == 1
    nav.press(1)  # still the second movie page: button 1 plays the 7th movie again
    nav.playing(7)


def test_sixty_titles_fit_in_the_dispatcher(tmp_path: Path) -> None:
    """Authoring only: one tiny title stands for all sixty."""
    media = tmp_path / "media"
    clips.episode(media / "Serie" / "Serie.S01E01.mkv", ("por",), seconds=1)
    one = clips.plan_for(media, "Serie")
    job = tmp_path / "job"
    job.mkdir()
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=lambda: False, cwd=job)
    titles = tuple(one.titles[0].model_copy(update={"menu_name": f"{n}. Ep"})
                   for n in range(1, 61))  # fmt: skip
    pages = build_pages("series", [t.menu_name for t in titles], "Serie", None,
                        ("Português",), ())  # fmt: skip
    assert one.menu is not None
    menu = one.menu.model_copy(update={"pages": pages})
    plan = one.model_copy(update={"titles": titles, "menu": menu})
    tiny = job / "tiny.mpg"
    clips.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=720x480:r=30000/1001:d=1", "-f", "lavfi",
                 "-i", "sine=d=1:sample_rate=48000", "-c:v", "mpeg2video", "-c:a", "ac3",
                 "-aspect", "16:9", "-f", "dvd", str(tiny))  # fmt: skip
    for number in range(1, 61):
        os.link(tiny, job / f"title{number}.mpg")
    for index in range(len(pages)):
        pipeline_module._render_menu(plan, index, job, runner)
    xml = job / "dvd.xml"
    xml.write_text(disc_xml(plan, job), encoding="utf-8")

    authored = runner.run(dvdauthor_command(xml))

    assert "ERR:" not in authored.stderr
    assert (job / "dvd" / "VIDEO_TS" / "VTS_60_1.VOB").exists()


# Cache, resume and copied DVD video


def run_with_cache(
    plan: DiscPlan, media: Path, job: Path, work: Path, out: Path,
    should_cancel: Callable[[], bool] = lambda: False,
    report: Callable[[Step, float, int], None] = lambda step, fraction, title: None,
) -> PipelineResult:  # fmt: skip
    job.mkdir(parents=True, exist_ok=True)
    runner = ProcessRunner(log_path=job / "job.log", should_cancel=should_cancel, cwd=job)
    use = CacheUse(work_dir=work, limit_bytes=10**12, ffmpeg="slow-test")
    return run_pipeline(plan, media_dir=media, job_dir=job, output_dir=out, tools=runner,
                        report=report, should_cancel=should_cancel, cache=use)  # fmt: skip


def test_a_second_build_reuses_the_encoded_video(tmp_path: Path) -> None:
    media = tmp_path / "media"
    clips.movie_1080p(media / "Filme" / "Filme.mkv", seconds=6)
    plan = clips.plan_for(media, "Filme", subtitles=(), subtitle_on=None)
    first = run_with_cache(plan, media, tmp_path / "j1", tmp_path / "work", tmp_path / "out")
    first.iso_path.unlink()

    second = run_with_cache(plan, media, tmp_path / "j2", tmp_path / "work", tmp_path / "out")

    log = (tmp_path / "j2" / "job.log").read_text()
    assert "-pass" not in log and "vídeo reaproveitado do cache" in log
    passed(second.qa_json)


def test_a_job_stopped_in_the_second_title_resumes_from_the_cache(tmp_path: Path) -> None:
    media = tmp_path / "media"
    folder = clips.series_folder(media)
    plan = clips.plan_for(media, folder, subtitles=())
    state: dict[str, bool] = {}

    def report(step: Step, fraction: float, title: int) -> None:
        if (step, title) == (Step.VIDEO_PASS1, 2):
            state["stop"] = True

    with pytest.raises(Canceled):
        run_with_cache(plan, media, tmp_path / "job", tmp_path / "work", tmp_path / "out",
                       should_cancel=lambda: "stop" in state, report=report)  # fmt: skip
    state.clear()

    result = run_with_cache(plan, media, tmp_path / "job", tmp_path / "work", tmp_path / "out")

    log = (tmp_path / "job" / "job.log").read_text()
    assert "Título 1: vídeo reaproveitado do cache" in log
    passed(result.qa_json)


@pytest.mark.parametrize("size_tag", [True, False])
def test_a_dvd_rip_is_copied_byte_for_byte(tmp_path: Path, size_tag: bool) -> None:
    media = tmp_path / "media"
    source = clips.dvd_rip_copyable(media / "Rip" / "Rip.mkv", size_tag)
    plan = clips.plan_for(media, "Rip", subtitles=(), subtitle_on=None)
    assert plan.titles[0].copy_video, plan.titles[0]

    result = run_with_cache(plan, media, tmp_path / "job", tmp_path / "work", tmp_path / "out")

    report = passed(result.qa_json)
    assert {"t1-same_video", "t1-gop"} <= {c.name for c in report.checks}
    xml = (tmp_path / "job" / "dvd.xml").read_text()
    found = re.search(r'title1\.mpg" chapters="([^"]+)"', xml)
    assert found is not None
    chapters = [_seconds(text) for text in found.group(1).split(",")]
    closed = [start for start, is_closed in inspect_stream(source).gops if is_closed]
    assert len(chapters) == 3 and chapters[0] == 0
    assert all(any(abs(c - start) < 0.002 for start in closed) for c in chapters)
    assert chapters[1:] != [2.1, 5.0]  # moved from the middle of open GOPs
    disc = framemd5(["-f", "dvdvideo", "-title", "1", "-i", str(result.iso_path)])
    assert disc == framemd5(["-i", str(source)])


def _seconds(text: str) -> float:
    hours, minutes, seconds = text.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def framemd5(args: list[str]) -> list[str]:
    output = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", *args, "-map", "0:v", "-c", "copy", "-f",
         "framemd5", "-"], capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [line.rsplit(",", 1)[1] for line in output.splitlines() if not line.startswith("#")]


def test_the_dvd_header_is_read_from_a_reference_stream(tmp_path: Path) -> None:
    source = clips.dvd_rip_copyable(tmp_path / "Rip" / "Rip.mkv", size_tag=True, seconds=2)
    probe = run_ffprobe(source)
    assert probe.json is not None
    video = summarize(json.loads(probe.json)).video
    assert video is not None and video.dvd_header == (9_800_000, 1_835_008)
