"""Database tables."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class MediaFile(SQLModel, table=True):
    """A video file under the input folder, with its cached ffprobe output.

    `(path, size, mtime_ns)` decides whether the file changed since the last scan.
    """

    __tablename__ = "media_file"

    id: int | None = Field(default=None, primary_key=True)
    # Disc folder name (NFC), the immediate subfolder of the input folder.
    folder: str = Field(index=True)
    # POSIX path relative to the input folder (NFC).
    path: str = Field(unique=True, index=True)
    size: int
    mtime_ns: int
    # Raw ffprobe JSON, kept whole: later phases read fields the summary ignores.
    probe_json: str | None = None
    # ffprobe error (truncated stderr) when the file could not be read.
    error: str | None = None
    scanned_at: datetime
