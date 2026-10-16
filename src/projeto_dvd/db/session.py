"""Engine creation and migrations."""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, event
from sqlmodel import create_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def make_engine(url: str) -> Engine:
    # FastAPI runs sync routes in a thread pool, so connections cross threads. timeout is the
    # SQLite busy timeout: the web and the worker share the database.
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 5})

    @event.listens_for(engine, "connect")
    def _wal(connection: Any, _record: Any) -> None:
        # WAL: readers never wait for the worker's writes. Works on the ext4 "data" volume.
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def migrate(url: str) -> None:
    """Upgrade the database to the latest migration.

    The Alembic config is built here instead of read from alembic.ini, so migrations work
    from the installed package inside the Docker image.
    """
    command.upgrade(_config(url), "head")


def is_migrated(engine: Engine) -> bool:
    """True when the database is at the latest migration (the worker waits for the web)."""
    head = ScriptDirectory.from_config(_config(str(engine.url))).get_current_head()
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision() == head


def _config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    return config
