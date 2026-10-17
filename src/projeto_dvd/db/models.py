"""Database tables."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Index, text
from sqlmodel import Field, Relationship, SQLModel


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
    # One TMDB match per video; deleting the video row (scan, purge) deletes it too. ORM
    # cascade, not PRAGMA foreign_keys: a future Alembic batch copy cannot wipe the titles.
    title: Optional["Title"] = Relationship(
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )


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


class Title(SQLModel, table=True):
    """The TMDB match of one video: a suggestion until the Vini confirms it."""

    __tablename__ = "title"

    media_file_id: int | None = Field(default=None, foreign_key="media_file.id", primary_key=True)
    status: str  # suggested, doubtful, confirmed, not_found
    kind: str  # movie or episode
    tmdb_id: int | None = None  # the movie, or the show of an episode
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None  # a file with two episodes
    label: str = ""  # what the card shows; a suggestion has no tmdb_json yet
    poster_path: str | None = None  # TMDB path, for the thumbnail
    message: str | None = None  # warning or the reason of not_found (Portuguese)
    tmdb_json: str | None = None  # stored details (Details), only when confirmed


class DiscProject(SQLModel, table=True):
    """The Montar DVD choices of one disc folder (a DiscChoices as JSON).

    No foreign key to media_file: a rescan must not delete the project.
    """

    __tablename__ = "disc_project"

    folder: str = Field(primary_key=True)
    choices_json: str
