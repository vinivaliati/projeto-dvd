"""What goes on the DVD for one video: audio conversion, subtitles, chapters. Pure."""

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict

from projeto_dvd.library.files import ExternalSubtitle
from projeto_dvd.library.probe import AudioTrack, Summary
from projeto_dvd.planner.languages import dvd_language

MAX_CHAPTERS = 99
MIN_CHAPTER_GAP = 1.0
COPY_MAX_KBPS = 448
TEXT_CODECS = frozenset({"subrip", "mov_text", "text"})
PGS = "Legenda em imagem (PGS): ainda não suportada"
VOBSUB = "Legenda em imagem (VobSub): ainda não suportada"
ASS = "Legenda ASS/SSA: ainda não suportada"
OTHER_SUBTITLE = "Legenda neste formato: ainda não suportada"


@dataclass(frozen=True)
class AudioOutput:
    action: Literal["copy", "ac3"]
    channels: int
    kbps: int
    downmix: int | None  # the -ac value, when the layout has to change


def audio_output(track: AudioTrack) -> AudioOutput:
    """Copy a DVD-compatible AC-3; otherwise convert, never inventing channels."""
    channels = track.channel_count or 2
    bit_rate = track.bit_rate or 0
    if (
        track.codec == "ac3"
        and track.sample_rate == 48000
        and 0 < bit_rate <= COPY_MAX_KBPS * 1000
        and channels <= 6
    ):
        return AudioOutput("copy", channels, bit_rate // 1000, None)
    if channels > 6:
        return AudioOutput("ac3", 6, 448, 6)
    if channels >= 3:
        return AudioOutput("ac3", channels, 448, None)
    if channels == 2:
        return AudioOutput("ac3", 2, 192, 2)
    return AudioOutput("ac3", 1, 96, 1)


@dataclass(frozen=True)
class SubtitleOption:
    key: str  # "s<stream index>" or "f:<external file name>"
    language: str | None  # DVD code ("pt")
    language_tag: str | None  # as found, for the screen
    kind: str
    title: str | None
    forced: bool
    default: bool
    supported: bool
    reason: str | None


def subtitle_options(
    summary: Summary, external: tuple[ExternalSubtitle, ...]
) -> list[SubtitleOption]:
    options = [
        SubtitleOption(
            key=f"s{track.index}",
            language=dvd_language(track.language),
            language_tag=track.language,
            kind=track.kind,
            title=track.title,
            forced=track.forced,
            default=track.default,
            supported=track.codec in TEXT_CODECS,
            reason=None if track.codec in TEXT_CODECS else _subtitle_reason(track.codec),
        )
        for track in summary.subtitles
    ]
    for sub in external:
        suffix = PurePosixPath(sub.name).suffix.lower()
        supported = suffix == ".srt"
        options.append(
            SubtitleOption(
                key=f"f:{sub.name}",
                language=dvd_language(sub.language),
                language_tag=sub.language,
                kind="image" if sub.image else "text",
                title=sub.name,
                forced="forced" in (sub.language or "").lower(),
                default=False,
                supported=supported,
                reason=None if supported else _subtitle_reason(suffix),
            )
        )
    return options


@dataclass(frozen=True)
class ChapterPlan:
    starts: tuple[float, ...]
    minutes: int | None  # the interval used, when automatic
    note: str | None  # shown on the form when the app changed what was asked


def plan_chapters(
    source: tuple[float, ...], duration: float, mode: Literal["file", "every"], minutes: int
) -> ChapterPlan:
    if mode == "file" and len(source) >= 2:
        starts = _clean_starts((0.0, *source), duration)
        if len(starts) <= MAX_CHAPTERS:
            return ChapterPlan(starts, None, None)
        used = _smallest_interval(duration, minutes=1)
        note = (
            f"O arquivo tem {len(source)} capítulos, e o DVD aceita até {MAX_CHAPTERS}. Vão ser "
            f"usados capítulos a cada {used} minutos."
        )
        return ChapterPlan(_every(duration, used), used, note)
    used = _smallest_interval(duration, minutes)
    if used == minutes:
        return ChapterPlan(_every(duration, used), used, None)
    note = f"Com {minutes} minutos passaria de {MAX_CHAPTERS} capítulos; vão ser {used}."
    return ChapterPlan(_every(duration, used), used, note)


def volume_name(folder: str) -> str:
    """ISO 9660 volume label: A-Z, 0-9 and _, up to 32 characters."""
    plain = unicodedata.normalize("NFKD", folder).encode("ascii", "ignore").decode().upper()
    label = re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]", "_", plain)).strip("_")[:32].rstrip("_")
    return label or "DVD"


class AudioChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    language: str | None
    action: Literal["copy", "ac3"]
    channels: int
    kbps: int
    downmix: int | None
    offset: float  # audio start minus video start in the source, seconds


class SubtitleChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    stream_index: int | None
    file: str | None  # path relative to the input folder
    language: str | None


def _subtitle_reason(codec: str) -> str:
    if codec in ("hdmv_pgs_subtitle", ".sup"):
        return PGS
    if codec in ("dvd_subtitle", ".idx"):
        return VOBSUB
    if codec in ("ass", "ssa", ".ass", ".ssa"):
        return ASS
    return OTHER_SUBTITLE


def _clean_starts(starts: tuple[float, ...], duration: float) -> tuple[float, ...]:
    kept: list[float] = []
    for start in sorted(set(starts)):
        if start < 0 or start > duration - MIN_CHAPTER_GAP:
            continue
        if kept and start - kept[-1] < MIN_CHAPTER_GAP:
            continue
        kept.append(start)
    return tuple(kept)


def _every(duration: float, minutes: int) -> tuple[float, ...]:
    count = math.ceil((duration - MIN_CHAPTER_GAP) / (minutes * 60))
    return _clean_starts(tuple(float(i * minutes * 60) for i in range(count)), duration)


def _smallest_interval(duration: float, minutes: int) -> int:
    used = max(1, minutes)
    while len(_every(duration, used)) > MAX_CHAPTERS:
        used += 1
    return used
