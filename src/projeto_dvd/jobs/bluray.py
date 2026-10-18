"""The job of a one-title Blu-ray: video, audio and subtitle files, tsMuxeR, QA, publish.

It shares the runner, the cache, the publish and the error handling of the DVD pipeline; the
steps and the tools are its own. tsMuxeR exits with 0 on discs it knows are broken, so its
output is read for problems, and the QA reads the ISO the way a player library does.
"""

from collections.abc import Callable
from pathlib import Path

from projeto_dvd.authoring.bluray.libs import bd_info, es_sha256, udf_copy, udf_tree
from projeto_dvd.authoring.bluray.meta import BdInputs, bd_meta, tsmuxer_command, tsmuxer_problem
from projeto_dvd.authoring.bluray.qa import (
    coverage_checks,
    coverage_command,
    es_check,
    es_command,
    info_checks,
    tree_checks,
)
from projeto_dvd.authoring.dvd.qa import Check, QaReport, decode_check, size_checks
from projeto_dvd.encode.bd_extract import (
    audio_es_command,
    audio_suffix,
    h264_copy_command,
    normalize_srt,
    sup_command,
)
from projeto_dvd.encode.bd_extract import srt_command as text_srt_command
from projeto_dvd.encode.x264 import x264_pass_command
from projeto_dvd.jobs import cache as jobs_cache
from projeto_dvd.jobs.cache import cache_key, plan_keys
from projeto_dvd.jobs.pipeline import (
    CacheUse,
    PipelineError,
    PipelineResult,
    QaFailed,
    Report,
    Step,
    check_source,
    keep,
    note,
    publish,
    sha256,
    tool_step,
)
from projeto_dvd.jobs.runner import Canceled, RunResult, ToolError, Tools
from projeto_dvd.planner.disc_plan import DiscPlan, TitlePlan

TSMUXER_FAILED = "O tsMuxeR avisou um problema no disco: {line}"
M2TS = "/BDMV/STREAM/00000.m2ts"
Begin = Callable[[Step, int], Callable[[float], None]]


def run_bluray(
    plan: DiscPlan,
    *,
    media_dir: Path,
    job_dir: Path,
    output_dir: Path,
    tools: Tools,
    report: Report,
    should_cancel: Callable[[], bool],
    cache: CacheUse | None = None,
) -> PipelineResult:
    title = plan.titles[0]
    source = media_dir / title.path
    check_source(source, title)
    job_dir.mkdir(parents=True, exist_ok=True)

    def begin(step: Step, number: int = 0) -> Callable[[float], None]:
        if should_cancel():
            raise Canceled
        report(step, 0.0, number)
        return lambda fraction: report(step, fraction, number)

    def checkpoint() -> None:
        if should_cancel():
            raise Canceled

    if cache is not None and not cache.limit_bytes:
        cache = None
    video = _video(plan, source, job_dir, tools, begin, cache)
    delivered = sha256(video)
    inputs = BdInputs(video, _audio(title, source, job_dir, tools, begin),
                      _subtitles(title, source, media_dir, job_dir, tools, begin))  # fmt: skip
    meta = job_dir / "disc.meta"
    meta.write_text(bd_meta(plan, inputs), encoding="utf-8")
    iso, log = job_dir / "disc.iso", job_dir / "tsmuxer.log"
    iso.unlink(missing_ok=True)
    begin(Step.ISO)
    try:
        run = tools.run(tsmuxer_command(meta, iso), stdout=log)
        failed, stderr = False, run.stderr
    except ToolError as error:
        failed, stderr = True, error.stderr
    output = log.read_text(encoding="utf-8", errors="replace") + stderr
    note(job_dir, "tsMuxeR:\n" + output.rstrip())
    problem = tsmuxer_problem(output)
    if failed and problem is None:
        problem = next((line.strip() for line in reversed(output.splitlines()) if line.strip()),
                       "sem mensagem")  # fmt: skip
    if problem:
        if cache is not None:  # the video may be what tsMuxeR refused: encode it again
            jobs_cache.purge(cache.work_dir, plan_keys(plan, cache.ffmpeg))
        raise PipelineError(TSMUXER_FAILED.format(line=problem), Step.ISO)
    for path in (inputs.video, *inputs.audio, *inputs.subtitles):
        path.unlink(missing_ok=True)
    qa_report = _qa(plan, iso, delivered, job_dir, tools, begin(Step.QA))
    if not qa_report.passed:
        raise QaFailed(qa_report)
    iso_path = publish(iso, output_dir, plan, begin(Step.COPY), checkpoint)
    return PipelineResult(iso_path=iso_path, qa_json=qa_report.model_dump_json())


def _video(
    plan: DiscPlan, source: Path, job_dir: Path, tools: Tools, begin: Begin,
    cache: CacheUse | None,
) -> Path:  # fmt: skip
    title = plan.titles[0]
    video = job_dir / "video.h264"
    # A video left by a job that hit the cache is a hard link to it: never write through it.
    video.unlink(missing_ok=True)
    if title.copy_video:
        progress = begin(Step.VIDEO_COPY, 1)
        with tool_step(Step.VIDEO_COPY):
            tools.run(h264_copy_command(source, title.video_index, video),
                      duration=title.duration, on_progress=progress)  # fmt: skip
        return video
    key = cache_key(plan, 1, cache.ffmpeg) if cache else ""
    cached = jobs_cache.lookup(cache.work_dir, key, video) if cache else None
    if cached is not None:
        note(job_dir, "Vídeo reaproveitado do cache.")
        for step in (Step.VIDEO_PASS1, Step.VIDEO_PASS2):
            begin(step, 1)(1.0)
        return video
    pass2 = RunResult({}, "")
    for pass_number, step in ((1, Step.VIDEO_PASS1), (2, Step.VIDEO_PASS2)):
        progress = begin(step, 1)
        with tool_step(step):
            pass2 = tools.run(
                x264_pass_command(source, title, plan.video_kbps, plan.maxrate_kbps,
                                  1 if pass_number == 1 else 2, job_dir / "x264", video),
                duration=title.duration, on_progress=progress,
            )  # fmt: skip
    for log in job_dir.glob("x264*.log*"):
        log.unlink()
    if cache is not None:
        keep(plan, 1, key, video, pass2, job_dir, cache)
    return video


def _audio(
    title: TitlePlan, source: Path, job_dir: Path, tools: Tools, begin: Begin
) -> tuple[Path, ...]:
    progress = begin(Step.AUDIO, 1)
    files = []
    for n, track in enumerate(title.audio, 1):
        out = job_dir / f"a{n}{audio_suffix(track)}"
        with tool_step(Step.AUDIO):
            tools.run(audio_es_command(source, track, title.duration, out))
        files.append(out)
        progress(n / len(title.audio))
    return tuple(files)


def _subtitles(
    title: TitlePlan, source: Path, media_dir: Path, job_dir: Path, tools: Tools, begin: Begin
) -> tuple[Path, ...]:
    if not title.subtitles:
        return ()
    begin(Step.SUBTITLES, 1)
    files = []
    for n, choice in enumerate(title.subtitles, 1):
        if choice.codec == "pgs":
            out = job_dir / f"s{n}.sup"
            with tool_step(Step.SUBTITLES):
                tools.run(sup_command(source, choice.stream_index or 0, out))
        else:
            out = job_dir / f"s{n}.srt"
            if choice.file is not None:
                out.write_bytes(normalize_srt((media_dir / choice.file).read_bytes()))
            else:
                with tool_step(Step.SUBTITLES):
                    tools.run(text_srt_command(source, choice.stream_index or 0, out))
                out.write_bytes(normalize_srt(out.read_bytes()))
        files.append(out)
    return tuple(files)


def _qa(
    plan: DiscPlan, iso: Path, delivered: str, job_dir: Path, tools: Tools,
    progress: Callable[[float], None],
) -> QaReport:  # fmt: skip
    checks = size_checks(iso.stat().st_size, plan)
    m2ts = job_dir / "00000.m2ts"
    try:
        checks += tree_checks(udf_tree(iso))
        checks += info_checks(bd_info(iso), plan)
        udf_copy(iso, M2TS, m2ts)
    except OSError as error:
        checks.append(Check(name="read", label="Disco lido pela libbluray", ok=False,
                            detail=str(error)))  # fmt: skip
    progress(0.3)
    if m2ts.exists():
        with tool_step(Step.QA):
            checks += coverage_checks(tools.capture(coverage_command(m2ts)), plan)
            decode = tools.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(m2ts),
                                "-map", "0:v", "-map", "0:a", "-f", "null", "-"])  # fmt: skip
            checks.append(decode_check(decode.stderr))
            progress(0.8)
            checks.append(es_check(es_sha256(es_command(m2ts)), delivered))
        m2ts.unlink()
    else:
        checks.append(decode_check("o disco não pôde ser lido"))
    return QaReport(checks=tuple(checks), iso_bytes=iso.stat().st_size,
                    estimated_bytes=plan.estimated_bytes)  # fmt: skip
