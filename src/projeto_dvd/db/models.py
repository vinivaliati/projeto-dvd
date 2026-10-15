"""Database tables."""

from datetime import datetime

from sqlalchemy import Index, text
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


class Job(SQLModel, table=True):
    """One DVD generation. The plan is stored whole; the log lives in WORK_DIR/jobs/<id>/."""

    __tablename__ = "job"
    # At most one queued or running job per disc folder: two quick clicks cannot create two.
    __table_args__ = (
        Index(
            "ix_job_active_folder",
            "folder",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    folder: str = Field(index=True)
    plan_json: str
    status: str = "queued"
    cancel_requested: bool = False
    step: str | None = None
    progress: float = 0.0
    error: str | None = None  # Portuguese, for the job page
    qa_json: str | None = None
    iso_path: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
