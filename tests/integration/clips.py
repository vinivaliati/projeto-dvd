"""Short lavfi clips and plans for the slow DVD tests (real tools, inside the image)."""

import json
import subprocess
from pathlib import Path
from typing import Any

from projeto_dvd.encode.mpeg2 import apply_soft_pulldown
from projeto_dvd.library.files import find_videos
from projeto_dvd.library.probe import run_ffprobe, summarize
from projeto_dvd.planner.disc_source import DiscSource, prepare, run_capture, suggested_plan
from projeto_dvd.planner.dvd_plan import DvdPlan


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def movie_1080p(path: Path, seconds: int = 12, noisy: bool = False) -> Path:
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
        # Noise makes the picture hard to compress, so the 2-pass encoder reaches its target.
        *(["-vf", "noise=alls=30:allf=t"] if noisy else []),
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


def srt_cp1252(path: Path) -> Path:
    text = ("1\r\n00:00:01,000 --> 00:00:03,000\r\nAção, coração e pão de açúcar!\r\n"
            "É você? Não, é ele.\r\n\r\n"
            "2\r\n00:00:05,000 --> 00:00:07,000\r\nUma fala com quarenta e dois caracteres\r\n"
            "e mais uma linha também bem comprida aqui\r\n")  # fmt: skip
    data = text.encode("cp1252")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        path.write_bytes(data)
        return path
    raise AssertionError("the test subtitle must not be valid UTF-8")


def dvd_rip_film(path: Path, seconds: int = 10) -> Path:
    """A MakeMKV-like rip of a film DVD: MPEG-2 24p with soft pulldown, remuxed to MKV."""
    work = path.parent
    work.mkdir(parents=True, exist_ok=True)
    m2v, vob = work / "rip.m2v", work / "rip.vob"
    ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=s=720x480:r=24000/1001:d={seconds}",
        "-c:v", "mpeg2video", "-b:v", "6000k", "-g", "12", "-bf", "2", "-flags", "+cgop",
        "-sc_threshold", "1000000000", "-aspect", "16:9", "-f", "mpeg2video", str(m2v),
    )  # fmt: skip
    apply_soft_pulldown(m2v)
    ffmpeg("-fflags", "+genpts", "-i", str(m2v), "-f", "lavfi", "-i",
           f"sine=d={seconds}:sample_rate=48000", "-map", "0", "-map", "1", "-c:v", "copy",
           "-c:a", "ac3", "-b:a", "192k", "-metadata:s:a:0", "language=por",
           "-f", "dvd", str(vob))  # fmt: skip
    # Without the dvd_nav_packet data stream: Matroska cannot hold it (MakeMKV drops it too).
    ffmpeg("-fflags", "+genpts", "-i", str(vob), "-map", "0:v", "-map", "0:a", "-c", "copy",
           str(path))  # fmt: skip
    m2v.unlink()
    vob.unlink()
    return path


def interlaced_480i(path: Path, seconds: int = 8) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=s=720x480:r=30000/1001:d={seconds}",
           "-f", "lavfi", "-i", f"sine=d={seconds}:sample_rate=48000",
           "-vf", "setfield=tff", "-c:v", "mpeg2video", "-flags", "+ilme+ildct", "-top", "1",
           "-b:v", "6000k", "-aspect", "4:3", "-c:a", "ac3", "-b:a", "192k",
           "-metadata:s:a:0", "language=por", str(path))  # fmt: skip
    return path
