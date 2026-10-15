"""Incremental scan of a disc folder and the view models of the library screens."""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from sqlmodel import Session, col, select

from projeto_dvd.db.models import MediaFile
from projeto_dvd.library.files import VideoFile, find_videos
from projeto_dvd.library.probe import READ_ERROR, ProbeResult, Summary, summarize

Prober = Callable[[Path], ProbeResult]


class Status(StrEnum):
    EMPTY = "vazia"
    NOT_SCANNED = "não escaneada"
    CHANGED = "mudou"
    WARNINGS = "com avisos"
    OK = "ok"


@dataclass(frozen=True)
class FileView:
    video: VideoFile
    summary: Summary | None  # None until scanned (or when ffprobe failed)
    error: str | None

    @property
    def warnings(self) -> tuple[str, ...]:
        if self.error is not None:
            return (READ_ERROR,)
        return self.summary.warnings if self.summary else ()


@dataclass(frozen=True)
class FolderView:
    name: str
    status: Status
    files: tuple[FileView, ...]
    size: int
    duration: float | None

    @property
    def warning_count(self) -> int:
        return sum(1 for file in self.files if file.warnings)


def scan_folder(session: Session, media_dir: Path, name: str, folder: Path, probe: Prober) -> int:
    """Probe new, changed and previously failed videos; drop rows of removed ones.

    Returns how many files were sent to ffprobe. Each file is committed on its own, so a long
    scan keeps what it already read if something stops it.
    """
    known = _rows(session, name)
    videos = find_videos(media_dir, folder)
    probed = 0
    for video in videos:
        row = known.get(video.path)
        if row is not None and row.error is None and _unchanged(row, video):
            continue
        result = probe(video.absolute)
        probed += 1
        if result.error is not None and not video.absolute.exists():
            if row is not None:  # removed while scanning
                session.delete(row)
                session.commit()
            continue
        row = row or MediaFile(folder=name, path=video.path, size=0, mtime_ns=0, scanned_at=_now())
        # The stat from before ffprobe: a file still being copied will look changed next time.
        row.size, row.mtime_ns = video.size, video.mtime_ns
        row.probe_json, row.error, row.scanned_at = result.json, result.error, _now()
        session.add(row)
        session.commit()
    current = {video.path for video in videos}
    for path, row in known.items():
        if path not in current:
            session.delete(row)
    session.commit()
    return probed


def purge_missing_folders(session: Session, names: Iterable[str]) -> None:
    """Delete rows of disc folders that no longer exist."""
    stale = select(MediaFile).where(col(MediaFile.folder).not_in(list(names)))
    for row in session.exec(stale).all():
        session.delete(row)
    session.commit()


def folder_view(session: Session, media_dir: Path, name: str, folder: Path) -> FolderView:
    """Everything the screens show about one disc folder. Only stat, never ffprobe."""
    rows = _rows(session, name)
    videos = find_videos(media_dir, folder)
    files = tuple(_file_view(video, rows.get(video.path)) for video in videos)
    durations = [f.summary.duration for f in files if f.summary and f.summary.duration is not None]
    return FolderView(
        name=name,
        status=_status(videos, rows, files),
        files=files,
        size=sum(video.size for video in videos),
        duration=sum(durations) if durations else None,
    )


def _status(
    videos: list[VideoFile], rows: dict[str, MediaFile], files: tuple[FileView, ...]
) -> Status:
    if not videos and not rows:
        return Status.EMPTY
    if not rows:
        return Status.NOT_SCANNED
    current = {video.path: video for video in videos}
    if current.keys() != rows.keys() or not all(
        _unchanged(rows[path], video) for path, video in current.items()
    ):
        return Status.CHANGED
    if any(file.warnings for file in files):
        return Status.WARNINGS
    return Status.OK


def _file_view(video: VideoFile, row: MediaFile | None) -> FileView:
    if row is None:
        return FileView(video=video, summary=None, error=None)
    summary = summarize(json.loads(row.probe_json)) if row.probe_json else None
    return FileView(video=video, summary=summary, error=row.error)


def _rows(session: Session, name: str) -> dict[str, MediaFile]:
    query = select(MediaFile).where(MediaFile.folder == name)
    return {row.path: row for row in session.exec(query).all()}


def _unchanged(row: MediaFile, video: VideoFile) -> bool:
    # Equality, not "newer than": Explorer keeps the original mtime when copying.
    return row.size == video.size and row.mtime_ns == video.mtime_ns


def _now() -> datetime:
    return datetime.now(UTC)
