"""Shared web dependencies: templates, settings, database session, disc folders."""

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import Engine
from sqlmodel import Session

from projeto_dvd.api.formatting import (
    format_ago,
    format_aspect,
    format_channels,
    format_duration,
    format_fps,
    format_language,
    format_remaining,
    format_size,
    format_subtitle_kind,
    probe_reason,
    video_label,
)
from projeto_dvd.config import Settings
from projeto_dvd.library.files import list_disc_folders

WEB_DIR = Path(__file__).parent.parent / "web"

templates = Jinja2Templates(directory=WEB_DIR / "templates")
templates.env.filters.update(
    size=format_size,
    duration=format_duration,
    fps=format_fps,
    aspect=format_aspect,
    video_label=video_label,
    probe_reason=probe_reason,
    language=format_language,
    channels=format_channels,
    subtitle_kind=format_subtitle_kind,
    ago=format_ago,
    remaining=format_remaining,
)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


EngineDep = Annotated[Engine, Depends(get_engine)]


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_media_dir(settings: SettingsDep) -> Path:
    return settings.media_dir


MediaDirDep = Annotated[Path, Depends(get_media_dir)]


def disc_folder(media_dir: MediaDirDep, name: str) -> Path:
    """The real path of a disc folder; 404 for anything that is not one (no traversal)."""
    folder = list_disc_folders(media_dir).get(name)
    if folder is None:
        raise HTTPException(status_code=404)
    return folder


FolderDep = Annotated[Path, Depends(disc_folder)]
