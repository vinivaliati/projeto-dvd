"""AC-3 audio for DVD-Video: copy a compatible track, convert anything else."""

from pathlib import Path

from projeto_dvd.planner.dvd_plan import AudioChoice


def audio_command(choice: AudioChoice, source: Path, output: Path) -> list[str]:
    command = [
        "ffmpeg", "-y", "-nostdin", "-i", str(source.absolute()),
        "-map", f"0:{choice.index}", "-vn", "-sn", "-dn",
    ]  # fmt: skip
    if choice.offset < 0:
        # The audio starts before the video: drop that part, so both start together.
        command += ["-ss", f"{-choice.offset:.6f}"]
    if choice.action == "copy":
        command += ["-c:a", "copy"]
    else:
        command += ["-c:a", "ac3", "-b:a", f"{choice.kbps}k", "-ar", "48000"]
        if choice.downmix:
            command += ["-ac", str(choice.downmix)]
    return [*command, "-progress", "pipe:1", "-nostats", "-f", "ac3", str(output.absolute())]
