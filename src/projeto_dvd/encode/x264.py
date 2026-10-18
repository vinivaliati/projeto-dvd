"""The H.264 video of a Blu-ray: x264 in Blu-ray mode, two passes (parameters tested on the
image's ffmpeg 7.1, libx264 164 and tsMuxeR 2.7.0)."""

from pathlib import Path
from typing import Literal

from projeto_dvd.planner.disc_plan import TitlePlan

# The VBV goes in -maxrate/-bufsize only: repeated inside -x264-params the two fight ("VBV
# parameters cannot be changed when NAL HRD is in use"). Closed GOPs, like the DVD.
X264_PARAMS = (
    "bluray-compat=1:keyint=24:min-keyint=1:slices=4:b-pyramid=strict:open-gop=0:"
    "nal-hrd=vbr:aud=1:colorprim=bt709:transfer=bt709:colormatrix=bt709"
)
BUFSIZE_KBPS = 30_000


def x264_pass_command(
    source: Path,
    title: TitlePlan,
    target_kbps: int,
    maxrate_kbps: int,
    pass_number: Literal[1, 2],
    passlog: Path,
    out: Path,
) -> list[str]:
    command = [
        "ffmpeg", "-y", "-nostdin", "-i", str(source), "-map", f"0:{title.video_index}",
        "-r", "24000/1001", "-fps_mode", "cfr", "-vf", frame_filter(title),
        "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-level", "4.1",
        # Always 8 bits: a 10-bit source would come out High 10, which a Blu-ray refuses.
        "-pix_fmt", "yuv420p", "-b:v", f"{target_kbps}k", "-maxrate", f"{maxrate_kbps}k",
        "-bufsize", f"{BUFSIZE_KBPS}k", "-x264-params", X264_PARAMS, "-an", "-sn", "-dn",
        "-pass", str(pass_number), "-passlogfile", str(passlog),
        "-progress", "pipe:1", "-nostats",
    ]  # fmt: skip
    if pass_number == 1:
        return [*command, "-f", "null", "-"]
    return [*command, "-f", "h264", str(out)]


def frame_filter(title: TitlePlan) -> str:
    """A full Blu-ray frame: the anamorphic 1440x1080 scaled, anything smaller padded (black,
    centered; a no-op on a full frame)."""
    width, height = title.width, title.height
    if title.scale:
        return f"scale={width}:{height}:flags=lanczos,setsar=1"
    return f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
