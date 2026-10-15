"""Two-pass MPEG-2 video for NTSC DVD-Video.

Never `-target ntsc-dvd`: it reaches 29.97 by duplicating whole frames (a judder every 4th
frame). Film is encoded at 23.976 and gets soft pulldown flags afterwards (encode/mpeg2.py).
"""

from pathlib import Path
from typing import Literal

from projeto_dvd.planner.dvd_plan import DvdPlan
from projeto_dvd.planner.source import VideoMode

FILM_RATE = "24000/1001"
NTSC_RATE = "30000/1001"
# MP@ML limits: 224 KiB VBV, closed 12-picture GOPs (30 fields with pulldown, below 36).
# +cgop needs scene-cut detection off; non_linear_quant needs qmax <= 28.
CODEC_OPTIONS = [
    "-c:v", "mpeg2video", "-bufsize", "1835k", "-g", "12", "-bf", "2",
    "-sc_threshold", "1000000000", "-dc", "10", "-intra_vlc", "1", "-non_linear_quant", "1",
    "-qmin", "1", "-qmax", "28", "-mbd", "rd", "-trellis", "1", "-cmp", "2", "-subcmp", "2",
]  # fmt: skip
# The -color_* options do not reach the sequence_display_extension; this bitstream filter does.
COLOR_TAGS = "mpeg2_metadata=colour_primaries=6:transfer_characteristics=6:matrix_coefficients=6"


def video_filters(plan: DvdPlan) -> str:
    filters = []
    if plan.mode == VideoMode.HYBRID:
        filters.append("repeatfields")  # hard telecine of the film parts
    if plan.scale:
        filters.append(
            f"scale={plan.width}:{plan.height}:flags=lanczos+accurate_rnd+full_chroma_int"
        )
    if plan.hd_color:
        # After the scale: converting the matrix at 1080p costs ten times more.
        filters.append("colorspace=all=smpte170m:iall=bt709")
    filters.append("format=yuv420p")
    pad_x, pad_y = (720 - plan.width) // 2, (480 - plan.height) // 2
    filters.append(f"pad=720:480:{pad_x}:{pad_y}:black")
    filters.append(f"setsar={'32/27' if plan.aspect == '16:9' else '8/9'}")
    return ",".join(filters)


def video_pass_command(
    plan: DvdPlan, source: Path, job_dir: Path, pass_number: Literal[1, 2]
) -> list[str]:
    film = plan.mode == VideoMode.FILM
    command = [
        "ffmpeg", "-y", "-nostdin", "-i", str(source.absolute()),
        "-map", f"0:{plan.video_index}",
        # Always explicit: without it ffmpeg follows r_frame_rate and duplicates the frames
        # of a soft-telecined DVD rip.
        "-r", FILM_RATE if film else NTSC_RATE, "-fps_mode", "cfr",
        "-vf", video_filters(plan),
        *CODEC_OPTIONS,
        "-b:v", f"{plan.video_kbps}k", "-maxrate", f"{plan.maxrate_kbps}k",
        "-flags", "+cgop" if film else "+cgop+ilme+ildct",
    ]  # fmt: skip
    if not film:
        command += ["-top", "1" if plan.top_field_first else "0"]
    command += [
        "-aspect", plan.aspect, "-bsf:v", COLOR_TAGS, "-an", "-sn", "-dn",
        "-pass", str(pass_number), "-passlogfile", str(job_dir / "pass"),
        "-progress", "pipe:1", "-nostats",
    ]  # fmt: skip
    if pass_number == 1:
        return [*command, "-f", "null", "-"]
    return [*command, "-f", "mpeg2video", str(job_dir / "video.m2v")]
