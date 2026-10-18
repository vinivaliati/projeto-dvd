"""Short lavfi clips and plans for the slow DVD tests (real tools, inside the image)."""

import json
import subprocess
from pathlib import Path
from typing import Any

from projeto_dvd.encode.mpeg2 import apply_soft_pulldown
from projeto_dvd.encode.x264 import X264_PARAMS
from projeto_dvd.library.files import find_videos
from projeto_dvd.library.probe import run_ffprobe, summarize
from projeto_dvd.metadata.filename import guess
from projeto_dvd.planner.calculator import suggest_profile
from projeto_dvd.planner.disc import DiscTitle
from projeto_dvd.planner.disc_build import TitleSource, build_disc_plan, disc_estimates, menu_plan
from projeto_dvd.planner.disc_plan import DiscPlan
from projeto_dvd.planner.disc_source import prepare_title, run_capture, run_trace, suggestion
from projeto_dvd.planner.dvd_plan import subtitle_options
from projeto_dvd.planner.profiles import PROFILES


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


def disc_titles(media: Path, folder: str) -> tuple[DiscTitle, ...]:
    """The folder as the app sees it after a scan, without the database."""
    titles = []
    for video in find_videos(media, media / folder):
        probe = run_ffprobe(video.absolute)
        assert probe.json is not None, probe.error
        summary = summarize(json.loads(probe.json))
        titles.append(DiscTitle(
            path=video.path, video=video, summary=summary,
            options=tuple(subtitle_options(summary, video.subtitles)), info=None,
            guess=guess(video.path.split("/", 1)[1], folder, 2030),
        ))  # fmt: skip
    return tuple(titles)


def source_of(media: Path, folder: str) -> TitleSource:
    result = prepare_title(disc_titles(media, folder)[0], run_capture)
    assert isinstance(result, TitleSource), result
    return result


def plan_for(media: Path, folder: str, confirm_low: bool = True, **choices: Any) -> DiscPlan:
    """The suggested disc of a folder, with some choices overridden."""
    titles = disc_titles(media, folder)
    chosen = suggestion(titles, folder).model_copy(update=choices)
    if "profile" not in choices and PROFILES[chosen.profile].medium != "dvd":
        # An HD clip suggests a Blu-ray now; these tests are about the DVD.
        dvd = [e for e in disc_estimates(chosen, titles, folder) if e.profile.medium == "dvd"]
        chosen = chosen.model_copy(update={"profile": suggest_profile(dvd).key})
    sources = [prepare_title(title, run_capture) for title in titles]
    ready = [s for s in sources if isinstance(s, TitleSource)]
    assert len(ready) == len(titles), sources
    menu = menu_plan(chosen, titles, folder, None, None)
    return build_disc_plan(folder, ready, chosen, menu, confirm_low=confirm_low,
                           replace_iso=False)  # fmt: skip


def episode(path: Path, languages: tuple[str, ...], aspect: str = "16:9", seconds: int = 4) -> Path:
    """A short episode: H.264 in the aspect asked, one AC-3 track per language."""
    path.parent.mkdir(parents=True, exist_ok=True)
    size = "640x360" if aspect == "16:9" else "640x480"
    inputs: list[str] = ["-f", "lavfi", "-i", f"testsrc2=s={size}:r=24000/1001:d={seconds}"]
    maps = ["-map", "0:v"]
    for number, language in enumerate(languages, 1):
        inputs += [
            "-f",
            "lavfi",
            "-i",
            f"sine=f={300 + 100 * number}:d={seconds}:sample_rate=48000",
        ]
        maps += ["-map", f"{number}:a", f"-metadata:s:a:{number - 1}", f"language={language}"]
    ffmpeg(*inputs, *maps, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-aspect", aspect, "-c:a", "ac3", "-b:a", "192k", str(path))  # fmt: skip
    return path


def series_folder(media: Path) -> str:
    """Three episodes: Portuguese and English with a Portuguese .srt, English only, and a 4:3
    one in Portuguese only."""
    folder = media / "Serie"
    episode(folder / "Serie.S01E01.mkv", ("por", "eng"))
    srt_cp1252(folder / "Serie.S01E01.pt.srt")
    episode(folder / "Serie.S01E02.mkv", ("eng",))
    episode(folder / "Serie.S01E03.mkv", ("por",), aspect="4:3")
    return "Serie"


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


def reopen_gops(m2v: Path, closed: set[int]) -> None:
    """Clear the closed_gop flag of every GOP not in `closed` (by order), as commercial DVDs
    with open GOPs have; the pictures stay decodable (the encoder closed them)."""
    data = bytearray(m2v.read_bytes())
    count, position = 0, data.find(b"\x00\x00\x01\xb8")
    while position >= 0:
        if count not in closed:
            data[position + 7] &= ~0x40 & 0xFF
        count += 1
        position = data.find(b"\x00\x00\x01\xb8", position + 4)
    m2v.write_bytes(bytes(data))


def dvd_rip_copyable(path: Path, size_tag: bool, seconds: int = 10) -> Path:
    """A rip like a commercial film DVD: MPEG-2 with the DVD header (9.8 Mbps, VBV 224 KiB),
    GOPs of 12 pictures with soft pulldown (30 fields), most of them open, chapters in the
    middle of GOPs, Portuguese AC-3 at 192k; MKV with or without MakeMKV's size tag."""
    work = path.parent
    work.mkdir(parents=True, exist_ok=True)
    m2v, vob, chapters = work / "rip.m2v", work / "rip.vob", work / "chapters.txt"
    ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=s=720x480:r=24000/1001:d={seconds}",
        "-c:v", "mpeg2video", "-b:v", "6000k", "-maxrate", "9800k", "-bufsize", "1835k",
        "-g", "12", "-bf", "2", "-flags", "+cgop", "-sc_threshold", "1000000000",
        "-aspect", "16:9", "-f", "mpeg2video", str(m2v),
    )  # fmt: skip
    apply_soft_pulldown(m2v)
    reopen_gops(m2v, closed={0, 4, 8, 12})  # closed at 0, 2, 4 and 6 s
    chapters.write_text(
        ";FFMETADATA1\n"
        + "".join(
            f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={s}\nEND={s + 1000}\ntitle=C\n"
            for s in (0, 2100, 5000)  # 2.1 s: near the closed GOP at 2 s; 5 s: none near
        )
    )
    ffmpeg("-fflags", "+genpts", "-i", str(m2v), "-f", "lavfi", "-i",
           f"sine=d={seconds}:sample_rate=48000", "-map", "0", "-map", "1", "-c:v", "copy",
           "-c:a", "ac3", "-b:a", "192k", "-metadata:s:a:0", "language=por",
           "-f", "dvd", str(vob))  # fmt: skip
    tag = ["-metadata:s:v:0", f"NUMBER_OF_BYTES-eng={m2v.stat().st_size}"] if size_tag else []
    ffmpeg("-fflags", "+genpts", "-i", str(vob), "-i", str(chapters), "-map", "0:v",
           "-map", "0:a", "-map_chapters", "1", "-c", "copy", *tag, str(path))  # fmt: skip
    for leftover in (vob, chapters):
        leftover.unlink()
    return m2v  # kept next to the rip, to compare with the disc


def bd_plan_for(media: Path, folder: str, **choices: Any) -> DiscPlan:
    """The Blu-ray of a one-video folder (BD-25), with the header and GOP samples of Gerar."""
    titles = disc_titles(media, folder)
    chosen = suggestion(titles, folder).model_copy(update={"profile": "bd25", **choices})
    source = prepare_title(titles[0], run_capture, "bluray", run_trace)
    assert isinstance(source, TitleSource), source
    return build_disc_plan(folder, [source], chosen, None, confirm_low=True, replace_iso=False)


def bd_remux(path: Path, seconds: int = 10, delay: float = 0.0, lpcm: bool = False) -> Path:
    """A Blu-ray style H.264 (x264 in Blu-ray mode, 1920x1080) with AC-3 640k or LPCM.

    Not ultrafast: it writes Constrained Baseline, which the copy rule rightly refuses."""
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = ["-c:a", "pcm_s24le"] if lpcm else ["-c:a", "ac3", "-b:a", "640k"]
    ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=s=1920x1080:r=24000/1001:d={seconds}",
        "-itsoffset", str(delay), "-f", "lavfi",
        "-i", f"sine=f=440:d={seconds}:sample_rate=48000",
        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-b:v", "8000k",
        "-maxrate", "35000k", "-bufsize", "30000k", "-x264-params", X264_PARAMS,
        *audio, "-ac", "2", "-metadata:s:a:0", "language=por", str(path),
    )  # fmt: skip
    return path
