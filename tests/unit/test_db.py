import json
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
from projeto_dvd.planner.disc_plan import DiscPlan


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


def test_migration_creates_the_disc_project_table(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("disc_project")}

    assert columns == {"folder", "choices_json"}


PHASE_3_PLAN = {
    "folder": "Filme", "path": "Filme/Filme.mkv", "video_index": 0, "size": 100,
    "mtime_ns": 200, "duration": 7200.0, "profile": "dvd9", "video_kbps": 8487,
    "maxrate_kbps": 9000, "estimated_bytes": 8_000_000_000, "mode": "film",
    "top_field_first": True, "aspect": "16:9", "width": 720, "height": 356, "scale": True,
    "hd_color": True,
    "audio": [
        {"index": 2, "language": "pt", "action": "ac3", "channels": 6, "kbps": 448,
         "downmix": None, "offset": 0.0},
        {"index": 1, "language": "en", "action": "copy", "channels": 6, "kbps": 448,
         "downmix": None, "offset": 0.05},
    ],
    "subtitles": [{"key": "s3", "stream_index": 3, "file": None, "language": "pt"}],
    "subtitle_on": True, "chapters": [0.0, 300.0], "confirmed_low": False,
    "replace_existing": False, "volume": "FILME", "iso_name": "Filme.iso",
}  # fmt: skip


def test_migration_0004_converts_phase_3_jobs(database_url: str) -> None:
    command.upgrade(_config(database_url), "0003")
    engine = make_engine(database_url)
    insert = text(
        "INSERT INTO job (folder, plan_json, status, cancel_requested, progress, created_at)"
        " VALUES (:folder, :plan, :status, 0, 0.0, '2026-10-16 00:00:00')"
    )
    with engine.begin() as connection:
        for folder, status in (("Filme", "done"), ("Outro", "queued"), ("Mais", "running")):
            plan = json.dumps({**PHASE_3_PLAN, "folder": folder})
            connection.execute(insert, {"folder": folder, "plan": plan, "status": status})

    migrate(database_url)

    with engine.connect() as connection:
        rows = connection.execute(text("SELECT plan_json, status, error FROM job ORDER BY id"))
        jobs = rows.all()
    engine.dispose()
    plans = [DiscPlan.model_validate_json(row[0]) for row in jobs]
    assert plans[0].menu is None
    assert plans[0].subtitle_on == 1
    title = plans[0].titles[0]
    assert (title.path, title.audio_map, title.subtitle_map) == ("Filme/Filme.mkv", (0, 1), (0,))
    assert title.menu_name == "Filme"
    assert jobs[0][1:] == ("done", None)
    old = "Job criado numa versão anterior; gere de novo."
    assert [row[1:] for row in jobs[1:]] == [("failed", old), ("failed", old)]
