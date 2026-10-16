"""Application settings, read from environment variables."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Paths inside the container; override with MEDIA_DIR and DATABASE_URL outside Docker."""

    # Input folder: each immediate subfolder is one disc. Mounted read-only.
    media_dir: Path = Path("/media")
    database_url: str = "sqlite:////data/projeto_dvd.db"
    # Intermediate files (WSL ext4) and the final ISO (a Windows folder). Phase 3.
    work_dir: Path = Path("/work")
    output_dir: Path = Path("/output")
    # Host names the app answers to (the port is published on 127.0.0.1 only).
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    # The output folder as the host sees it (HOST_OUTPUT_DIR), only to show the ISO path.
    host_output_dir: str | None = None
    # TMDB API Read Access Token (Bearer); empty or missing turns the curation off. Phase 2.
    tmdb_token: SecretStr | None = None
    tmdb_language: str = "pt-BR"
