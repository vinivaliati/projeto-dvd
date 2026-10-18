from pathlib import Path

import pytest

from projeto_dvd.encode.bd_extract import (
    audio_es_command,
    audio_suffix,
    h264_copy_command,
    normalize_srt,
    srt_command,
    sup_command,
)
from projeto_dvd.planner.dvd_plan import AudioChoice

SOURCE = Path("/media/F/a.mkv")


def choice(action: str = "copy", codec: str = "ac3", channels: int = 6, kbps: int = 640,
           downmix: int | None = None, offset: float = 0.0) -> AudioChoice:  # fmt: skip
    return AudioChoice(index=1, language="pt", action=action, channels=channels,  # type: ignore[arg-type]
                       kbps=kbps, downmix=downmix, offset=offset, codec=codec)  # fmt: skip


def test_h264_copy_is_annex_b() -> None:
    assert h264_copy_command(SOURCE, 0, Path("/j/v.h264")) == [
        "ffmpeg", "-y", "-nostdin", "-i", "/media/F/a.mkv", "-map", "0:0", "-c", "copy",
        "-bsf:v", "h264_mp4toannexb", "-progress", "pipe:1", "-nostats", "-f", "h264",
        "/j/v.h264",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("audio", "suffix"),
    [(choice(), ".ac3"), (choice(codec="dts"), ".dts"), (choice(codec="pcm_s24le"), ".wav"),
     (choice("ac3", codec="truehd"), ".ac3")],
)  # fmt: skip
def test_audio_suffix(audio: AudioChoice, suffix: str) -> None:
    assert audio_suffix(audio) == suffix


def test_copied_audio_is_cut_to_the_movie() -> None:
    command = audio_es_command(SOURCE, choice(codec="dts"), 7200.0, Path("/j/a1.dts"))

    assert command == ["ffmpeg", "-y", "-nostdin", "-i", "/media/F/a.mkv", "-map", "0:1",
                       "-t", "7200.000", "-c:a", "copy", "-f", "dts", "/j/a1.dts"]  # fmt: skip


def test_lpcm_with_a_delay_is_padded_without_loss() -> None:
    command = audio_es_command(SOURCE, choice(codec="pcm_s24le", channels=2, offset=0.5), 60.0,
                               Path("/j/a1.wav"))  # fmt: skip

    assert command[command.index("-af") + 1] == "adelay=500:all=1"
    assert command[-5:] == ["-c:a", "pcm_s24le", "-f", "wav", "/j/a1.wav"]


def test_converted_audio_keeps_the_delay_and_the_layout() -> None:
    command = audio_es_command(SOURCE, choice("ac3", "truehd", 6, 640, 6, offset=0.25), 60.0,
                               Path("/j/a1.ac3"))  # fmt: skip

    assert command[command.index("-af") + 1] == "adelay=250:all=1"
    assert command[-9:-3] == ["-c:a", "ac3", "-b:a", "640k", "-ac", "6"]
    assert command[-2:] == ["ac3", "/j/a1.ac3"]


def test_an_early_track_is_trimmed() -> None:
    command = audio_es_command(SOURCE, choice("ac3", "aac", 2, 256, 2, offset=-0.2), 60.0,
                               Path("/j/a1.ac3"))  # fmt: skip

    assert command[command.index("-ss") + 1] == "0.200"


def test_subtitle_commands() -> None:
    assert sup_command(SOURCE, 3, Path("/j/s1.sup")) == [
        "ffmpeg", "-y", "-nostdin", "-i", "/media/F/a.mkv", "-map", "0:3", "-c", "copy",
        "-f", "sup", "/j/s1.sup"]  # fmt: skip
    assert srt_command(SOURCE, 4, Path("/j/s2.srt")) == [
        "ffmpeg", "-y", "-nostdin", "-i", "/media/F/a.mkv", "-map", "0:4", "-c:s", "srt",
        "-f", "srt", "/j/s2.srt"]  # fmt: skip


CUE = b"1\n00:00:01,000 --> 00:00:02,000\nOi\n"


@pytest.mark.parametrize(
    "raw",
    [b"\xef\xbb\xbf" + CUE.replace(b"\n", b"\r\n"), CUE, CUE + b"\n", CUE + b"\n\n\n"],
)
def test_normalize_srt_ends_with_a_blank_line(raw: bytes) -> None:
    assert normalize_srt(raw) == CUE + b"\n"


def test_a_converted_5_1_keeps_its_channels() -> None:
    command = audio_es_command(SOURCE, choice("ac3", "eac3", 6, 640), 60.0, Path("/j/a1.ac3"))

    assert "-ac" not in command and "-af" not in command
