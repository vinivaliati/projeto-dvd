"""The tsMuxeR meta file of a one-title Blu-ray, and how to read its output.

tsMuxeR exits with 0 on discs it knows are broken (a TrueHD that will not play, a frame it
resynced), so its output is read for problems as well (all tested on tsMuxeR 2.7.0).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from projeto_dvd.encode.bd_extract import audio_suffix
from projeto_dvd.planner.disc_plan import DiscPlan
from projeto_dvd.planner.languages import ISO_639_2

AUDIO_CODECS = {".ac3": "A_AC3", ".dts": "A_DTS", ".mka": "A_LPCM"}
TO_ISO_639_2 = {short: long for long, short in reversed(ISO_639_2.items())}  # bibliographic
# DejaVu Sans as on the DVD, scaled to the frame (26 px at 480 lines, a 10% margin).
TEXT_STYLE = {1080: (58, 4, 108), 720: (39, 3, 72)}  # font size, border, bottom offset
_PROGRESS = re.compile(r"^(\d+(?:\.\d+)?)% complete")
_PROBLEM = re.compile(r"warning|bad frame|invalid|can't", re.IGNORECASE)


@dataclass(frozen=True)
class BdInputs:
    video: Path
    audio: tuple[Path, ...]  # in the order of the plan
    subtitles: tuple[Path, ...]


def iso_639_2(code: str | None) -> str:
    return TO_ISO_639_2.get(code or "", "und")


def chapters_text(starts: Sequence[float]) -> str:
    return ";".join(_timestamp(start) for start in starts)


def bd_meta(plan: DiscPlan, inputs: BdInputs) -> str:
    """The meta of the only title: video, then the audio in disc order (the first plays
    first), then the subtitles (the one turned on marked default=all)."""
    title = plan.titles[0]
    lines = [
        f'MUXOPT --blu-ray --vbr --label="{plan.volume}" '
        f"--custom-chapters={chapters_text(title.chapters)}",
        f'V_MPEG4/ISO/AVC, "{inputs.video}", fps=23.976',
    ]
    for n, (track, path) in enumerate(zip(title.audio, inputs.audio, strict=True)):
        suffix = audio_suffix(track)
        codec = AUDIO_CODECS[suffix]
        source = ", track=1" if suffix == ".mka" else ""  # LPCM rides in Matroska
        default = ", default" if n == 0 else ""
        lines.append(f'{codec}, "{path}"{source}, lang={iso_639_2(track.language)}{default}')
    # subtitle_on is the position of the language on the disc; this title may lack some.
    on_track = title.subtitle_map[plan.subtitle_on - 1] if plan.subtitle_on else None
    for n, (choice, path) in enumerate(zip(title.subtitles, inputs.subtitles, strict=True)):
        on = ", default=all" if n == on_track else ""
        language = f"lang={iso_639_2(choice.language)}"
        if choice.codec == "pgs":
            lines.append(f'S_HDMV/PGS, "{path}", {language}{on}')
            continue
        size, border, bottom = TEXT_STYLE[title.height]
        lines.append(
            f'S_TEXT/UTF8, "{path}", font-name="DejaVu Sans", font-size={size}, '
            f"font-border={border}, bottom-offset={bottom}, video-width={title.width}, "
            f"video-height={title.height}, fps=23.976, {language}{on}"
        )
    return "\n".join(lines) + "\n"


def tsmuxer_command(meta: Path, iso: Path) -> list[str]:
    return ["tsMuxeR", str(meta), str(iso)]


def tsmuxer_progress(line: str) -> float | None:
    found = _PROGRESS.match(line.strip())
    return float(found.group(1)) / 100 if found else None


def tsmuxer_problem(output: str) -> str | None:
    """The first line where tsMuxeR warns or gives up; None for a clean run."""
    return next((line.strip() for line in output.splitlines() if _PROBLEM.search(line)), None)


def _timestamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours:02d}:{minutes:02d}:{rest // 1000:02d}.{rest % 1000:03d}"
