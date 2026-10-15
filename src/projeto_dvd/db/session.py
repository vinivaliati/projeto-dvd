"""Engine creation and migrations."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlmodel import create_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def make_engine(url: str) -> Engine:
    # FastAPI runs sync routes in a thread pool, so connections cross threads.
    return create_engine(url, connect_args={"check_same_thread": False})


def migrate(url: str) -> None:
    """Upgrade the database to the latest migration.

    The Alembic config is built here instead of read from alembic.ini, so migrations work
    from the installed package inside the Docker image.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
