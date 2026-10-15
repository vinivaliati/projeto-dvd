"""From a DvdPlan to an ISO in the output folder: encode, mux, author, check, publish.

Intermediate files are deleted as soon as the next step succeeds, so the work folder peaks at
about twice the disc size. The ISO reaches the output folder only after the automatic QA.
"""

import argparse
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from sqlmodel import Session

from projeto_dvd.api.formatting import format_size
from projeto_dvd.authoring.dvd.dvdauthor import dvdauthor_command, dvdauthor_xml
from projeto_dvd.authoring.dvd.mux import (
    audio_path,
    first_pts_command,
    iso_command,
    mux_command,
    parse_first_pts,
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
from projeto_dvd.encode.mpeg2 import PulldownError, apply_soft_pulldown
from projeto_dvd.encode.video import video_pass_command
from projeto_dvd.jobs.runner import Canceled, ProcessRunner, ToolError, Tools
from projeto_dvd.library.files import list_disc_folders
from projeto_dvd.library.probe import run_ffprobe
from projeto_dvd.library.scan import folder_view, scan_folder
from projeto_dvd.planner.disc_source import folder_reasons, prepare, run_capture, suggested_plan
from projeto_dvd.planner.dvd_plan import DvdPlan, SubtitleChoice
from projeto_dvd.planner.source import VideoMode

COPY_CHUNK = 16 * 1024 * 1024
GIB = 1024**3
SOURCE_CHANGED = (
    "O vídeo mudou ou ficou inacessível depois que o job foi criado (o HD externo foi "
    "desconectado?). Escaneie a pasta e gere de novo."
)
NO_SPACE = (
    "Acabou o espaço na pasta de trabalho. Libere espaço ou apague os arquivos temporários de "
    "outros jobs."
)
NO_SPACE_OUTPUT = "Acabou o espaço na pasta de saída ao copiar o ISO."
ISO_EXISTS = (
    "Já existe um ISO com este nome na pasta de saída, e a substituição não foi confirmada."
)
ISO_EXISTS_FORM = 'Já existe um ISO com este nome. Marque "Substituir o ISO existente".'


class Step(StrEnum):
    VIDEO_PASS1 = "video_pass1"
    VIDEO_PASS2 = "video_pass2"
    PULLDOWN = "pulldown"
    AUDIO = "audio"
    SUBTITLES = "subtitles"
    MUX = "mux"
    AUTHOR = "author"
    ISO = "iso"
    QA = "qa"
    COPY = "copy"


STEP_LABELS = {
    Step.VIDEO_PASS1: "Vídeo: 1ª passada (análise)",
    Step.VIDEO_PASS2: "Vídeo: 2ª passada (codificação)",
    Step.PULLDOWN: "Ajuste de quadros para TV",
    Step.AUDIO: "Áudio",
    Step.SUBTITLES: "Legendas",
    Step.MUX: "Juntando vídeo, áudio e legendas",
    Step.AUTHOR: "Montando a estrutura do DVD",
    Step.ISO: "Criando o ISO",
    Step.QA: "Conferindo o disco",
    Step.COPY: "Copiando o ISO para a pasta de saída",
}
STEP_WEIGHTS = {
    Step.VIDEO_PASS1: 35, Step.VIDEO_PASS2: 45, Step.PULLDOWN: 2, Step.AUDIO: 5,
    Step.SUBTITLES: 2, Step.MUX: 4, Step.AUTHOR: 2, Step.ISO: 2, Step.QA: 3, Step.COPY: 2,
}  # fmt: skip
TOTAL_WEIGHT = sum(STEP_WEIGHTS.values())


class PipelineError(Exception):
    """A failure with a Portuguese message for the job page."""

    def __init__(self, message: str, step: Step | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.step = step


@dataclass(frozen=True)
class PipelineResult:
    iso_path: Path
    qa_json: str | None


def overall_progress(step: Step, fraction: float) -> float:
    steps = list(Step)
    done = sum(STEP_WEIGHTS[item] for item in steps[: steps.index(step)])
    return (done + STEP_WEIGHTS[step] * fraction) / TOTAL_WEIGHT


def run_pipeline(
    plan: DvdPlan,
    *,
    media_dir: Path,
    job_dir: Path,
    output_dir: Path,
    tools: Tools,
    report: Callable[[Step, float], None],
    should_cancel: Callable[[], bool],
) -> PipelineResult:
    source = media_dir / plan.path
    _check_source(source, plan)
    job_dir.mkdir(parents=True, exist_ok=True)

    def begin(step: Step) -> Callable[[float], None]:
        if should_cancel():
            raise Canceled
        report(step, 0.0)
        return lambda fraction: report(step, fraction)

    def checkpoint() -> None:
        if should_cancel():
            raise Canceled

    m2v = job_dir / "video.m2v"
    for number, step in ((1, Step.VIDEO_PASS1), (2, Step.VIDEO_PASS2)):
        progress = begin(step)
        with _tool_step(step):
            tools.run(
                video_pass_command(plan, source, job_dir, 1 if number == 1 else 2),
                duration=plan.duration, on_progress=progress,
            )  # fmt: skip
    for log in job_dir.glob("pass-*.log*"):
        log.unlink()
    if plan.mode == VideoMode.FILM:
        begin(Step.PULLDOWN)
        try:
            apply_soft_pulldown(m2v, checkpoint)
        except PulldownError as error:
            raise PipelineError(str(error), Step.PULLDOWN) from error
    progress = begin(Step.AUDIO)
    for number, audio in enumerate(plan.audio, start=1):
        with _tool_step(Step.AUDIO):
            tools.run(audio_command(audio, source, audio_path(job_dir, number)))
        progress(number / len(plan.audio))
    progress = begin(Step.MUX)
    movie = job_dir / "movie.mpg"
    with _tool_step(Step.MUX):
        first_pts = parse_first_pts(tools.capture(first_pts_command(m2v)))
        tools.run(mux_command(plan, job_dir, first_pts), duration=plan.duration,
                  on_progress=progress)  # fmt: skip
    m2v.unlink()
    for number in range(1, len(plan.audio) + 1):
        audio_path(job_dir, number).unlink()
    progress = begin(Step.SUBTITLES)
    for number, subtitle in enumerate(plan.subtitles):
        _render_subtitle(plan, subtitle, number, source, media_dir, job_dir, tools)
        progress((number + 1) / len(plan.subtitles))
    begin(Step.AUTHOR)
    xml = job_dir / "dvd.xml"
    xml.write_text(dvdauthor_xml(plan, job_dir), encoding="utf-8")
    shutil.rmtree(job_dir / "dvd", ignore_errors=True)  # dvdauthor appends to what exists
    with _tool_step(Step.AUTHOR):
        tools.run(dvdauthor_command(xml))
    movie.unlink()
    begin(Step.ISO)
    with _tool_step(Step.ISO):
        tools.run(iso_command(plan, job_dir))
    shutil.rmtree(job_dir / "dvd")
    iso = job_dir / "disc.iso"
    iso_path = _publish(iso, output_dir, plan, begin(Step.COPY), checkpoint)
    return PipelineResult(iso_path=iso_path, qa_json=None)


def _render_subtitle(
    plan: DvdPlan,
    subtitle: SubtitleChoice,
    number: int,
    source: Path,
    media_dir: Path,
    job_dir: Path,
    tools: Tools,
) -> None:
    """Draw one SRT as subpicture stream `number` into movie.mpg (spumux, stdin to stdout)."""
    srt = job_dir / f"sub{number}.srt"
    with _tool_step(Step.SUBTITLES):
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
    movie, rendered = job_dir / "movie.mpg", job_dir / "movie.next.mpg"
    with _tool_step(Step.SUBTITLES):
        tools.run(spumux_command(xml_file, number), stdin=movie, stdout=rendered)
    os.replace(rendered, movie)
    srt.unlink()
    xml_file.unlink()


def preflight(
    work_dir: Path, output_dir: Path, estimated_bytes: int, iso_name: str, replace: bool
) -> list[str]:
    """Problems to show on the form before a job is created."""
    errors = []
    for label, folder in (("pasta de trabalho", work_dir), ("pasta de saída", output_dir)):
        if not _writable(folder):
            errors.append(cannot_write(label, folder))
    if errors:
        return errors
    for label, folder, needed in (
        ("pasta de trabalho", work_dir, 2 * estimated_bytes + GIB),
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


def cannot_write(label: str, folder: Path) -> str:
    return (
        f"Não dá para gravar na {label} ({folder}). Ela pode ter sido criada pelo Docker como "
        "root. Para corrigir, no WSL: sudo chown 1000:1000 <a pasta correspondente do .env>."
    )


def _check_source(source: Path, plan: DvdPlan) -> None:
    try:
        stat = source.stat()
    except OSError as error:
        raise PipelineError(SOURCE_CHANGED) from error
    if (stat.st_size, stat.st_mtime_ns) != (plan.size, plan.mtime_ns):
        raise PipelineError(SOURCE_CHANGED)


@contextmanager
def _tool_step(step: Step) -> Iterator[None]:
    try:
        yield
    except ToolError as error:
        if "No space left" in error.stderr:
            raise PipelineError(NO_SPACE, step) from error
        raise PipelineError(f"Falhou na etapa {STEP_LABELS[step]}.", step) from error
    except ValueError as error:  # unreadable tool output (first pts)
        raise PipelineError(f"Falhou na etapa {STEP_LABELS[step]}.", step) from error


def _publish(
    iso: Path,
    output_dir: Path,
    plan: DvdPlan,
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
        view = folder_view(session, settings.media_dir, args.folder, folder)
    engine.dispose()
    reasons = folder_reasons(view)
    file = view.files[0] if len(view.files) == 1 else None
    if reasons or file is None or file.summary is None:
        print("\n".join(reasons or ("Nada para gerar.",)), file=sys.stderr)
        return 1
    source = prepare(args.folder, file.video, file.summary, run_capture)
    if isinstance(source, tuple):
        print("\n".join(source), file=sys.stderr)
        return 1
    plan = suggested_plan(source, confirm_low=True)
    job_dir = settings.work_dir / "dev" / datetime.now().strftime("%Y%m%d-%H%M%S")
    job_dir.mkdir(parents=True)
    runner = ProcessRunner(log_path=job_dir / "job.log", should_cancel=lambda: False, cwd=job_dir)

    def report(step: Step, fraction: float) -> None:
        print(f"\r{STEP_LABELS[step]}: {fraction:.0%}   ", end="", flush=True)

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
