"""The one video of a disc folder, ready to plan: shared by the web form and the dev command."""

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from projeto_dvd.library.files import VideoFile
from projeto_dvd.library.probe import Summary
from projeto_dvd.library.scan import FolderView, Status
from projeto_dvd.planner.dvd_plan import (
    DvdPlan,
    SubtitleOption,
    build_plan,
    subtitle_options,
    suggest_choices,
)
from projeto_dvd.planner.source import (
    FRAMES_UNREADABLE,
    VideoMode,
    check_video,
    classify_frames,
    frame_scan_command,
    top_field_first_from_frames,
)

SCAN_FIRST = "Escaneie a pasta antes de gerar o disco."
CHANGED = "Os arquivos mudaram desde o último scan. Escaneie de novo."
ONE_VIDEO = (
    "Por enquanto o app gera disco com um vídeo só (discos com vários vídeos chegam com o "
    "menu). Para gerar agora, deixe este vídeo sozinho numa pasta."
)
READ_ERROR = (
    "Não foi possível ler o arquivo. Escaneie de novo; se continuar, o arquivo pode estar "
    "danificado."
)
FRAME_SCAN_TIMEOUT = 120


@dataclass(frozen=True)
class DiscSource:
    folder: str
    video: VideoFile
    summary: Summary
    options: list[SubtitleOption]
    mode: VideoMode
    top_field_first: bool


def folder_reasons(view: FolderView) -> tuple[str, ...]:
    """Folder-level reasons; an empty folder has none (the screen shows no DVD block)."""
    if view.status == Status.EMPTY:
        return ()
    if view.status == Status.NOT_SCANNED:
        return (SCAN_FIRST,)
    if view.status == Status.CHANGED:
        return (CHANGED,)
    if len(view.files) != 1:
        return (ONE_VIDEO,)
    file = view.files[0]
    if file.error is not None:
        return (READ_ERROR,)
    if file.summary is None:
        return (SCAN_FIRST,)
    return check_video(file.summary).reasons


def prepare(
    folder: str, video: VideoFile, summary: Summary, capture: Callable[[list[str]], str]
) -> DiscSource | tuple[str, ...]:
    check = check_video(summary)
    if check.reasons:
        return check.reasons
    mode, top_field_first = check.mode, check.top_field_first
    if check.needs_frame_scan:
        try:
            frames = capture(frame_scan_command(video.absolute, summary.duration or 0.0))
        except (OSError, subprocess.SubprocessError):
            return (FRAMES_UNREADABLE,)
        result = classify_frames(frames)
        if not isinstance(result, VideoMode):  # VideoMode is a str too: test it first
            return (result,)
        mode, top_field_first = result, top_field_first_from_frames(frames)
    assert mode is not None
    options = subtitle_options(summary, video.subtitles)
    return DiscSource(folder, video, summary, options, mode, top_field_first)


def run_capture(command: list[str]) -> str:
    result = subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        timeout=FRAME_SCAN_TIMEOUT, check=True,
    )  # fmt: skip
    return result.stdout


def suggested_plan(source: DiscSource, **choice_overrides: Any) -> DvdPlan:
    duration = source.summary.duration or 0.0
    choices = suggest_choices(source.summary, source.options, duration)
    if choice_overrides:
        choices = choices.model_copy(update=choice_overrides)
    return build_plan(
        folder=source.folder, path=source.video.path, size=source.video.size,
        mtime_ns=source.video.mtime_ns, summary=source.summary, options=source.options,
        choices=choices, mode=source.mode, top_field_first=source.top_field_first,
    )  # fmt: skip
