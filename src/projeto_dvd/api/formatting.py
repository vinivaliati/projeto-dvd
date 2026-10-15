"""Brazilian Portuguese formatting for the templates (Jinja filters)."""

from pathlib import Path

from projeto_dvd.library.probe import AudioTrack, Video

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
