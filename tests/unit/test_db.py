from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from projeto_dvd.db.models import MediaFile
from projeto_dvd.db.session import make_engine, migrate


def make_row(path: str = "Disco/a.mkv") -> MediaFile:
    return MediaFile(
        folder="Disco",
        path=path,
        size=10,
        mtime_ns=1,
        probe_json="{}",
        scanned_at=datetime.now(UTC),
    )


def test_migration_creates_the_media_file_table(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("media_file")}

    assert columns == {
        "id",
        "folder",
        "path",
        "size",
        "mtime_ns",
        "probe_json",
        "error",
        "scanned_at",
    }


def test_models_match_the_migrations(engine: Engine) -> None:
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), SQLModel.metadata)

    assert diff == []


def test_migrate_twice_is_harmless(database_url: str, engine: Engine) -> None:
    migrate(database_url)

    assert "media_file" in inspect(engine).get_table_names()


def test_path_is_unique(session: Session) -> None:
    session.add(make_row())
    session.commit()
    session.add(make_row())

    with pytest.raises(IntegrityError):
        session.commit()


def test_engine_can_be_used_from_another_thread(engine: Engine) -> None:
    # FastAPI runs sync routes in a thread pool: the SQLite connection must allow that.
    def count() -> int:
        with Session(engine) as session:
            return len(session.exec(select(MediaFile)).all())

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(count).result() == 0


def test_make_engine_does_not_create_the_table(database_url: str) -> None:
    engine = make_engine(database_url)

    assert inspect(engine).get_table_names() == []
    engine.dispose()
