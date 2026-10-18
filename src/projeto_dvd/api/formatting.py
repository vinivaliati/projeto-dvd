"""Brazilian Portuguese formatting for the templates (Jinja filters)."""

from datetime import datetime
from pathlib import Path

from projeto_dvd.library.probe import AudioTrack, Video
from projeto_dvd.planner.profiles import Medium

VIDEO_CODECS = {
    "h264": "H.264",
    "hevc": "HEVC",
    "mpeg2video": "MPEG-2",
    "mpeg4": "MPEG-4",
    "av1": "AV1",
    "vc1": "VC-1",
}
SIXTEEN_NINE = 16 / 9
UNDEFINED_LANGUAGE = "não definido"
CHANNEL_LAYOUTS = {
    "mono": "mono",
    "stereo": "estéreo",
    "5.1": "5.1",
    "5.1(side)": "5.1",
    "7.1": "7.1",
}
CHANNEL_COUNTS = {1: "mono", 2: "estéreo", 6: "5.1", 8: "7.1"}
SUBTITLE_KINDS = {"text": "texto", "image": "imagem", "unknown": "desconhecido"}


def format_size(size: int) -> str:
    """Decimal units, like disc capacities (4,7 GB)."""
    for unit, factor in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if size >= factor:
            return f"{_decimal(size / factor)} {unit}"
    return f"{_decimal(size / 1e3)} KB"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours}h{minutes:02d}" if hours else f"{minutes} min"


def format_fps(fps: float | None) -> str:
    if fps is None:
        return "?"
    return f"{fps:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def format_aspect(ratio: float | None) -> str | None:
    """None for 16:9 (the common case is not shown) and for unknown ratios."""
    if ratio is None or abs(ratio - SIXTEEN_NINE) < 0.02:
        return None
    return f"{ratio:.2f}:1".replace(".", ",")


def video_label(video: Video) -> str:
    codec = VIDEO_CODECS.get(video.codec, video.codec.upper())
    return f"{_resolution(video.width, video.height)} · {codec} · {format_fps(video.fps)}"


def _resolution(width: int, height: int) -> str:
    # Scope movies are full width but less high (1920x800, 3832x1600): the width decides.
    if width >= 3800 or height >= 2000:
        return "2160p"
    if width > 1920 or height > 1080 or width < 1280:
        return f"{width}x{height}"
    return "1080p" if width > 1280 or height > 720 else "720p"


AUDIO_CODECS = {
    "ac3": "Dolby Digital (AC-3)",
    "eac3": "Dolby Digital Plus",
    "dts": "DTS",
    "truehd": "Dolby TrueHD",
    "aac": "AAC",
    "flac": "FLAC",
    "mp3": "MP3",
    "opus": "Opus",
}


def format_audio_codec(codec: str) -> str:
    if codec.startswith("pcm_"):
        return "PCM"
    return AUDIO_CODECS.get(codec, codec.upper())


def input_label(video: Video) -> str:
    """ "1080p, 23,976 quadros/s": what the form says about the source."""
    return f"{_resolution(video.width, video.height)}, {format_fps(video.fps)} quadros/s"


# Encode time per second of movie on a 6-core CPU, both passes (measured by the tech lead:
# ~310 fps for 1080p H.264 sources, SD about twice as fast).
ENCODE_SECONDS_PER_SECOND = {True: 0.2, False: 0.1}


# Blu-ray (Phase 6a, to calibrate with a real movie): x264 slow at 1080p is about real time;
# a copied remux is only read and written.
BD_ENCODE_SECONDS_PER_SECOND = 1.0
BD_COPY_SECONDS_PER_SECOND = 0.02


def encode_seconds(duration: float, hd: bool, medium: Medium, copied: bool) -> float:
    if medium == "bluray":
        return duration * (BD_COPY_SECONDS_PER_SECOND if copied else BD_ENCODE_SECONDS_PER_SECOND)
    return duration * ENCODE_SECONDS_PER_SECOND[hd]


def format_encode_time(duration: float, hd: bool) -> str:
    return format_remaining(duration * ENCODE_SECONDS_PER_SECOND[hd])


def output_display(host_output_dir: str | None, relative: str) -> str:
    """Where a file of OUTPUT_DIR is on Windows, or how to find it without HOST_OUTPUT_DIR."""
    if host_output_dir:
        return windows_path(host_output_dir, relative)
    return f"{relative.replace('/', chr(92))} (na pasta HOST_OUTPUT_DIR do .env)"


def windows_path(host_dir: str, relative: str) -> str:
    """/mnt/c/Users/x + iso/F.iso as C:\\Users\\x\\iso\\F.iso; other paths stay POSIX."""
    parts = [part for part in host_dir.split("/") if part]
    if len(parts) >= 2 and parts[0] == "mnt" and len(parts[1]) == 1:
        return "\\".join([f"{parts[1].upper()}:", *parts[2:], *relative.split("/")])
    return "/".join([host_dir.rstrip("/"), relative])


def format_language(language: str | None) -> str:
    return language or UNDEFINED_LANGUAGE


def format_channels(track: AudioTrack) -> str:
    if track.channel_layout:
        return CHANNEL_LAYOUTS.get(track.channel_layout, track.channel_layout)
    if track.channel_count is not None:
        return CHANNEL_COUNTS.get(track.channel_count, f"{track.channel_count} canais")
    return "?"


def format_subtitle_kind(kind: str) -> str:
    return SUBTITLE_KINDS.get(kind, kind)


def last_line(text: str) -> str:
    """ffprobe prints the reason last; earlier lines carry memory addresses."""
    lines = text.strip().splitlines()
    return lines[-1] if lines else ""


def probe_reason(error: str, path: Path) -> str:
    """The reason alone: ffprobe starts it with the path, already shown beside it."""
    return last_line(error).removeprefix(f"{path}: ")


def _decimal(value: float) -> str:
    text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
    return text.removesuffix(".0").replace(".", ",")


def format_ago(value: datetime | None, now: datetime) -> str:
    if value is None:
        return "?"
    minutes = int((now - value).total_seconds() // 60)
    if minutes < 1:
        return "agora"
    if minutes < 60:
        return f"há {minutes} min"
    if minutes < 24 * 60:
        return f"há {minutes // 60} h"
    days = minutes // (24 * 60)
    return f"há {days} dia{'s' if days != 1 else ''}"


def format_remaining(seconds: float | None) -> str:
    if seconds is None:
        return "calculando..."
    if seconds < 60:
        return "menos de 1 min"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"cerca de {minutes} min"
    return f"cerca de {minutes // 60}h{minutes % 60:02d}"
