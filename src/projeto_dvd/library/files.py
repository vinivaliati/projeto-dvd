"""Find disc folders, videos and external subtitles. Read-only: nothing here writes."""

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = frozenset({".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts"})
# .idx counts only next to its .sub (VobSub keeps the images in the .sub).
SUBTITLE_EXTENSIONS = frozenset({".srt", ".ass", ".ssa", ".sup", ".idx"})
IMAGE_SUBTITLE_EXTENSIONS = frozenset({".sup", ".idx"})


@dataclass(frozen=True)
class ExternalSubtitle:
    name: str
    language: str | None  # the middle part of the name, as is ("pt-BR", "en.forced")
    image: bool


@dataclass(frozen=True)
class VideoFile:
    path: str  # relative to the input folder, POSIX, NFC
    absolute: Path  # the real path, for reading
    size: int
    mtime_ns: int
    subtitles: tuple[ExternalSubtitle, ...] = ()


def nfc(text: str) -> str:
    # Accented names copied from Windows can arrive decomposed (NFD).
    return unicodedata.normalize("NFC", text)


def natural_key(text: str) -> tuple[tuple[int, str], ...]:
    """Sort key that puts S01E02 before S01E10, ignoring case."""
    return tuple(
        # isdecimal, not isdigit: "²" is a digit but int() rejects it.
        (int(part), "") if part.isdecimal() else (0, part.casefold())
        for part in re.split(r"(\d+)", text)
    )


def list_disc_folders(media_dir: Path) -> dict[str, Path]:
    """Readable, non-link subfolders of the input folder: NFC name -> real path."""
    try:
        entries = list(os.scandir(media_dir))
    except OSError:
        return {}
    folders = {
        nfc(entry.name): Path(entry.path)
        for entry in entries
        if entry.is_dir(follow_symlinks=False) and _readable(entry.path)
    }
    return dict(sorted(folders.items(), key=lambda item: natural_key(item[0])))


def find_videos(media_dir: Path, folder: Path) -> list[VideoFile]:
    """Videos under a disc folder (recursive, links skipped), stat taken now, natural order."""
    videos: dict[str, VideoFile] = {}
    for dirpath, _, filenames in os.walk(folder, followlinks=False):
        directory = Path(dirpath)
        names = [name for name in filenames if not os.path.islink(directory / name)]
        for name, subtitles in match_subtitles(names).items():
            absolute = directory / name
            path = nfc(absolute.relative_to(media_dir).as_posix())
            if path in videos:  # same name in NFC and NFD: keep one, the path is the key
                continue
            try:
                stat = absolute.stat()
            except OSError:  # removed (or unreadable) since the listing
                continue
            videos[path] = VideoFile(
                path=path,
                absolute=absolute,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                subtitles=subtitles,
            )
    return sorted(videos.values(), key=lambda video: natural_key(video.path))


def match_subtitles(filenames: list[str]) -> dict[str, tuple[ExternalSubtitle, ...]]:
    """Map each video in one folder to its external subtitles.

    A subtitle belongs to the video whose name (without extension) starts it, followed by a
    dot; when several videos match, only the longest name wins ("Filme.2.pt.srt" belongs to
    "Filme.2.mkv", not to "Filme.mkv"). Names are compared in NFC, ignoring case; the keys of
    the result are the real video names.
    """
    lower_names = {nfc(name).lower() for name in filenames}
    stems = {
        name: nfc(Path(name).stem)
        for name in filenames
        if Path(name).suffix.lower() in VIDEO_EXTENSIONS
    }
    result: dict[str, list[ExternalSubtitle]] = {name: [] for name in stems}
    for name in sorted(map(nfc, filenames), key=natural_key):
        suffix = Path(name).suffix.lower()
        if suffix not in SUBTITLE_EXTENSIONS:
            continue
        if suffix == ".idx" and Path(name).with_suffix(".sub").name.lower() not in lower_names:
            continue
        base = name[: -len(suffix)]
        matches = {
            video: stem
            for video, stem in stems.items()
            if base.lower() == stem.lower() or base.lower().startswith(stem.lower() + ".")
        }
        if not matches:
            continue
        longest = max(len(stem) for stem in matches.values())
        for video, stem in matches.items():
            if len(stem) == longest:
                language = base[len(stem) + 1 :]
                result[video].append(
                    ExternalSubtitle(
                        name=name,
                        language=language or None,
                        image=suffix in IMAGE_SUBTITLE_EXTENSIONS,
                    )
                )
    return {video: tuple(subtitles) for video, subtitles in result.items()}


def _readable(path: str) -> bool:
    try:
        with os.scandir(path):
            return True
    except OSError:
        return False
