"""Mux video and audio into an MPEG program stream, and build the ISO."""

from pathlib import Path

from projeto_dvd.planner.dvd_plan import DvdPlan


def first_pts_command(m2v: Path) -> list[str]:
    """The first displayed frame of the raw stream, with the timestamps the mux will use."""
    return [
        "ffprobe", "-v", "error", "-fflags", "+genpts", "-select_streams", "v:0",
        "-show_entries", "frame=pts_time", "-read_intervals", "%+#1", "-of", "csv=p=0",
        str(m2v),
    ]  # fmt: skip


def parse_first_pts(output: str) -> float:
    lines = [line for line in output.split() if line]
    if not lines:
        raise ValueError("ffprobe returned no frame")
    return float(lines[0])


def audio_path(job_dir: Path, number: int) -> Path:
    return job_dir / f"audio{number}.ac3"


def mux_command(plan: DvdPlan, job_dir: Path, first_pts: float) -> list[str]:
    """Video and AC-3 tracks into movie.mpg.

    +genpts: without it ffmpeg writes only two nav packs and every chapter falls at 0.
    -itsoffset: the raw video starts after the audio (preload and B-frame delay, 39 to 55 ms);
    each audio is shifted to the first video frame plus its own delay in the source.
    """
    command = ["ffmpeg", "-y", "-nostdin", "-fflags", "+genpts", "-i", str(job_dir / "video.m2v")]
    for number, audio in enumerate(plan.audio, start=1):
        offset = first_pts + max(audio.offset, 0.0)
        command += ["-itsoffset", f"{offset:.6f}", "-i", str(audio_path(job_dir, number))]
    for number in range(len(plan.audio) + 1):
        command += ["-map", str(number)]
    return [
        *command, "-c", "copy", "-f", "dvd", "-muxrate", "10080k", "-packetsize", "2048",
        "-progress", "pipe:1", "-nostats", str(job_dir / "movie.mpg"),
    ]  # fmt: skip


def iso_command(plan: DvdPlan, job_dir: Path) -> list[str]:
    """genisoimage, because xorriso does not write the UDF 1.02 bridge DVD-Video needs."""
    return [
        "genisoimage", "-quiet", "-dvd-video", "-udf", "-V", plan.volume,
        "-o", str(job_dir / "disc.iso"), str(job_dir / "dvd"),
    ]  # fmt: skip
