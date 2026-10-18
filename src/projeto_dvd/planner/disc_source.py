"""The disc of a folder as the screens and the job see it: what blocks it, the titles ready to
encode and the suggested plan (shared by the web page and the dev command)."""

import subprocess
from collections.abc import Callable
from datetime import date
from pathlib import Path

from PIL import Image
from sqlmodel import Session

from projeto_dvd.library.scan import FolderView, Status, folder_view
from projeto_dvd.menus.theme import available_backdrops, backdrop_path
from projeto_dvd.metadata.curation import confirmed_infos
from projeto_dvd.planner.bd_source import (
    HeaderReport,
    parse_trace_headers,
    trace_headers_command,
)
from projeto_dvd.planner.calculator import suggest_profile
from projeto_dvd.planner.disc import DiscTitle, disc_titles, suggest_choices
from projeto_dvd.planner.disc_build import (
    TitleSource,
    build_disc_plan,
    disc_errors,
    disc_estimates,
    menu_plan,
    profile_for,
)
from projeto_dvd.planner.disc_plan import DiscChoices, DiscPlan, MenuPlan
from projeto_dvd.planner.profiles import PROFILES, Medium
from projeto_dvd.planner.source import (
    FRAMES_UNREADABLE,
    VideoMode,
    check_video,
    classify_frames,
    frame_scan_command,
    max_gop_fields,
    top_field_first_from_frames,
)

SCAN_FIRST = "Escaneie a pasta antes de gerar o disco."
CHANGED = "Os arquivos mudaram desde o último scan. Escaneie de novo."
READ_ERROR = (
    "não foi possível ler o arquivo. Escaneie de novo; se continuar, o arquivo pode estar "
    "danificado."
)
FRAME_SCAN_TIMEOUT = 120
Capture = Callable[[list[str]], str]


def folder_reasons(view: FolderView) -> tuple[str, ...]:
    """What blocks the disc; an empty folder has none (the screen shows no DVD block)."""
    if view.status == Status.EMPTY:
        return ()
    if view.status == Status.NOT_SCANNED:
        return (SCAN_FIRST,)
    if view.status == Status.CHANGED:
        return (CHANGED,)
    reasons: list[str] = []
    for file in view.files:
        name = file.video.path.split("/", 1)[1]
        if file.error is not None:
            reasons.append(f"{name}: {READ_ERROR}")
        elif file.summary is None:
            reasons.append(SCAN_FIRST)
        else:
            reasons += [f"{name}: {reason}" for reason in check_video(file.summary).reasons]
    return tuple(dict.fromkeys(reasons))


def load_disc(
    session: Session, media_dir: Path, name: str, folder: Path
) -> tuple[FolderView, tuple[DiscTitle, ...]]:
    view = folder_view(session, media_dir, name, folder)
    infos = confirmed_infos(session, name)
    return view, disc_titles(view, infos, date.today().year + 1)


def suggestion(titles: tuple[DiscTitle, ...], folder: str) -> DiscChoices:
    return suggest_choices(titles, folder, profile_for(titles, folder))


def prepare_title(
    title: DiscTitle,
    capture: Capture,
    medium: Medium = "dvd",
    trace: Capture | None = None,
) -> TitleSource | tuple[str, ...]:
    """The video mode, with the frame scan of MPEG-2 rips (up to 2 minutes each).

    A Blu-ray copy (``trace`` given) first samples the SPS and slice headers and the GOPs; a
    sample that cannot be read just means the video is encoded.
    """
    check = check_video(title.summary, medium)
    if check.reasons:
        return check.reasons
    if medium == "bluray":
        if trace is None:
            return TitleSource(title, VideoMode.FILM, True)
        video = title.summary.video
        assert video is not None
        try:
            headers = parse_trace_headers(trace(trace_headers_command(title.video.absolute,
                                                                      video.index)))  # fmt: skip
            frames = capture(frame_scan_command(title.video.absolute, title.summary.duration or 0))
            gop = max_gop_fields(frames) // 2  # progressive: two fields a frame
        except (OSError, subprocess.SubprocessError, ValueError):
            headers, gop = HeaderReport(hrd=False, slices=0, max_dec_frame_buffering=None), None
        return TitleSource(title, VideoMode.FILM, True, headers=headers, gop_frames=gop)
    mode, top_field_first = check.mode, check.top_field_first
    if check.needs_frame_scan:
        try:
            frames = capture(frame_scan_command(title.video.absolute, title.summary.duration or 0))
        except (OSError, subprocess.SubprocessError):
            return (FRAMES_UNREADABLE,)
        result = classify_frames(frames)
        if not isinstance(result, VideoMode):  # VideoMode is a str too: test it first
            return (result,)
        mode, top_field_first = result, top_field_first_from_frames(frames)
        return TitleSource(title, mode, top_field_first, max_gop_fields(frames))
    assert mode is not None
    return TitleSource(title, mode, top_field_first)


def run_trace(command: list[str]) -> str:
    """stderr of a command: trace_headers prints there."""
    result = subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        timeout=FRAME_SCAN_TIMEOUT, check=True,
    )  # fmt: skip
    return result.stderr


def run_capture(command: list[str]) -> str:
    result = subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        timeout=FRAME_SCAN_TIMEOUT, check=True,
    )  # fmt: skip
    return result.stdout


def theme_image(
    choices: DiscChoices, folder: str, output_dir: Path
) -> tuple[Path | None, Image.Image | None]:
    """The chosen backdrop and its picture; one that cannot be read counts as none."""
    name = choices.theme.backdrop
    if name is None or name not in available_backdrops(output_dir, folder):
        return None, None
    path = backdrop_path(output_dir, folder, name)
    try:
        with Image.open(path) as opened:
            return path, opened.convert("RGB")
    except OSError:
        return None, None


def disc_menu(
    choices: DiscChoices, titles: tuple[DiscTitle, ...], folder: str, output_dir: Path
) -> MenuPlan:
    path, image = theme_image(choices, folder, output_dir)
    return menu_plan(choices, titles, folder, path, image)


def suggested_disc_plan(
    session: Session, media_dir: Path, output_dir: Path, name: str, folder: Path,
    capture: Capture, medium: Medium = "dvd",
) -> DiscPlan | tuple[str, ...]:  # fmt: skip
    """The disc with every suggestion taken and the low quality accepted (dev command, tests)."""
    view, titles = load_disc(session, media_dir, name, folder)
    reasons = folder_reasons(view)
    if reasons or not titles:
        return reasons or ("Nada para gerar.",)
    choices = suggestion(titles, name)
    if PROFILES[choices.profile].medium != medium:
        estimates = [e for e in disc_estimates(choices, titles, name)
                     if e.profile.medium == medium]  # fmt: skip
        choices = choices.model_copy(update={"profile": suggest_profile(estimates).key})
    backdrops = available_backdrops(output_dir, name)
    if backdrops:
        theme = choices.theme.model_copy(update={"backdrop": backdrops[0]})
        choices = choices.model_copy(update={"theme": theme})
    trace = run_trace if medium == "bluray" else None
    sources = [prepare_title(title, capture, medium, trace) for title in titles]
    problems = [reason for s in sources if isinstance(s, tuple) for reason in s]
    if problems:
        return tuple(problems)
    estimate = next(e for e in disc_estimates(choices, titles, name)
                    if e.profile is PROFILES[choices.profile])  # fmt: skip
    errors = disc_errors(choices, titles, estimate, confirm_low=True)
    if errors:
        return tuple(errors)
    menu = disc_menu(choices, titles, name, output_dir) if medium == "dvd" else None
    ready = [s for s in sources if isinstance(s, TitleSource)]
    return build_disc_plan(name, ready, choices, menu, confirm_low=True, replace_iso=True)
