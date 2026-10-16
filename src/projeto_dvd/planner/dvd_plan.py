"""The disc plan: what goes on the DVD and how. Pure: no I/O, no tools."""

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict

from projeto_dvd.library.files import ExternalSubtitle
from projeto_dvd.library.probe import AudioTrack, Summary
from projeto_dvd.planner.calculator import Quality, estimate, suggest_profile
from projeto_dvd.planner.languages import dvd_language
from projeto_dvd.planner.profiles import PROFILES
from projeto_dvd.planner.source import VideoMode, geometry

MAX_AUDIO = 8
MAX_SUBTITLES = 32
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


class Choices(BaseModel):
    """What the Vini picked in the form (or what the app suggests)."""

    model_config = ConfigDict(frozen=True)

    profile: str
    audio: tuple[int, ...]  # stream indices, in source order
    first_audio: int
    subtitles: tuple[str, ...]  # option keys
    subtitle_on: str | None
    chapters: Literal["file", "every"]
    minutes: int
    confirm_low: bool = False
    replace_iso: bool = False


def suggest_choices(
    summary: Summary,
    options: list[SubtitleOption],
    duration: float,
    original_language: str | None = None,
) -> Choices:
    """original_language comes from TMDB when the title is confirmed (ISO 639-1)."""
    picked = _suggest_audio(summary, original_language)
    first = next((t.index for t in summary.audio if t.index in picked and _is_pt(t)), picked[0])
    first_track = next(t for t in summary.audio if t.index == first)
    subtitles = tuple(o.key for o in options if o.supported and o.language == "pt")
    subtitle_on = None
    if not _is_pt(first_track):
        subtitle_on = next((o.key for o in options if o.key in subtitles and not o.forced), None)
    chapters: Literal["file", "every"] = "file" if len(summary.chapters) >= 2 else "every"
    draft = Choices(profile="dvd5", audio=picked, first_audio=first, subtitles=subtitles,
                    subtitle_on=subtitle_on, chapters=chapters, minutes=5)  # fmt: skip
    kbps = audio_kbps(summary, draft)
    profile = suggest_profile(
        [estimate(p, duration, kbps, len(subtitles)) for p in PROFILES.values()]
    )
    return draft.model_copy(update={"profile": profile.key})


def audio_kbps(summary: Summary, choices: Choices) -> list[int]:
    return [audio_output(t).kbps for t in summary.audio if t.index in choices.audio]


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


def validate_choices(
    choices: Choices, summary: Summary, options: list[SubtitleOption]
) -> list[str]:
    errors: list[str] = []
    indices = {track.index for track in summary.audio}
    keys = {option.key for option in options if option.supported}
    profile = PROFILES.get(choices.profile)
    if profile is None:
        errors.append("Escolha um perfil de disco.")
    if not choices.audio:
        errors.append("Escolha ao menos uma faixa de áudio.")
    elif not set(choices.audio) <= indices:
        errors.append("Faixa de áudio inválida.")
    elif choices.first_audio not in choices.audio:
        errors.append("A faixa que toca ao colocar o disco precisa estar marcada.")
    if len(choices.audio) > MAX_AUDIO:
        errors.append(f"O DVD aceita até {MAX_AUDIO} faixas de áudio.")
    if not set(choices.subtitles) <= keys:
        errors.append("Legenda inválida.")
    if len(choices.subtitles) > MAX_SUBTITLES:
        errors.append(f"O DVD aceita até {MAX_SUBTITLES} legendas.")
    if choices.subtitle_on is not None and choices.subtitle_on not in choices.subtitles:
        errors.append("A legenda ligada ao iniciar precisa estar marcada.")
    if choices.chapters == "every" and choices.minutes < 1:
        errors.append("O intervalo dos capítulos precisa ser de 1 minuto ou mais.")
    if profile is not None and summary.duration and not errors:
        result = estimate(profile, summary.duration, audio_kbps(summary, choices),
                          len(choices.subtitles))  # fmt: skip
        if result.quality == Quality.DOES_NOT_FIT:
            errors.append(f"O filme não cabe no {profile.name}.")
        elif result.quality == Quality.LOW and not choices.confirm_low:
            errors.append("Confirme que quer gerar com qualidade baixa.")
    return errors


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


class DvdPlan(BaseModel):
    """Everything the pipeline needs, stored whole in the job."""

    model_config = ConfigDict(frozen=True)

    folder: str
    path: str  # video, relative to the input folder
    video_index: int
    size: int
    mtime_ns: int
    duration: float
    profile: str
    video_kbps: int
    maxrate_kbps: int
    estimated_bytes: int
    mode: VideoMode
    top_field_first: bool
    aspect: Literal["16:9", "4:3"]
    width: int
    height: int
    scale: bool
    hd_color: bool
    audio: tuple[AudioChoice, ...]  # disc order: the one that plays first is first
    subtitles: tuple[SubtitleChoice, ...]  # disc order: the one turned on is first
    subtitle_on: bool
    chapters: tuple[float, ...]
    confirmed_low: bool
    replace_existing: bool
    volume: str
    iso_name: str


def build_plan(
    *,
    folder: str,
    path: str,
    size: int,
    mtime_ns: int,
    summary: Summary,
    options: list[SubtitleOption],
    choices: Choices,
    mode: VideoMode,
    top_field_first: bool,
) -> DvdPlan:
    video = summary.video
    duration = summary.duration
    if video is None or duration is None:
        raise ValueError("source without video or duration")
    profile = PROFILES[choices.profile]
    picked = [t for t in summary.audio if t.index in choices.audio]
    picked.sort(key=lambda t: t.index != choices.first_audio)
    audio = tuple(
        AudioChoice(
            index=t.index,
            language=dvd_language(t.language),
            action=(out := audio_output(t)).action,
            channels=out.channels,
            kbps=out.kbps,
            downmix=out.downmix,
            offset=round(t.start_time - video.start_time, 6),
        )
        for t in picked
    )
    by_key = {option.key: option for option in options}
    keys = [key for key in (o.key for o in options) if key in choices.subtitles]
    keys.sort(key=lambda key: key != choices.subtitle_on)
    directory = PurePosixPath(path).parent
    subtitles = tuple(
        SubtitleChoice(
            key=key,
            stream_index=int(key[1:]) if key.startswith("s") else None,
            file=str(directory / key[2:]) if key.startswith("f:") else None,
            language=by_key[key].language,
        )
        for key in keys
    )
    result = estimate(profile, duration, [a.kbps for a in audio], len(subtitles))
    shape = geometry(video)
    chapters = plan_chapters(summary.chapters, duration, choices.chapters, choices.minutes)
    return DvdPlan(
        folder=folder, path=path, video_index=video.index, size=size, mtime_ns=mtime_ns,
        duration=duration, profile=profile.key, video_kbps=result.video_kbps,
        maxrate_kbps=result.maxrate_kbps, estimated_bytes=result.size_bytes, mode=mode,
        top_field_first=top_field_first, aspect=shape.aspect, width=shape.width,
        height=shape.height, scale=shape.scale, hd_color=video.height > 576, audio=audio,
        subtitles=subtitles, subtitle_on=choices.subtitle_on is not None, chapters=chapters.starts,
        confirmed_low=choices.confirm_low, replace_existing=choices.replace_iso,
        volume=volume_name(folder), iso_name=f"{folder}.iso",
    )  # fmt: skip


def _suggest_audio(summary: Summary, original_language: str | None) -> tuple[int, ...]:
    original = dvd_language(summary.audio[0].language)
    # TMDB knows the original language; use it only if the file has that track (TMDB also
    # has codes like "cn" and "xx").
    tmdb = dvd_language(original_language)
    if tmdb and any(dvd_language(t.language) == tmdb for t in summary.audio):
        original = tmdb
    wanted = {"pt", original} if any(_is_pt(t) for t in summary.audio) else {original}
    best: dict[str | None, AudioTrack] = {}
    for track in summary.audio:
        language = dvd_language(track.language)
        if language not in wanted:
            continue
        current = best.get(language)
        if current is None or (track.channel_count or 0) > (current.channel_count or 0):
            best[language] = track
    picked = sorted(track.index for track in best.values())
    return tuple(picked[:MAX_AUDIO])


def _is_pt(track: AudioTrack) -> bool:
    return dvd_language(track.language) == "pt"


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
