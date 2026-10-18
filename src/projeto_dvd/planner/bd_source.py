"""When the video of a source goes on a Blu-ray as it is: the copy rule and its header sample.

Only a real Blu-ray remux passes: tsMuxeR accepts a web file (keyint 250, one slice, no HRD)
without a word, but a player may not.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from projeto_dvd.planner.disc import DiscTitle, video_size
from projeto_dvd.planner.disc_plan import DiscChoices
from projeto_dvd.planner.source import FILM_RATE, bd_frame

COPY_PROFILES = frozenset({"High", "Main"})
MAX_LEVEL = 41
MIN_SLICES = 4
MAX_DPB = 4
MAX_GOP_FRAMES = 24  # one second
_FIELD = re.compile(r"(nal_hrd_parameters_present_flag|max_dec_frame_buffering|"
                    r"first_mb_in_slice)\s+[01]+ = (\d+)\s*$")  # fmt: skip


@dataclass(frozen=True)
class HeaderReport:
    hrd: bool
    slices: int  # the fewest slices in a frame of the sample
    max_dec_frame_buffering: int | None


def trace_headers_command(path: Path, video_index: int, seconds: int = 3) -> list[str]:
    """The SPS and slice headers of the first seconds, on stderr."""
    return ["ffmpeg", "-hide_banner", "-nostdin", "-v", "info", "-i", str(path),
            "-map", f"0:{video_index}", "-t", str(seconds), "-c", "copy",
            "-bsf:v", "trace_headers", "-f", "null", "-"]  # fmt: skip


def parse_trace_headers(stderr: str) -> HeaderReport:
    hrd = False
    dpb: int | None = None
    frames: list[int] = []
    for line in stderr.splitlines():
        found = _FIELD.search(line)
        if found is None:
            continue
        name, value = found.group(1), int(found.group(2))
        if name == "nal_hrd_parameters_present_flag":
            hrd = hrd or value == 1
        elif name == "max_dec_frame_buffering":
            dpb = value if dpb is None else max(dpb, value)
        elif value == 0 or not frames:
            frames.append(1)
        else:
            frames[-1] += 1
    return HeaderReport(hrd=hrd, slices=min(frames, default=0), max_dec_frame_buffering=dpb)


def bd_copy_reason(
    title: DiscTitle, choices: DiscChoices, headers: HeaderReport | None, gop_frames: int | None
) -> str | None:
    """None when the video can be copied; otherwise why it is encoded.

    Without the header and GOP samples (the page never runs them) those checks wait for
    "Gerar", which runs them before planning.
    """
    if choices.reencode_rips:
        return "Recodificar marcado"
    video = title.summary.video
    if video is None or video.codec != "h264":
        return "não é H.264"
    if video.profile not in COPY_PROFILES:
        return f"perfil {video.profile or 'desconhecido'}"
    if video.level is None or video.level > MAX_LEVEL:
        return f"level {video.level / 10 if video.level else '?'}"
    if video.pix_fmt != "yuv420p":
        return "10 bits" if "10" in (video.pix_fmt or "") else f"formato {video.pix_fmt}"
    frame = bd_frame(video)
    if (frame is None or frame[:2] != (1920, 1080) or video.height != 1080
            or video.r_frame_rate != FILM_RATE):  # fmt: skip
        return f"{video.width}x{video.height} precisa do quadro inteiro"
    if video_size(title) is None:
        return "tamanho do vídeo desconhecido"
    if headers is not None:
        if not headers.hrd:
            return "sem HRD (não é remux de Blu-ray)"
        if headers.slices < MIN_SLICES:
            return f"{headers.slices} slice por quadro"
        if (headers.max_dec_frame_buffering or 0) > MAX_DPB:
            return f"DPB de {headers.max_dec_frame_buffering} quadros"
    if gop_frames is not None and gop_frames > MAX_GOP_FRAMES:
        return f"GOP de {gop_frames} quadros"
    return None
