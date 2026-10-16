from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.db.session import _config, is_migrated, make_engine, migrate


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


def test_migration_creates_the_job_table(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("job")}

    assert columns == {"id", "folder", "plan_json", "status", "cancel_requested", "step",
                       "progress", "error", "qa_json", "iso_path", "created_at", "started_at",
                       "finished_at"}  # fmt: skip


def test_wal_is_on(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"


def test_is_migrated(database_url: str) -> None:
    engine = make_engine(database_url)
    assert not is_migrated(engine)
    migrate(database_url)
    assert is_migrated(engine)
    engine.dispose()


def make_title(session: Session, status: str = "confirmed") -> MediaFile:
    row = make_row()
    row.title = Title(status=status, kind="movie", label="Anel (2001)", tmdb_id=101)
    session.add(row)
    session.commit()
    return row


def test_deleting_a_media_file_deletes_its_title(session: Session) -> None:
    row = make_title(session)

    session.delete(row)
    session.commit()

    assert session.exec(select(Title)).all() == []


def test_migration_0003_keeps_existing_rows(database_url: str) -> None:
    command.upgrade(_config(database_url), "0002")
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO media_file (folder, path, size, mtime_ns, scanned_at)"
                " VALUES ('F', 'F/a.mkv', 1, 1, '2026-10-16 00:00:00')"
            )
        )
    migrate(database_url)
    with Session(engine) as session:
        assert len(session.exec(select(MediaFile)).all()) == 1
        assert session.exec(select(Title)).all() == []
    engine.dispose()
