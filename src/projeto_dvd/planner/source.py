"""Which sources the DVD pipeline accepts, how their frames are encoded, and their geometry."""

import json
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Literal

from projeto_dvd.library.probe import Summary, Video

NO_VIDEO = "O arquivo não tem imagem, só áudio."
NO_AUDIO = "O vídeo não tem áudio."
NO_DURATION = (
    "Não foi possível ler a duração do vídeo. Escaneie de novo; se continuar, o arquivo pode "
    "estar danificado."
)
HDR = "O vídeo está em HDR (HDR10, HLG ou Dolby Vision), e o app ainda não converte HDR para DVD."
ABOVE_1080P = "O vídeo é maior que 1080p (4K?), e o app ainda não converte essa resolução."
VARIABLE_FPS = (
    "O vídeo tem taxa de quadros variável (comum em gravação de celular ou de tela). Ainda não "
    "suportado."
)
PAL = "O vídeo está em 25 quadros por segundo (padrão PAL, europeu). Por enquanto só NTSC."
EXACT_24 = "O vídeo está em 24 quadros por segundo exatos. Por enquanto só 23,976 ou 29,97."
INTERLACED_HD = "O vídeo é entrelaçado em 1080i (gravação de TV). Ainda não suportado."
INTERLACED_OTHER = "O vídeo é entrelaçado fora de 720x480. Ainda não suportado."
PROGRESSIVE_2997 = "O vídeo está em 29,97 quadros por segundo progressivos. Ainda não suportado."
FPS_5994 = "O vídeo está em 59,94 quadros por segundo. Ainda não suportado."
FRAMES_UNREADABLE = (
    "Não foi possível ler os quadros do vídeo. Escaneie de novo; se continuar, o arquivo pode "
    "estar danificado."
)

FILM_RATE = Fraction(24000, 1001)
NTSC_RATE = Fraction(30000, 1001)
SD_WIDTHS = (720, 704)
INTERLACED_ORDERS = frozenset({"tt", "bb", "tb", "bt"})
WINDOW_SECONDS = 20
SIXTEEN_NINE = 16 / 9
FOUR_THREE = 4 / 3


def other_rate(rate: str) -> str:
    return f"Taxa de quadros {rate} ainda não suportada."


class VideoMode(StrEnum):
    FILM = "film"  # 23.976 progressive, soft pulldown after the encode
    INTERLACED = "interlaced"  # 29.97 interlaced (480i only)
    HYBRID = "hybrid"  # DVD rip mixing film and video: repeatfields, then interlaced


@dataclass(frozen=True)
class SourceCheck:
    reasons: tuple[str, ...]
    mode: VideoMode | None  # None when refused or when the frames decide (MPEG-2 SD)
    top_field_first: bool
    needs_frame_scan: bool


def check_video(summary: Summary) -> SourceCheck:
    """Every reason the source cannot become a DVD yet, all at once."""
    video = summary.video
    if video is None:
        return SourceCheck((NO_VIDEO,), None, True, False)
    reasons: list[str] = []
    if not summary.audio:
        reasons.append(NO_AUDIO)
    if summary.duration is None:
        reasons.append(NO_DURATION)
    if video.hdr:
        reasons.append(HDR)
    if video.width > 1920 or video.height > 1080:
        reasons.append(ABOVE_1080P)
    top_field_first = (video.field_order or "t")[0] != "b"
    if _is_dvd_mpeg2(video):
        # The stream rate of a DVD rip lies (soft telecine): the frames decide later.
        return SourceCheck(tuple(reasons), None, top_field_first, not reasons)
    mode, rate_reason = _mode_from_rate(video)
    if rate_reason:
        reasons.append(rate_reason)
    return SourceCheck(tuple(reasons), None if reasons else mode, top_field_first, False)


def frame_scan_command(path: Path, duration: float) -> list[str]:
    """Read ~20 s of frames at 10%, 50% and 90% of the movie."""
    windows = ",".join(f"{duration * share:.3f}%+{WINDOW_SECONDS}" for share in (0.1, 0.5, 0.9))
    return [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", windows,
        "-show_entries", "frame=repeat_pict,interlaced_frame,top_field_first",
        "-of", "json", str(path.absolute()),
    ]  # fmt: skip


def classify_frames(probe_json: str) -> VideoMode | str:
    """Film (3:2 soft telecine), interlaced, or a mix; a str is a refusal text."""
    frames = json.loads(probe_json).get("frames", [])
    if not frames:
        return FRAMES_UNREADABLE
    repeated = sum(1 for frame in frames if frame.get("repeat_pict", 0) > 0)
    interlaced = sum(1 for frame in frames if frame.get("interlaced_frame") == 1)
    if interlaced == 0 and abs(repeated / len(frames) - 0.5) < 0.05:
        return VideoMode.FILM
    if repeated == 0 and interlaced > 0.9 * len(frames):
        return VideoMode.INTERLACED
    if repeated == 0 and interlaced == 0:
        return PROGRESSIVE_2997
    return VideoMode.HYBRID


def top_field_first_from_frames(probe_json: str) -> bool:
    frames = json.loads(probe_json).get("frames", [])
    top = sum(1 for frame in frames if frame.get("top_field_first") == 1)
    return top * 2 >= len(frames)


@dataclass(frozen=True)
class Geometry:
    aspect: Literal["16:9", "4:3"]
    width: int  # active picture inside the 720x480 frame
    height: int
    scale: bool  # False when the source already is the active picture (DVD rips)


def geometry(video: Video) -> Geometry:
    """Letterbox or pillarbox inside a 16:9 or 4:3 frame, keeping the display aspect."""
    dar = video.aspect or (video.width / video.height)
    aspect: Literal["16:9", "4:3"] = "16:9" if dar >= 1.5 else "4:3"
    target = SIXTEEN_NINE if aspect == "16:9" else FOUR_THREE
    if video.height == 480 and video.width in SD_WIDTHS and abs(dar - target) < 0.02:
        return Geometry(aspect, video.width, 480, scale=False)
    if dar >= target:
        height = min(480, _multiple(480 * target / dar, 4))
        return Geometry(aspect, 720, height, scale=True)
    return Geometry(aspect, min(720, _multiple(720 * dar / target, 2)), 480, scale=True)


def _is_dvd_mpeg2(video: Video) -> bool:
    return video.codec == "mpeg2video" and video.height == 480 and video.width in SD_WIDTHS


def _mode_from_rate(video: Video) -> tuple[VideoMode | None, str | None]:
    r_rate, avg_rate = video.r_frame_rate, video.avg_frame_rate
    rate = r_rate or avg_rate
    if rate is None:
        return None, other_rate("?")
    if r_rate and avg_rate and abs(r_rate - avg_rate) / r_rate > Fraction(1, 1000):
        return None, VARIABLE_FPS
    interlaced = video.field_order in INTERLACED_ORDERS
    if rate == FILM_RATE and not interlaced:
        return VideoMode.FILM, None
    if rate in (25, 50):
        return None, PAL
    if rate == 24:
        return None, EXACT_24
    if rate == NTSC_RATE and interlaced:
        if video.height > 480:
            return None, INTERLACED_HD
        if video.width not in SD_WIDTHS:
            return None, INTERLACED_OTHER
        return VideoMode.INTERLACED, None
    if rate == NTSC_RATE:
        return None, PROGRESSIVE_2997
    if rate == 2 * NTSC_RATE:
        return None, FPS_5994
    return None, other_rate(_rate_text(rate))


def _rate_text(rate: Fraction) -> str:
    return f"{float(rate):.3f}".rstrip("0").rstrip(".").replace(".", ",")


def _multiple(value: float, step: int) -> int:
    return max(step, round(value / step) * step)
