"""Run ffprobe and turn its JSON into a summary for the library screens."""

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

TIMEOUT_SECONDS = 60
ERROR_LIMIT = 500

# Warning texts shown in the UI (Portuguese).
READ_ERROR = "Não foi possível ler o arquivo"
NO_VIDEO = "Sem faixa de vídeo"
HDR = "HDR (precisa de conversão para SDR)"
DOLBY_VISION_5 = "Dolby Vision perfil 5 (conversão de cor a confirmar)"
ABOVE_1080P = "Acima de 1080p"

HDR_TRANSFERS = frozenset({"smpte2084", "arib-std-b67"})
DOVI_SIDE_DATA = "DOVI configuration record"
TEXT_SUBTITLES = frozenset({"subrip", "ass", "ssa", "mov_text", "webvtt", "text"})
IMAGE_SUBTITLES = frozenset({"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"})

SubtitleKind = Literal["text", "image", "unknown"]


class FfprobeMissingError(Exception):
    """ffprobe is not installed: the whole scan stops instead of marking every file."""


@dataclass(frozen=True)
class ProbeResult:
    json: str | None
    error: str | None


@dataclass(frozen=True)
class Video:
    index: int
    codec: str
    width: int
    height: int
    fps: float | None
    r_frame_rate: Fraction | None
    avg_frame_rate: Fraction | None
    field_order: str | None  # "progressive", "tt", "bb", "tb", "bt" or None
    aspect: float | None
    hdr: bool
    dolby_vision_5: bool
    start_time: float


@dataclass(frozen=True)
class AudioTrack:
    index: int
    language: str | None  # as ffprobe gives it ("por"); None when missing or "und"
    codec: str
    channel_count: int | None
    channel_layout: str | None
    sample_rate: int | None
    bit_rate: int | None
    start_time: float
    title: str | None
    default: bool
    forced: bool


@dataclass(frozen=True)
class SubtitleTrack:
    index: int
    language: str | None
    kind: SubtitleKind
    codec: str
    title: str | None
    default: bool
    forced: bool


@dataclass(frozen=True)
class Summary:
    """Raw values for the planner; the screens translate them (api/formatting.py)."""

    duration: float | None
    video: Video | None
    audio: tuple[AudioTrack, ...]
    subtitles: tuple[SubtitleTrack, ...]
    chapters: tuple[float, ...]  # start times in seconds
    warnings: tuple[str, ...]


def ffprobe_command(path: Path) -> list[str]:
    # Absolute path, so a file named "-something.mkv" is never read as an option.
    return [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(path.absolute()),
    ]


def run_ffprobe(path: Path) -> ProbeResult:
    """Probe one file. ffprobe only reads the headers, so this is fast even for 50 GB files."""
    try:
        result = subprocess.run(
            ffprobe_command(path),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except OSError as error:  # not installed, or not executable
        raise FfprobeMissingError from error
    except subprocess.TimeoutExpired:
        return ProbeResult(json=None, error=f"ffprobe não respondeu em {TIMEOUT_SECONDS} s")
    if result.returncode != 0:
        message = result.stderr.strip() or f"ffprobe terminou com código {result.returncode}"
        # The end: ffprobe prints the reason last ("<file>: Invalid data found ...").
        return ProbeResult(json=None, error=message[-ERROR_LIMIT:])
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError:
        return ProbeResult(json=None, error="ffprobe devolveu um JSON inválido")
    return ProbeResult(json=result.stdout, error=None)


def summarize(data: dict[str, Any]) -> Summary:
    """Summarize ffprobe JSON; missing or odd values become None, never an error."""
    streams: list[dict[str, Any]] = data.get("streams", [])
    video_streams = [
        s
        for s in streams
        if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1
    ]
    video = _video(video_streams[0]) if video_streams else None
    return Summary(
        duration=_float(data.get("format", {}).get("duration")),
        video=video,
        audio=tuple(_audio(s) for s in streams if s.get("codec_type") == "audio"),
        subtitles=tuple(_subtitle(s) for s in streams if s.get("codec_type") == "subtitle"),
        chapters=tuple(_float(c.get("start_time")) or 0.0 for c in data.get("chapters", [])),
        warnings=_warnings(video),
    )


def _video(stream: dict[str, Any]) -> Video:
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    dovi = [
        side
        for side in stream.get("side_data_list", [])
        if side.get("side_data_type") == DOVI_SIDE_DATA
    ]
    r_rate = _fraction(stream.get("r_frame_rate"))
    avg_rate = _fraction(stream.get("avg_frame_rate"))
    rate = avg_rate or r_rate
    return Video(
        index=int(stream.get("index", 0)),
        codec=stream.get("codec_name", "?"),
        width=width,
        height=height,
        fps=float(rate) if rate else None,
        r_frame_rate=r_rate,
        avg_frame_rate=avg_rate,
        field_order=stream.get("field_order"),
        aspect=_aspect(stream, width, height),
        hdr=stream.get("color_transfer") in HDR_TRANSFERS or bool(dovi),
        dolby_vision_5=any(side.get("dv_profile") == 5 for side in dovi),
        start_time=_float(stream.get("start_time")) or 0.0,
    )


def _aspect(stream: dict[str, Any], width: int, height: int) -> float | None:
    display = _ratio(stream.get("display_aspect_ratio"), ":")
    if display is not None:
        return display
    if not width or not height:
        return None
    sample = _ratio(stream.get("sample_aspect_ratio"), ":") or 1.0
    return sample * width / height


def _audio(stream: dict[str, Any]) -> AudioTrack:
    channels = stream.get("channels")
    return AudioTrack(
        index=int(stream.get("index", 0)),
        language=_language(stream),
        codec=stream.get("codec_name", "?"),
        channel_count=channels if isinstance(channels, int) else None,
        channel_layout=stream.get("channel_layout") or None,
        sample_rate=_int(stream.get("sample_rate")),
        bit_rate=_int(stream.get("bit_rate")),
        start_time=_float(stream.get("start_time")) or 0.0,
        title=_tags(stream).get("title"),
        default=_disposition(stream, "default"),
        forced=_disposition(stream, "forced"),
    )


def _subtitle(stream: dict[str, Any]) -> SubtitleTrack:
    codec = stream.get("codec_name", "?")
    kind: SubtitleKind = (
        "text" if codec in TEXT_SUBTITLES else "image" if codec in IMAGE_SUBTITLES else "unknown"
    )
    return SubtitleTrack(
        index=int(stream.get("index", 0)),
        language=_language(stream),
        kind=kind,
        codec=codec,
        title=_tags(stream).get("title"),
        default=_disposition(stream, "default"),
        forced=_disposition(stream, "forced"),
    )


def _warnings(video: Video | None) -> tuple[str, ...]:
    if video is None:
        return (NO_VIDEO,)
    warnings = []
    if video.hdr:
        warnings.append(HDR)
    if video.dolby_vision_5:
        warnings.append(DOLBY_VISION_5)
    if video.width > 1920 or video.height > 1080:
        warnings.append(ABOVE_1080P)
    return tuple(warnings)


def _language(stream: dict[str, Any]) -> str | None:
    language = _tags(stream).get("language")
    return None if not language or language == "und" else language


def _tags(stream: dict[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = stream.get("tags") or {}
    return tags


def _disposition(stream: dict[str, Any], name: str) -> bool:
    return bool(stream.get("disposition", {}).get(name) == 1)


def _ratio(value: str | None, separator: str) -> float | None:
    """'24000/1001' or '16:9' as a float; None for missing, zero or invalid values."""
    numerator, _, denominator = (value or "").partition(separator)
    try:
        top, bottom = float(numerator), float(denominator)
    except ValueError:
        return None
    return top / bottom if top and bottom else None


def _fraction(value: str | None) -> Fraction | None:
    """'24000/1001' as a Fraction; None for missing, zero or invalid values."""
    numerator, _, denominator = (value or "").partition("/")
    try:
        result = Fraction(int(numerator), int(denominator))
    except (ValueError, ZeroDivisionError):
        return None
    return result or None


def _int(value: str | int | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
