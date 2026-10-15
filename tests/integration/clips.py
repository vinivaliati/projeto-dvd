"""Short lavfi clips and plans for the slow DVD tests (real tools, inside the image)."""

import json
import subprocess
from pathlib import Path
from typing import Any

from projeto_dvd.library.files import find_videos
from projeto_dvd.library.probe import run_ffprobe, summarize
from projeto_dvd.planner.disc_source import DiscSource, prepare, run_capture, suggested_plan
from projeto_dvd.planner.dvd_plan import DvdPlan


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def movie_1080p(path: Path, seconds: int = 12) -> Path:
    """Scope 1080p film: AAC 5.1 at 44.1 kHz (por), AC-3 2.0 192k starting 0.2 s late (eng),
    chapters at 0, 4 and 8 s."""
    path.parent.mkdir(parents=True, exist_ok=True)
    chapters = path.with_name("chapters.txt")
    chapters.write_text(
        ";FFMETADATA1\n"
        + "".join(
            f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={s * 1000}\nEND={(s + 4) * 1000}\ntitle=C{s}\n"
            for s in (0, 4, 8)
        )
    )
    ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=s=1920x800:r=24000/1001:d={seconds}",
        "-f", "lavfi", "-i", f"sine=f=440:d={seconds}:sample_rate=44100",
        "-itsoffset", "0.2", "-f", "lavfi", "-i", f"sine=f=660:d={seconds}:sample_rate=48000",
        "-i", str(chapters),
        "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map_chapters", "3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a:0", "aac", "-ac:a:0", "6", "-c:a:1", "ac3", "-b:a:1", "192k", "-ac:a:1", "2",
        "-metadata:s:a:0", "language=por", "-metadata:s:a:1", "language=eng",
        str(path),
    )  # fmt: skip
    chapters.unlink()
    return path


def disc_source(media: Path, folder: str) -> DiscSource:
    video = find_videos(media, media / folder)[0]
    probe = run_ffprobe(video.absolute)
    assert probe.json is not None, probe.error
    result = prepare(folder, video, summarize(json.loads(probe.json)), run_capture)
    assert isinstance(result, DiscSource), result
    return result


def plan_for(media: Path, folder: str, **overrides: Any) -> DvdPlan:
    return suggested_plan(disc_source(media, folder), **overrides)
