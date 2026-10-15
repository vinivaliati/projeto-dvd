"""Application settings, read from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Paths inside the container; override with MEDIA_DIR and DATABASE_URL outside Docker."""

    # Input folder: each immediate subfolder is one disc. Mounted read-only.
    media_dir: Path = Path("/media")
    database_url: str = "sqlite:////data/projeto_dvd.db"
    # Intermediate files (WSL ext4) and the final ISO (a Windows folder). Phase 3.
    work_dir: Path = Path("/work")
    output_dir: Path = Path("/output")
