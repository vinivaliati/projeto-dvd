"""The elementary streams tsMuxeR reads for a Blu-ray, cut and aligned to the video.

tsMuxeR ignores the delay a MKV gives an audio track, so each track is written already in
place: LPCM gets silence in front (no loss), a converted track gets the delay applied, and an
early track is trimmed. Every track ends with the movie.
"""

from pathlib import Path

from projeto_dvd.planner.dvd_plan import BD_PCM_BITS, AudioChoice

SUFFIXES = {"ac3": ".ac3", "dts": ".dts"}
FORMATS = {".ac3": "ac3", ".dts": "dts", ".wav": "wav"}


def h264_copy_command(source: Path, video_index: int, out: Path) -> list[str]:
    """The H.264 of a remux in Annex B: tsMuxeR then repeats SPS/PPS before every I frame
    without insertSEI or contSPS (which rewrite the stream)."""
    return [
        "ffmpeg", "-y", "-nostdin", "-i", str(source), "-map", f"0:{video_index}", "-c", "copy",
        "-bsf:v", "h264_mp4toannexb", "-progress", "pipe:1", "-nostats", "-f", "h264", str(out),
    ]  # fmt: skip


def audio_suffix(choice: AudioChoice) -> str:
    if choice.action == "ac3":
        return ".ac3"
    if choice.codec in BD_PCM_BITS:
        return ".wav"
    return SUFFIXES[choice.codec]


def audio_es_command(source: Path, choice: AudioChoice, duration: float, out: Path) -> list[str]:
    command = ["ffmpeg", "-y", "-nostdin", "-i", str(source), "-map", f"0:{choice.index}"]
    if choice.offset < 0:
        command += ["-ss", f"{-choice.offset:.3f}"]
    command += ["-t", f"{duration:.3f}"]
    pcm = choice.action == "copy" and choice.codec in BD_PCM_BITS
    if choice.offset > 0 and (pcm or choice.action == "ac3"):
        command += ["-af", f"adelay={round(choice.offset * 1000)}:all=1"]
    if choice.action == "ac3":
        command += ["-c:a", "ac3", "-b:a", f"{choice.kbps}k"]
        if choice.downmix:
            command += ["-ac", str(choice.downmix)]
    elif pcm:
        command += ["-c:a", choice.codec]  # written again as the same PCM: lossless
    else:
        command += ["-c:a", "copy"]
    return [*command, "-f", FORMATS[audio_suffix(choice)], str(out)]


def sup_command(source: Path, stream_index: int, out: Path) -> list[str]:
    return ["ffmpeg", "-y", "-nostdin", "-i", str(source), "-map", f"0:{stream_index}",
            "-c", "copy", "-f", "sup", str(out)]  # fmt: skip


def srt_command(source: Path, stream_index: int, out: Path) -> list[str]:
    return ["ffmpeg", "-y", "-nostdin", "-i", str(source), "-map", f"0:{stream_index}",
            "-c:s", "srt", "-f", "srt", str(out)]  # fmt: skip


def normalize_srt(data: bytes) -> bytes:
    """UTF-8 without BOM, LF, and a blank line at the end: without it tsMuxeR drops the last
    subtitle (tested)."""
    text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return (text.rstrip("\n") + "\n\n").encode("utf-8")
