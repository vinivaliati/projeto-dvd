"""From a DiscPlan to an ISO in the output folder: encode each title, draw the menus, author,
check, publish.

Intermediate files are deleted as soon as the next step succeeds, so the work folder peaks at
about twice the disc size. The ISO reaches the output folder only after the automatic QA.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from sqlmodel import Session

from projeto_dvd.api.formatting import format_size
from projeto_dvd.authoring.dvd.dvdauthor import chapters_on_closed_gops, disc_xml, dvdauthor_command
from projeto_dvd.authoring.dvd.menus import (
    menu_video_command,
    page_file,
    spumux_buttons_xml,
    spumux_menu_command,
)
from projeto_dvd.authoring.dvd.mux import (
    audio_path,
    first_pts_command,
    iso_command,
    mpg_path,
    mux_command,
    parse_first_pts,
)
from projeto_dvd.authoring.dvd.qa import (
    ASPECT_CODES,
    MAX_GOP_FIELDS,
    Check,
    QaReport,
    bitstream_checks,
    copied_checks,
    decode_check,
    decode_command,
    dvd_probe_command,
    encode_check,
    extract_menu_command,
    extract_video_command,
    isoinfo_command,
    menu_checks,
    menu_probe_command,
    prefixed,
    required_tree,
    size_checks,
    stream_checks,
    sync_check,
    sync_probe_command,
    tree_check,
    vob_check,
)
from projeto_dvd.authoring.dvd.subtitles import (
    SubtitleError,
    extract_command,
    prepare_srt,
    spumux_command,
    spumux_xml,
)
from projeto_dvd.config import Settings
from projeto_dvd.db.session import make_engine, migrate
from projeto_dvd.encode.audio import audio_command
from projeto_dvd.encode.mpeg2 import (
    NTSC_RATE_CODE,
    PulldownError,
    StreamReport,
    apply_soft_pulldown,
    inspect_stream,
)
from projeto_dvd.encode.video import copy_command, m2v_path, video_pass_command
from projeto_dvd.jobs import cache as jobs_cache
from projeto_dvd.jobs.cache import cache_key, plan_keys
from projeto_dvd.jobs.files import cannot_write
from projeto_dvd.jobs.runner import Canceled, ProcessRunner, RunResult, ToolError, Tools
from projeto_dvd.library.files import list_disc_folders
from projeto_dvd.library.probe import run_ffprobe
from projeto_dvd.library.scan import scan_folder
from projeto_dvd.menus.layout import letterbox_layout
from projeto_dvd.menus.render import highlight, render_page
from projeto_dvd.planner.disc_plan import DiscPlan, TitlePlan
from projeto_dvd.planner.disc_source import run_capture, suggested_disc_plan
from projeto_dvd.planner.dvd_plan import SubtitleChoice
from projeto_dvd.planner.profiles import medium_of
from projeto_dvd.planner.source import VideoMode

COPY_CHUNK = 16 * 1024 * 1024
COPY_SIZE_SLACK = 1.01  # the copied video may be 1% above the size in the plan
GIB = 1024**3
FIRST_PAGE_PGC = 4  # VMGM menu PGCs 1 to 3 are the dispatchers
SOURCE_CHANGED = (
    "O vídeo {name} mudou ou ficou inacessível depois que o job foi criado (o HD externo foi "
    "desconectado?). Escaneie a pasta e gere de novo."
)
OLD_PLAN = "Job criado numa versão anterior; gere de novo."
NO_SPACE = (
    "Acabou o espaço na pasta de trabalho. Libere espaço ou apague os arquivos temporários de "
    "outros jobs."
)
NO_SPACE_OUTPUT = "Acabou o espaço na pasta de saída ao copiar o ISO."
ISO_EXISTS = (
    "Já existe um ISO com este nome na pasta de saída, e a substituição não foi confirmada."
)
COPY_REFUSED = (
    "O vídeo do rip {name} não segue o padrão do DVD ({reason}). Marque Recodificar os rips e "
    "gere de novo."
)
COPY_GREW = "O rip {name} mudou desde o plano; abra o Montar DVD de novo."
COPY_UNDERFLOW = (
    "O vídeo copiado do rip não cabe no fluxo do DVD com estas faixas. Tire uma faixa de áudio "
    "ou marque Recodificar os rips."
)
ISO_EXISTS_FORM = 'Já existe um ISO com este nome. Marque "Substituir o ISO existente".'


class Step(StrEnum):
    VIDEO_COPY = "video_copy"
    VIDEO_PASS1 = "video_pass1"
    VIDEO_PASS2 = "video_pass2"
    PULLDOWN = "pulldown"
    AUDIO = "audio"
    MUX = "mux"
    SUBTITLES = "subtitles"
    MENUS = "menus"
    AUTHOR = "author"
    ISO = "iso"
    QA = "qa"
    COPY = "copy"


TITLE_STEPS = (Step.VIDEO_COPY, Step.VIDEO_PASS1, Step.VIDEO_PASS2, Step.PULLDOWN, Step.AUDIO,
               Step.MUX, Step.SUBTITLES)  # fmt: skip
DISC_STEPS = (Step.MENUS, Step.AUTHOR, Step.ISO, Step.QA, Step.COPY)
# Phase 6a: a Blu-ray title has no pulldown and no MPEG-2 mux; tsMuxeR writes the ISO.
BD_TITLE_STEPS = (Step.VIDEO_COPY, Step.VIDEO_PASS1, Step.VIDEO_PASS2, Step.AUDIO, Step.SUBTITLES)
BD_DISC_STEPS = (Step.ISO, Step.QA, Step.COPY)
BD_ISO_LABEL = "Montando o Blu-ray (tsMuxeR)"
STEP_LABELS = {
    Step.VIDEO_COPY: "Vídeo copiado da origem",
    Step.VIDEO_PASS1: "Vídeo: 1ª passada (análise)",
    Step.VIDEO_PASS2: "Vídeo: 2ª passada (codificação)",
    Step.PULLDOWN: "Ajuste de quadros para TV",
    Step.AUDIO: "Áudio",
    Step.MUX: "Juntando vídeo e áudio",
    Step.SUBTITLES: "Legendas",
    Step.MENUS: "Desenhando os menus",
    Step.AUTHOR: "Montando a estrutura do DVD",
    Step.ISO: "Criando o ISO",
    Step.QA: "Conferindo o disco",
    Step.COPY: "Copiando o ISO para a pasta de saída",
}
STEP_WEIGHTS = {
    Step.VIDEO_COPY: 0,  # minutes against hours: the copied title barely moves the bar
    Step.VIDEO_PASS1: 35, Step.VIDEO_PASS2: 45, Step.PULLDOWN: 2, Step.AUDIO: 5,
    Step.MUX: 4, Step.SUBTITLES: 2, Step.MENUS: 1, Step.AUTHOR: 2, Step.ISO: 2, Step.QA: 3,
    Step.COPY: 2,
}  # fmt: skip
Steps = tuple[tuple[Step, ...], tuple[Step, ...]]
Report = Callable[[Step, float, int], None]  # (step, fraction, title; 0 for disc steps)


class PipelineError(Exception):
    """A failure with a Portuguese message for the job page."""

    def __init__(self, message: str, step: Step | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.step = step


class QaFailed(PipelineError):
    """The automatic QA rejected the disc; the ISO stays in the work folder."""

    def __init__(self, report: QaReport) -> None:
        failure = report.first_failure
        label = failure.label if failure else "?"
        super().__init__(
            f"A conferência automática reprovou: {label}. O ISO ficou na pasta de trabalho "
            "para inspeção.",
            Step.QA,
        )
        self.report = report


@dataclass(frozen=True)
class PipelineResult:
    iso_path: Path
    qa_json: str | None


@dataclass(frozen=True)
class CacheUse:
    """Where the encoded video is kept and how much of it (0 turns the cache off)."""

    work_dir: Path
    limit_bytes: int
    ffmpeg: str | None


@dataclass(frozen=True)
class TitleResult:
    """What the QA needs from the encode of one title."""

    pass2: RunResult
    mux: RunResult
    sync: Check
    # A copied DVD video: the chapters moved to closed GOPs, the source stream and its hash.
    chapters: tuple[float, ...] | None = None
    source_report: StreamReport | None = None
    sha256: str | None = None


def step_text(step: Step, title: int) -> str:
    """How the job row keeps the step: '2:video_pass2' for title 2, 'iso' for the disc."""
    return f"{title}:{step}" if title else str(step)


def steps_for(plan: DiscPlan) -> Steps:
    """The title steps and the disc steps of the medium of the plan."""
    if medium_of(plan.profile) == "bluray":
        return BD_TITLE_STEPS, BD_DISC_STEPS
    return TITLE_STEPS, DISC_STEPS


def step_label(step: Step, plan: DiscPlan) -> str:
    if step == Step.ISO and medium_of(plan.profile) == "bluray":
        return BD_ISO_LABEL
    return STEP_LABELS[step]


def overall_progress(plan: DiscPlan, step: Step, fraction: float, title: int) -> float:
    """Each title weighs by its duration; the disc steps come after all titles."""
    title_steps, disc_steps = steps_for(plan)
    titles_weight = sum(STEP_WEIGHTS[s] for s in title_steps)
    total_weight = titles_weight + sum(STEP_WEIGHTS[s] for s in disc_steps)
    durations = [t.duration for t in plan.titles]
    total = sum(durations) or 1.0
    if title:
        before = sum(durations[: title - 1]) / total
        share = durations[title - 1] / total
        steps = title_steps[: title_steps.index(step)]
        within = sum(STEP_WEIGHTS[s] for s in steps) + STEP_WEIGHTS[step] * fraction
        done = titles_weight * before + share * within
    else:
        steps = disc_steps[: disc_steps.index(step)]
        done = titles_weight + sum(STEP_WEIGHTS[s] for s in steps) + STEP_WEIGHTS[step] * fraction
    return done / total_weight


def run_pipeline(
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
    menu = plan.menu
    if menu is None:
        raise PipelineError(OLD_PLAN)
    for title in plan.titles:
        check_source(media_dir / title.path, title)
    job_dir.mkdir(parents=True, exist_ok=True)

    def begin(step: Step, title: int = 0) -> Callable[[float], None]:
        if should_cancel():
            raise Canceled
        report(step, 0.0, title)
        return lambda fraction: report(step, fraction, title)

    def checkpoint() -> None:
        if should_cancel():
            raise Canceled

    if cache is not None and not cache.limit_bytes:
        cache = None
    results = [
        _encode_title(plan, number, media_dir, job_dir, tools, begin, checkpoint, cache)
        for number in range(1, len(plan.titles) + 1)
    ]
    progress = begin(Step.MENUS)
    for index in range(len(menu.pages)):
        _render_menu(plan, index, job_dir, tools)
        progress((index + 1) / len(menu.pages))
    begin(Step.AUTHOR)
    xml = job_dir / "dvd.xml"
    moved = {n: r.chapters for n, r in enumerate(results, 1) if r.chapters is not None}
    xml.write_text(disc_xml(plan, job_dir, moved), encoding="utf-8")
    shutil.rmtree(job_dir / "dvd", ignore_errors=True)  # dvdauthor appends to what exists
    with tool_step(Step.AUTHOR):
        author = tools.run(dvdauthor_command(xml))
    vob = vob_check(job_dir / "dvd")
    for number in range(1, len(plan.titles) + 1):
        mpg_path(job_dir, number).unlink()
    for index in range(len(menu.pages)):
        page_file(job_dir, index).unlink()
    begin(Step.ISO)
    with tool_step(Step.ISO):
        tools.run(iso_command(plan, job_dir))
    shutil.rmtree(job_dir / "dvd")
    iso = job_dir / "disc.iso"
    progress = begin(Step.QA)
    with tool_step(Step.QA):
        tree = required_tree(len(plan.titles), menus=True)
        checks = [*size_checks(iso.stat().st_size, plan), vob,
                  tree_check(tools.capture(isoinfo_command(iso)), tree)]  # fmt: skip
        for number, (title, result) in enumerate(zip(plan.titles, results, strict=True), 1):
            checks += prefixed(
                _title_checks(iso, number, title, result, author, job_dir, tools),
                f"t{number}", f"Título {number}",
            )  # fmt: skip
            progress(number / (len(plan.titles) + 1))
        for index in range(len(menu.pages)):
            checks += prefixed(_menu_checks(iso, index, menu.aspect, job_dir, tools),
                               f"m{index + 1}", f"Menu {index + 1}")  # fmt: skip
    qa_report = QaReport(checks=tuple(checks), iso_bytes=iso.stat().st_size,
                         estimated_bytes=plan.estimated_bytes)  # fmt: skip
    if not qa_report.passed:
        raise QaFailed(qa_report)
    iso_path = publish(iso, output_dir, plan, begin(Step.COPY), checkpoint)
    return PipelineResult(iso_path=iso_path, qa_json=qa_report.model_dump_json())


def _encode_title(
    plan: DiscPlan,
    number: int,
    media_dir: Path,
    job_dir: Path,
    tools: Tools,
    begin: Callable[[Step, int], Callable[[float], None]],
    checkpoint: Callable[[], None],
    cache: CacheUse | None,
) -> TitleResult:
    title = plan.titles[number - 1]
    source = media_dir / title.path
    check_source(source, title)
    m2v = m2v_path(job_dir, number)
    # A video left by a job that hit the cache is a hard link to it: never write through it.
    m2v.unlink(missing_ok=True)
    if title.copy_video:
        run, chapters, report, digest = _copy_video(title, number, source, job_dir, tools, begin)
        result = _finish_title(plan, number, source, media_dir, job_dir, tools, begin, run)
        return replace(result, chapters=chapters, source_report=report, sha256=digest)
    key = cache_key(plan, number, cache.ffmpeg) if cache else ""
    cached = jobs_cache.lookup(cache.work_dir, key, m2v) if cache else None
    if cached is not None:
        note(job_dir, f"Título {number}: vídeo reaproveitado do cache.")
        for step in (Step.VIDEO_PASS1, Step.VIDEO_PASS2):
            begin(step, number)(1.0)
        pass2 = cached
    else:
        pass2 = _encode_video(plan, number, source, job_dir, tools, begin, checkpoint)
        if cache is not None:
            keep(plan, number, key, m2v, pass2, job_dir, cache)
    return _finish_title(plan, number, source, media_dir, job_dir, tools, begin, pass2)


def _encode_video(
    plan: DiscPlan,
    number: int,
    source: Path,
    job_dir: Path,
    tools: Tools,
    begin: Callable[[Step, int], Callable[[float], None]],
    checkpoint: Callable[[], None],
) -> RunResult:
    """Both passes and, for film, the soft pulldown."""
    title = plan.titles[number - 1]
    m2v = m2v_path(job_dir, number)
    pass2 = RunResult({}, "")
    for pass_number, step in ((1, Step.VIDEO_PASS1), (2, Step.VIDEO_PASS2)):
        progress = begin(step, number)
        with tool_step(step):
            pass2 = tools.run(
                video_pass_command(plan, number, source, job_dir, 1 if pass_number == 1 else 2),
                duration=title.duration, on_progress=progress,
            )  # fmt: skip
    for log in job_dir.glob("pass-*.log*"):
        log.unlink()
    if title.mode == VideoMode.FILM:
        begin(Step.PULLDOWN, number)
        try:
            apply_soft_pulldown(m2v, checkpoint)
        except PulldownError as error:
            raise PipelineError(str(error), Step.PULLDOWN) from error
    return pass2


def _copy_video(
    title: TitlePlan,
    number: int,
    source: Path,
    job_dir: Path,
    tools: Tools,
    begin: Callable[[Step, int], Callable[[float], None]],
) -> tuple[RunResult, tuple[float, ...], StreamReport, str]:
    """The video of a DVD rip as it is, checked against the standard before anything else."""
    m2v = m2v_path(job_dir, number)
    progress = begin(Step.VIDEO_COPY, number)
    with tool_step(Step.VIDEO_COPY):
        run = tools.run(copy_command(source, title.video_index, m2v), duration=title.duration,
                        on_progress=progress)  # fmt: skip
    report = inspect_stream(m2v)
    reason = _copy_problem(report, title.aspect)
    if reason:
        raise PipelineError(COPY_REFUSED.format(name=source.name, reason=reason), Step.VIDEO_COPY)
    if m2v.stat().st_size > (title.video_bytes or 0) * COPY_SIZE_SLACK:
        raise PipelineError(COPY_GREW.format(name=source.name), Step.VIDEO_COPY)
    chapters, dropped = chapters_on_closed_gops(title.chapters, report.gops)
    for chapter in dropped:
        note(job_dir, f"Título {number}: capítulo em {chapter} s saiu (sem GOP fechado perto).")
    return run, chapters, report, sha256(m2v)


def _copy_problem(report: StreamReport, aspect: str) -> str | None:
    if report.frame_rate_codes != {NTSC_RATE_CODE} or report.progressive_sequence != {0}:
        return "não é NTSC 29,97 entrelaçado"
    if report.aspect_codes != {ASPECT_CODES[aspect]}:
        return "o aspecto muda ou não é o esperado"
    if not report.headers_every_gop:
        return "falta sequence header antes de cada GOP"
    if not report.first_gop_closed:
        return "o primeiro GOP é aberto"
    if report.max_gop_fields > MAX_GOP_FIELDS:
        return f"GOP de {report.max_gop_fields} campos, o limite é {MAX_GOP_FIELDS}"
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(COPY_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def keep(
    plan: DiscPlan, number: int, key: str, m2v: Path, pass2: RunResult, job_dir: Path,
    cache: CacheUse,
) -> None:  # fmt: skip
    """Keep the new video and trim the cache; a cache problem never stops the job."""
    try:
        jobs_cache.store(cache.work_dir, key, m2v, pass2)
        jobs_cache.evict(cache.work_dir, cache.limit_bytes, plan_keys(plan, cache.ffmpeg))
    except OSError as error:
        note(job_dir, f"Título {number}: cache não gravado ({error}).")


def _finish_title(
    plan: DiscPlan,
    number: int,
    source: Path,
    media_dir: Path,
    job_dir: Path,
    tools: Tools,
    begin: Callable[[Step, int], Callable[[float], None]],
    pass2: RunResult,
) -> TitleResult:
    """Audio, mux and subtitles of one title, whatever the video came from."""
    title = plan.titles[number - 1]
    m2v = m2v_path(job_dir, number)
    progress = begin(Step.AUDIO, number)
    for track, audio in enumerate(title.audio, start=1):
        with tool_step(Step.AUDIO):
            tools.run(audio_command(audio, source, audio_path(job_dir, number, track)))
        progress(track / len(title.audio))
    progress = begin(Step.MUX, number)
    movie = mpg_path(job_dir, number)
    with tool_step(Step.MUX):
        first_pts = parse_first_pts(tools.capture(first_pts_command(m2v)))
        mux = tools.run(mux_command(title, job_dir, number, first_pts), duration=title.duration,
                        on_progress=progress)  # fmt: skip
        sync = sync_check(json.loads(tools.capture(sync_probe_command(movie))), title)
    if title.copy_video and "buffer underflow" in mux.stderr:
        raise PipelineError(COPY_UNDERFLOW, Step.MUX)
    m2v.unlink()
    for track in range(1, len(title.audio) + 1):
        audio_path(job_dir, number, track).unlink()
    progress = begin(Step.SUBTITLES, number)
    for index, subtitle in enumerate(title.subtitles):
        _render_subtitle(title, number, subtitle, index, source, media_dir, job_dir, tools)
        progress((index + 1) / len(title.subtitles))
    return TitleResult(pass2=pass2, mux=mux, sync=sync)


def _render_menu(plan: DiscPlan, index: int, job_dir: Path, tools: Tools) -> None:
    """Background as one second of still MPEG-2, then the buttons by spumux (and, on 16:9
    menus, a second button stream for 4:3 TVs that letterbox the menu)."""
    assert plan.menu is not None
    rendered = render_page(plan.menu, index)
    names = ("background", "highlight", "select", "lb-highlight", "lb-select")
    files = {name: job_dir / f"menu{index}.{name}.png" for name in names}
    rendered.background.save(files["background"])
    rendered.highlight.save(files["highlight"])
    rendered.select.save(files["select"])
    layouts = [(rendered.layout, files["highlight"], files["select"])]
    if plan.menu.aspect == "16:9":
        boxed = letterbox_layout(rendered.layout)
        highlight(boxed, plan.menu.accent, select=False).save(files["lb-highlight"])
        highlight(boxed, plan.menu.accent, select=True).save(files["lb-select"])
        layouts.append((boxed, files["lb-highlight"], files["lb-select"]))
    current = job_dir / f"menu{index}.still.mpg"
    with tool_step(Step.MENUS):
        tools.run(menu_video_command(files["background"], plan.menu.aspect, current))
        for stream, (layout, lit, chosen) in enumerate(layouts):
            xml = job_dir / f"menu{index}.{stream}.xml"
            xml.write_text(spumux_buttons_xml(layout, lit, chosen), encoding="utf-8")
            following = job_dir / f"menu{index}.s{stream}.mpg"
            tools.run(spumux_menu_command(xml, stream), stdin=current, stdout=following)
            current.unlink()
            xml.unlink()
            current = following
    os.replace(current, page_file(job_dir, index))
    for path in files.values():
        path.unlink(missing_ok=True)


def _title_checks(
    iso: Path,
    number: int,
    title: TitlePlan,
    result: TitleResult,
    author: RunResult,
    job_dir: Path,
    tools: Tools,
) -> list[Check]:
    probe = json.loads(tools.capture(dvd_probe_command(iso, number)))
    checks = stream_checks(probe, title, _encoded_seconds(result.pass2, title))
    extracted = job_dir / "qa.m2v"
    try:
        tools.run(extract_video_command(iso, extracted, number))
        report = inspect_stream(extracted)
        if result.source_report is not None:  # copied video
            same = sha256(extracted) == result.sha256
            chapters = result.chapters or title.chapters
            checks += bitstream_checks(report, title.aspect)[:1]
            checks += copied_checks(report, result.source_report, same, chapters)
        else:
            checks += bitstream_checks(report, title.aspect)
    finally:
        extracted.unlink(missing_ok=True)
    checks += [result.sync, encode_check(result.pass2, result.mux, author)]
    decode = tools.run(decode_command(iso, number), duration=title.duration)
    checks.append(decode_check(decode.stderr))
    return checks


def _menu_checks(iso: Path, index: int, aspect: str, job_dir: Path, tools: Tools) -> list[Check]:
    pgc = index + FIRST_PAGE_PGC
    checks = menu_checks(json.loads(tools.capture(menu_probe_command(iso, pgc))), aspect)
    extracted = job_dir / "qa-menu.m2v"
    try:
        tools.run(extract_menu_command(iso, extracted, pgc))
        report = inspect_stream(extracted)
    finally:
        extracted.unlink(missing_ok=True)
    return checks + bitstream_checks(report, aspect)


def _encoded_seconds(pass2: RunResult, plan: TitlePlan) -> float:
    """The length of the encoded video, so a longer audio in the source does not fail QA."""
    microseconds = pass2.progress.get("out_time_us", "")
    return int(microseconds) / 1e6 if microseconds.isdecimal() else plan.duration


def _render_subtitle(
    plan: TitlePlan,
    title: int,
    subtitle: SubtitleChoice,
    number: int,
    source: Path,
    media_dir: Path,
    job_dir: Path,
    tools: Tools,
) -> None:
    """Draw one SRT as subpicture stream `number` into the title (spumux, stdin to stdout)."""
    srt = job_dir / f"sub{number}.srt"
    with tool_step(Step.SUBTITLES):
        if subtitle.stream_index is not None:
            tools.run(extract_command(source, subtitle.stream_index, srt))
            name = f"interna {subtitle.stream_index}"
            data = srt.read_bytes()
        else:
            assert subtitle.file is not None
            name = Path(subtitle.file).name
            try:
                data = (media_dir / subtitle.file).read_bytes()
            except OSError as error:
                message = f"A legenda {name} não foi encontrada."
                raise PipelineError(message, Step.SUBTITLES) from error
    try:
        srt.write_text(prepare_srt(data, name), encoding="utf-8")
    except SubtitleError as error:
        raise PipelineError(str(error), Step.SUBTITLES) from error
    xml_file = job_dir / f"sub{number}.xml"
    xml_file.write_text(spumux_xml(srt, plan.aspect), encoding="utf-8")
    movie = mpg_path(job_dir, title)
    rendered = movie.with_suffix(".next.mpg")
    with tool_step(Step.SUBTITLES):
        tools.run(spumux_command(xml_file, number), stdin=movie, stdout=rendered)
    os.replace(rendered, movie)
    srt.unlink()
    xml_file.unlink()


def preflight(
    work_dir: Path,
    output_dir: Path,
    estimated_bytes: int,
    iso_name: str,
    replace: bool,
    cache_on: bool = False,
) -> list[str]:
    """Problems to show on the form before a job is created.

    The work folder holds about twice the disc; with the cache, three times (the cached video
    keeps its blocks while the program streams and the ISO exist).
    """
    errors = []
    for label, folder in (("pasta de trabalho", work_dir), ("pasta de saída", output_dir)):
        if not _writable(folder):
            errors.append(cannot_write(label, folder))
    if errors:
        return errors
    for label, folder, needed in (
        ("pasta de trabalho", work_dir, (3 if cache_on else 2) * estimated_bytes + GIB),
        ("pasta de saída", output_dir, estimated_bytes + 100 * 1024 * 1024),
    ):
        free = shutil.disk_usage(folder).free
        if free < needed:
            errors.append(
                f"Falta espaço na {label}: precisa de {format_size(needed)} livres e há "
                f"{format_size(free)}."
            )
    if (output_dir / "iso" / iso_name).exists() and not replace:
        errors.append(ISO_EXISTS_FORM)
    return errors


def note(job_dir: Path, text: str) -> None:
    """A line of the app in the job log, between the tool outputs."""
    with (job_dir / "job.log").open("a", encoding="utf-8") as log:
        log.write(f"[projeto-dvd] {text}\n")


def check_source(source: Path, plan: TitlePlan) -> None:
    message = SOURCE_CHANGED.format(name=source.name)
    try:
        stat = source.stat()
    except OSError as error:
        raise PipelineError(message) from error
    if (stat.st_size, stat.st_mtime_ns) != (plan.size, plan.mtime_ns):
        raise PipelineError(message)


@contextmanager
def tool_step(step: Step, label: str | None = None) -> Iterator[None]:
    try:
        yield
    except ToolError as error:
        if "No space left" in error.stderr:
            raise PipelineError(NO_SPACE, step) from error
        raise PipelineError(f"Falhou na etapa {label or STEP_LABELS[step]}.", step) from error
    except ValueError as error:  # unreadable tool output (first pts)
        raise PipelineError(f"Falhou na etapa {label or STEP_LABELS[step]}.", step) from error


def publish(
    iso: Path,
    output_dir: Path,
    plan: DiscPlan,
    progress: Callable[[float], None],
    checkpoint: Callable[[], None],
) -> Path:
    """Copy as .part and rename at the end: a half-copied ISO never has the final name."""
    target = output_dir / "iso" / plan.iso_name
    part = target.with_name(target.name + ".part")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not plan.replace_existing:
            raise PipelineError(ISO_EXISTS, Step.COPY)
        total, copied = iso.stat().st_size, 0
        with iso.open("rb") as source, part.open("wb") as copy:
            while chunk := source.read(COPY_CHUNK):
                checkpoint()
                copy.write(chunk)
                copied += len(chunk)
                progress(copied / total)
        if target.exists() and not plan.replace_existing:  # appeared during the copy
            raise PipelineError(ISO_EXISTS, Step.COPY)
        os.replace(part, target)
    except OSError as error:
        part.unlink(missing_ok=True)
        raise PipelineError(NO_SPACE_OUTPUT, Step.COPY) from error
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    iso.unlink()
    return target


def _writable(folder: Path) -> bool:
    try:
        with tempfile.TemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    """Development command: scan a folder and generate its DVD with the suggested choices."""
    parser = argparse.ArgumentParser(
        prog="python -m projeto_dvd.jobs.pipeline",
        description="Generate the DVD ISO of one disc folder with the suggested choices.",
    )
    parser.add_argument("folder", help="disc folder name inside MEDIA_DIR")
    args = parser.parse_args(argv)
    settings = Settings()
    folder = list_disc_folders(settings.media_dir).get(args.folder)
    if folder is None:
        print(f"Pasta não encontrada: {args.folder}", file=sys.stderr)
        return 2
    migrate(settings.database_url)
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        scan_folder(session, settings.media_dir, args.folder, folder, run_ffprobe)
        plan = suggested_disc_plan(session, settings.media_dir, settings.output_dir,
                                   args.folder, folder, run_capture)  # fmt: skip
    engine.dispose()
    if isinstance(plan, tuple):
        print("\n".join(plan), file=sys.stderr)
        return 1
    job_dir = settings.work_dir / "dev" / datetime.now().strftime("%Y%m%d-%H%M%S")
    job_dir.mkdir(parents=True)
    runner = ProcessRunner(log_path=job_dir / "job.log", should_cancel=lambda: False, cwd=job_dir)

    def report(step: Step, fraction: float, title: int) -> None:
        where = f"Título {title}: " if title else ""
        print(f"\r{where}{STEP_LABELS[step]}: {fraction:.0%}   ", end="", flush=True)

    try:
        result = run_pipeline(plan, media_dir=settings.media_dir, job_dir=job_dir,
                              output_dir=settings.output_dir, tools=runner, report=report,
                              should_cancel=lambda: False)  # fmt: skip
    except PipelineError as error:
        print(f"\n{error.message}\nLog: {job_dir / 'job.log'}", file=sys.stderr)
        return 1
    print(f"\nISO: {result.iso_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
