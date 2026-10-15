# Phase 1: Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** List each subfolder of the read-only input folder as a potential disc, scan its videos with ffprobe (incrementally) and show the technical data on two Portuguese screens.

**Architecture:** Pure functions do the work (`library/probe.py` reads and summarizes ffprobe JSON, `library/files.py` walks folders, `library/scan.py` scans incrementally and builds the view models); a single SQLite table `media_file` caches the raw ffprobe JSON keyed by `(path, size, mtime_ns)`. FastAPI routes in `api/` render Jinja templates; HTMX swaps the folder body after a synchronous scan guarded by a global lock.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX 2.0.11 (vendored), own CSS, SQLModel + Alembic on SQLite, pydantic-settings, ffprobe 7.1 (Debian trixie image), pytest.

**Spec:** `docs/plans/2026-10-14-fase-1-biblioteca-design.md` (approved by Vini on 2026-10-15, together with the own-CSS decision and the roadmap order 1 → 3 → 2 → 4 → 5 → 6 → 7 → 8).

## Global Constraints

- The input folder (`MEDIA_DIR`, `/media` in Docker) is **never written to**. No `open(..., "w")`, `touch`, `mkdir` or chmod under it, anywhere.
- Symlinks are ignored (disc folders, files, folders inside a disc folder). Names are normalized to Unicode NFC before comparing and storing.
- Video extensions: `.mkv .mp4 .m4v .avi .mov .ts .m2ts`; external subtitles: `.srt .ass .ssa .sup`, plus `.idx` only when the `.sub` with the same name exists. Case-insensitive.
- ffprobe command: `ffprobe -v error -print_format json -show_format -show_streams -show_chapters <absolute path>`, list arguments, no shell, timeout 60 s, stderr truncated to 500 characters.
- UI text in Portuguese, Brazilian number format (`23,976`, `38 GB`, `2h58`); code, identifiers, commits and docstrings in English.
- Warning texts, exactly: "Não foi possível ler o arquivo", "Sem faixa de vídeo", "HDR (precisa de conversão para SDR)", "Dolby Vision perfil 5 (conversão de cor a confirmar)", "Acima de 1080p".
- Palette: background `#121212`, surface `#1c1c1e`, border `#2c2c2e`, text `#ececec`, secondary `#9a9a9a`, accent `#e0a526`, ok `#4caf50`, error `#e5534b`; body `system-ui`, folder names `Georgia, serif`, numbers `tabular-nums`, max width ~1100 px.
- Run `make format` before every gate (long lines in the plan's code are left for ruff to wrap).
- Quality gates (CLAUDE.md 2.5): `make lint` (ruff check, ruff format --check, mypy strict) and `make test` (coverage ≥ 90% with branches) green at the end of every task. No `pragma: no cover` in `library/`.
- `slow` tests never skip because a tool is missing; they run inside the Docker `test` stage.
- No travessão (—) in prose; Conventional Commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Checkpoint rule (Vini):** stop after each task: the matching agents review it, then wait for Vini's ok before the next task.

## Plan decisions (beyond the spec)

- The scan count goes to the screen instead of a log line ("Scan concluído: 2 arquivos lidos pelo ffprobe."): uvicorn does not show app loggers by default, and on screen it is testable and useful for the manual QA of the incremental scan on `/mnt/c`.
- `dvd_subtitle` cannot be generated from text with ffmpeg (bitmap encoders need bitmap input); image subtitles are covered by the hand-written PGS fixture and by summary tests on small dicts.
- "Upsert by path" is done through the ORM inside the scan lock (load the folder's rows, update or insert); `path` keeps a unique index as the database-level guard.
- The app is built by a factory (`create_app(settings)`), and uvicorn runs with `--factory`, so tests get their own media folder and database.
- A never-scanned folder shows a message in place of the table, and the header button is the only "Escanear" (one button, one HTMX setup), instead of a second big button.
- The roadmap keeps phase numbers; only the order changes (1 → 3 → 2 → ...), to avoid renumbering every reference.

## Review Focus

1. A folder named with accents, spaces, `#` or `?` (common in Portuguese titles): links must be percent-encoded and the page must open (Task 4 test `test_folder_with_special_characters_opens_from_library_link`).
2. A file still being copied from Windows while scanning: the stat taken before ffprobe is stored, so the next scan sees a change and probes again (Task 3 test `test_file_growing_during_scan_is_probed_again_next_time`).
3. The external drive disconnected (empty `/media`): the library shows the help card and does not crash (Task 4 test `test_library_without_folders_shows_help`); cached rows are purged, which only costs a rescan.
4. Two clicks on "Escanear" (or two tabs): the second request answers "Já existe um scan em andamento" instead of probing twice (Task 4 test `test_scan_while_another_is_running_reports_it`).
5. A video whose stream data is partial (no duration, `0/0` frame rate, `0:1` aspect, no channel layout): the summary shows "?" and never divides by zero (Task 2 tests `test_missing_values_do_not_break_the_summary` and friends).

---

## File structure

| File | Responsibility |
|---|---|
| `src/projeto_dvd/config.py` | `Settings` (pydantic-settings): `media_dir`, `database_url` |
| `src/projeto_dvd/db/__init__.py` | package marker |
| `src/projeto_dvd/db/models.py` | `MediaFile` table |
| `src/projeto_dvd/db/session.py` | `make_engine`, `migrate` (Alembic config built in code) |
| `src/projeto_dvd/db/migrations/env.py` | Alembic environment (no `fileConfig`, batch mode) |
| `src/projeto_dvd/db/migrations/versions/0001_create_media_file.py` | first migration |
| `src/projeto_dvd/library/__init__.py` | package marker |
| `src/projeto_dvd/library/probe.py` | run ffprobe, summarize its JSON, warnings |
| `src/projeto_dvd/library/files.py` | disc folders, videos, external subtitles, natural sort, NFC |
| `src/projeto_dvd/library/scan.py` | incremental scan, purge, folder status and view models |
| `src/projeto_dvd/api/__init__.py` | package marker |
| `src/projeto_dvd/api/health.py` | `GET /health` (moved from `app.py`) |
| `src/projeto_dvd/api/formatting.py` | pt-BR formatting used as Jinja filters |
| `src/projeto_dvd/api/library.py` | `GET /`, `GET /folders/{name}`, `POST /folders/{name}/scan` |
| `src/projeto_dvd/app.py` | `create_app` factory, lifespan (migrate), static files |
| `src/projeto_dvd/web/templates/*.html` | `base`, `library`, `folder`, `_folder_body` |
| `src/projeto_dvd/web/static/app.css`, `htmx.min.js` | own CSS, vendored HTMX |
| `tests/conftest.py` | `engine`, `session` fixtures |
| `tests/fixtures/make_fixtures.sh`, `tests/fixtures/probe/*.json` | ffprobe fixtures |
| `tests/unit/test_*.py`, `tests/integration/test_*.py` | tests |

---

### Task 1: Configuration and database

**Files:**
- Modify: `pyproject.toml` (dependencies, pytest addopts)
- Create: `src/projeto_dvd/config.py`, `src/projeto_dvd/db/__init__.py`, `src/projeto_dvd/db/models.py`, `src/projeto_dvd/db/session.py`, `src/projeto_dvd/db/migrations/env.py`, `src/projeto_dvd/db/migrations/versions/0001_create_media_file.py`
- Create: `tests/conftest.py`, `tests/unit/test_config.py`, `tests/unit/test_db.py`

**Interfaces:**
- Produces:
  - `projeto_dvd.config.Settings(media_dir: Path = Path("/media"), database_url: str = "sqlite:////data/projeto_dvd.db")`
  - `projeto_dvd.db.models.MediaFile` (SQLModel table `media_file`: `id`, `folder`, `path`, `size`, `mtime_ns`, `probe_json`, `error`, `scanned_at`)
  - `projeto_dvd.db.session.make_engine(url: str) -> sqlalchemy.Engine`
  - `projeto_dvd.db.session.migrate(url: str) -> None`
  - fixtures `engine: Engine` and `session: Session` (migrated SQLite in `tmp_path`)

- [ ] **Step 1: Add the dependencies and the pytest options**

Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
uv add "sqlmodel>=0.0.48" "alembic>=1.20.0" "pydantic-settings>=2.16.0"
```

Then edit `[tool.pytest.ini_options]` in `pyproject.toml` to:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# "not slow" by default; "-m slow" on the command line wins (last -m applies).
addopts = "--strict-markers -m 'not slow' --cov=projeto_dvd --cov-branch --cov-report=term-missing --cov-fail-under=90"
markers = ["slow: integration tests that need the media toolchain (run inside the Docker image)"]
```

Expected: `uv.lock` updated; `uv run pytest` still green (30 passed).

- [ ] **Step 2: Write the failing tests for the settings**

`tests/unit/test_config.py`:
```python
from pathlib import Path

import pytest

from projeto_dvd.config import Settings


def test_defaults_point_to_the_container_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIA_DIR", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings()

    assert settings.media_dir == Path("/media")
    assert settings.database_url == "sqlite:////data/projeto_dvd.db"


def test_environment_variables_override_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", "/tmp/entrada")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/test.db")

    settings = Settings()

    assert settings.media_dir == Path("/tmp/entrada")
    assert settings.database_url == "sqlite:////tmp/test.db"
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_config.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'projeto_dvd.config'`

- [ ] **Step 4: Write `src/projeto_dvd/config.py`**

```python
"""Application settings, read from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Paths inside the container; override with MEDIA_DIR and DATABASE_URL outside Docker."""

    # Input folder: each immediate subfolder is one disc. Mounted read-only.
    media_dir: Path = Path("/media")
    database_url: str = "sqlite:////data/projeto_dvd.db"
```

- [ ] **Step 5: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_config.py -v --no-cov`
Expected: 2 passed

- [ ] **Step 6: Write the failing database tests and fixtures**

`tests/conftest.py`:
```python
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from projeto_dvd.db.session import make_engine, migrate


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    migrate(database_url)
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
```

`tests/unit/test_db.py`:
```python
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
```

- [ ] **Step 7: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_db.py -v --no-cov`
Expected: ERROR with `ModuleNotFoundError: No module named 'projeto_dvd.db'`

- [ ] **Step 8: Write the database package**

`src/projeto_dvd/db/__init__.py`:
```python
"""Database: SQLModel models, engine and Alembic migrations."""
```

`src/projeto_dvd/db/models.py`:
```python
"""Database tables."""

from datetime import datetime

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
```

`src/projeto_dvd/db/session.py`:
```python
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
```

`src/projeto_dvd/db/migrations/env.py`:
```python
"""Alembic environment.

No fileConfig() here: it would reset the uvicorn loggers when migrating at startup.
"""

from alembic import context
from sqlmodel import SQLModel, create_engine

from projeto_dvd.db import models  # noqa: F401 (registers the tables in the metadata)

url = context.config.get_main_option("sqlalchemy.url")
if url is None:
    raise RuntimeError("sqlalchemy.url is not set; use projeto_dvd.db.session.migrate()")

engine = create_engine(url)
with engine.connect() as connection:
    # Batch mode: SQLite cannot ALTER most things, so Alembic copies the table instead.
    context.configure(
        connection=connection,
        target_metadata=SQLModel.metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
```

`src/projeto_dvd/db/migrations/versions/0001_create_media_file.py`:
```python
"""Create the media_file table."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_file",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("folder", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mtime_ns", sa.Integer(), nullable=False),
        sa.Column("probe_json", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_media_file_folder", "media_file", ["folder"])
    op.create_index("ix_media_file_path", "media_file", ["path"], unique=True)


def downgrade() -> None:
    op.drop_table("media_file")
```

- [ ] **Step 9: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_db.py -v --no-cov`
Expected: 6 passed

- [ ] **Step 10: Full gate and commit**

Run: `make lint && make test`
Expected: ruff and mypy clean; all tests pass; coverage ≥ 90%.

```bash
git add pyproject.toml uv.lock src/projeto_dvd/config.py src/projeto_dvd/db tests/conftest.py tests/unit/test_config.py tests/unit/test_db.py
git commit -m "feat: add settings, media_file table and migrations"
```

(`docker-compose.yml`, the `data` volume and `/data` in the Dockerfile are part of Task 5, where the image changes.)

---

### Task 2: ffprobe reading and summary

**Files:**
- Create: `src/projeto_dvd/library/__init__.py`, `src/projeto_dvd/library/probe.py`
- Create: `tests/fixtures/make_fixtures.sh`, `tests/fixtures/probe/*.json` (generated), `tests/fixtures/probe/dv5_pgs.json` (by hand)
- Modify: `Makefile` (target `fixtures`)
- Create: `tests/unit/test_probe.py`

**Interfaces:**
- Produces:
  - `ffprobe_command(path: Path) -> list[str]`
  - `ProbeResult(json: str | None, error: str | None)` (frozen dataclass)
  - `FfprobeMissingError(Exception)`
  - `run_ffprobe(path: Path) -> ProbeResult` (raises `FfprobeMissingError`)
  - `Video(codec, width, height, fps: float | None, aspect: float | None, hdr: bool, dolby_vision_5: bool)`
  - `AudioTrack(language, channels, codec, title: str | None, default: bool, forced: bool)`
  - `SubtitleTrack(language, kind, codec, title: str | None, default: bool, forced: bool)`; `kind` in `"texto" | "imagem" | "desconhecido"`
  - `Summary(duration: float | None, video: Video | None, audio: tuple[AudioTrack, ...], subtitles: tuple[SubtitleTrack, ...], chapters: int, warnings: tuple[str, ...])`
  - `summarize(data: dict[str, Any]) -> Summary`
  - constants `READ_ERROR`, `NO_VIDEO`, `HDR`, `DOLBY_VISION_5`, `ABOVE_1080P`, `UNDEFINED_LANGUAGE`

- [ ] **Step 1: Write the fixture script**

`tests/fixtures/make_fixtures.sh`:
```sh
#!/bin/sh
# Regenerate the ffprobe JSON fixtures from short lavfi clips. Run inside the Docker image,
# which has the pinned ffmpeg:
#   make fixtures
# The clips are temporary; only the JSON files are committed.
#
# Hand-written fixture (Debian's ffmpeg has no encoder for these, so it cannot be generated):
#   dv5_pgs.json: Dolby Vision profile 5 video, TrueHD 7.1 audio and a PGS subtitle, following
#   the layout of ffprobe 7.1 output for such a file.
set -eu

out="$(realpath "${1:?usage: make_fixtures.sh OUTPUT_DIR}")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"

ff() { ffmpeg -nostdin -v error -y "$@"; }

printf '1\n00:00:00,500 --> 00:00:02,000\nOla\n' > sub.srt
printf ';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=2000\ntitle=Um\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=2000\nEND=4000\ntitle=Dois\n' > chapters.txt
ff -f lavfi -i testsrc=s=300x450 -frames:v 1 cover.jpg

# Scope movie: two audio tracks with languages, a forced text subtitle, chapters, cover art.
ff -f lavfi -i testsrc=s=1920x800:r=24000/1001:d=4 \
   -f lavfi -i sine=d=4:sample_rate=48000 -f lavfi -i sine=f=600:d=4:sample_rate=48000 \
   -i sub.srt -i chapters.txt \
   -map 0:v -map 1:a -map 2:a -map 3 -map_chapters 4 \
   -c:v libx264 -preset ultrafast -c:a:0 ac3 -ac:a:0 6 -c:a:1 aac -ac:a:1 2 -c:s srt \
   -metadata:s:a:0 language=por -metadata:s:a:1 language=eng -metadata:s:a:1 title=Comentario \
   -metadata:s:s:0 language=por -disposition:s:0 forced \
   -attach cover.jpg -metadata:s:t mimetype=image/jpeg -metadata:s:t filename=cover.jpg \
   movie.mkv

# Cover art stored as a video stream (attached_pic) after the real video.
ff -f lavfi -i testsrc=s=1280x720:r=25:d=2 -f lavfi -i sine=d=2 -i cover.jpg \
   -map 0 -map 1 -map 2 -c:v:0 libx264 -preset ultrafast -c:v:1 mjpeg \
   -disposition:v:1 attached_pic -c:a aac cover.mp4

# Audio with cover art only: no real video track.
ff -f lavfi -i sine=d=2 -i cover.jpg -map 0 -map 1 -c:a aac -c:v mjpeg \
   -disposition:v:0 attached_pic cover_only.mp4

# HDR10 in 4K (above 1080p).
ff -f lavfi -i testsrc=s=3840x2160:r=24:d=1 -c:v libx265 -preset ultrafast -pix_fmt yuv420p10le \
   -x265-params log-level=error:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc \
   hdr10.mkv

# HLG.
ff -f lavfi -i testsrc=s=1920x1080:r=24:d=1 -c:v libx265 -preset ultrafast -pix_fmt yuv420p10le \
   -x265-params log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc \
   hlg.mp4

# NTSC DVD-style MPEG-2: anamorphic 16:9, 29.97 fps, stereo AC-3 without a language tag.
ff -f lavfi -i testsrc=s=720x480:r=30000/1001:d=2 -f lavfi -i sine=d=2:sample_rate=48000 \
   -c:v mpeg2video -aspect 16:9 -c:a ac3 -ac 2 dvd.mpg

for clip in movie.mkv cover.mp4 cover_only.mp4 hdr10.mkv hlg.mp4 dvd.mpg; do
    ffprobe -v error -print_format json -show_format -show_streams -show_chapters "$clip" \
        > "$out/${clip%.*}.json"
done
```

Add to `Makefile` (and to `.PHONY`):
```make
# Regenerate tests/fixtures/probe/*.json with the ffmpeg pinned in the image.
fixtures:
	docker build -t projeto-dvd-fixtures .
	docker run --rm --network none -v "$(CURDIR)/tests/fixtures:/fixtures" \
		--user "$$(id -u):$$(id -g)" projeto-dvd-fixtures sh /fixtures/make_fixtures.sh /fixtures/probe
```

- [ ] **Step 2: Generate the fixtures and write the hand-made one**

Run: `mkdir -p tests/fixtures/probe && make fixtures && ls tests/fixtures/probe`
Expected: `cover.json cover_only.json dvd.json hdr10.json hlg.json movie.json` (the build reuses the Phase 0 cache).

`tests/fixtures/probe/dv5_pgs.json`:
```json
{
    "streams": [
        {
            "index": 0,
            "codec_name": "hevc",
            "codec_type": "video",
            "width": 3840,
            "height": 2160,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "16:9",
            "pix_fmt": "yuv420p10le",
            "r_frame_rate": "24000/1001",
            "avg_frame_rate": "24000/1001",
            "disposition": {"default": 1, "forced": 0, "attached_pic": 0},
            "tags": {"language": "eng"},
            "side_data_list": [
                {
                    "side_data_type": "DOVI configuration record",
                    "dv_version_major": 1,
                    "dv_version_minor": 0,
                    "dv_profile": 5,
                    "dv_level": 6,
                    "rpu_present_flag": 1,
                    "el_present_flag": 0,
                    "bl_present_flag": 1,
                    "dv_bl_signal_compatibility_id": 0
                }
            ]
        },
        {
            "index": 1,
            "codec_name": "truehd",
            "codec_type": "audio",
            "channels": 8,
            "channel_layout": "7.1",
            "disposition": {"default": 1, "forced": 0, "attached_pic": 0},
            "tags": {"language": "eng"}
        },
        {
            "index": 2,
            "codec_name": "hdmv_pgs_subtitle",
            "codec_type": "subtitle",
            "disposition": {"default": 0, "forced": 0, "attached_pic": 0},
            "tags": {"language": "por", "title": "Brazilian"}
        }
    ],
    "chapters": [],
    "format": {
        "filename": "dv5_pgs.mkv",
        "format_name": "matroska,webm",
        "duration": "7200.000000"
    }
}
```

- [ ] **Step 3: Write the failing tests**

`tests/unit/test_probe.py`:
```python
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library import probe
from projeto_dvd.library.probe import (
    ABOVE_1080P,
    DOLBY_VISION_5,
    HDR,
    NO_VIDEO,
    UNDEFINED_LANGUAGE,
    AudioTrack,
    FfprobeMissingError,
    ProbeResult,
    SubtitleTrack,
    ffprobe_command,
    run_ffprobe,
    summarize,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "probe"


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    return data


def video_stream(**fields: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "avg_frame_rate": "24000/1001",
        "r_frame_rate": "24000/1001",
        "display_aspect_ratio": "16:9",
    }
    stream.update(fields)
    return stream


def probe_data(*streams: dict[str, Any], duration: str | None = "60.0") -> dict[str, Any]:
    fmt = {} if duration is None else {"duration": duration}
    return {"streams": list(streams), "format": fmt, "chapters": []}


# ffprobe command and execution


def test_command_uses_the_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    command = ffprobe_command(Path("-weird.mkv"))

    assert command == [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(tmp_path / "-weird.mkv"),
    ]


def fake_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    raises: BaseException | None = None,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, **kwargs})
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(probe.subprocess, "run", run)
    return calls


def test_run_returns_the_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_run(monkeypatch, stdout='{"streams": []}')

    result = run_ffprobe(Path("/media/a.mkv"))

    assert result == ProbeResult(json='{"streams": []}', error=None)
    assert calls[0]["timeout"] == 60
    assert "shell" not in calls[0]


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"returncode": 1, "stderr": "a.mkv: Invalid data found\n"}, "a.mkv: Invalid data found"),
        ({"returncode": 1, "stderr": ""}, "ffprobe terminou com código 1"),
        ({"returncode": 1, "stderr": "x" * 600}, "x" * 500),
        ({"stdout": "not json"}, "ffprobe devolveu um JSON inválido"),
        (
            {"raises": subprocess.TimeoutExpired(["ffprobe"], 60)},
            "ffprobe não respondeu em 60 s",
        ),
    ],
    ids=["exit-code", "exit-code-silent", "truncated", "invalid-json", "timeout"],
)
def test_run_reports_errors(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], error: str
) -> None:
    fake_run(monkeypatch, **kwargs)

    assert run_ffprobe(Path("/media/a.mkv")) == ProbeResult(json=None, error=error)


def test_run_raises_when_ffprobe_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run(monkeypatch, raises=FileNotFoundError("ffprobe"))

    with pytest.raises(FfprobeMissingError):
        run_ffprobe(Path("/media/a.mkv"))


# Summary from real ffprobe output (fixtures)


def test_movie_summary() -> None:
    summary = summarize(fixture("movie"))

    assert summary.duration == pytest.approx(4.0, abs=0.1)
    assert summary.video is not None
    assert (summary.video.codec, summary.video.width, summary.video.height) == ("h264", 1920, 800)
    assert summary.video.fps == pytest.approx(23.976, abs=0.001)
    assert summary.video.aspect == pytest.approx(2.4)
    assert summary.video.hdr is False
    assert summary.audio == (
        AudioTrack(
            language="por", channels="5.1", codec="ac3", title=None, default=False, forced=False
        ),
        AudioTrack(
            language="eng",
            channels="estéreo",
            codec="aac",
            title="Comentario",
            default=False,
            forced=False,
        ),
    )
    assert summary.subtitles == (
        SubtitleTrack(
            language="por", kind="texto", codec="subrip", title=None, default=False, forced=True
        ),
    )
    assert summary.chapters == 2
    assert summary.warnings == ()


def test_cover_art_is_not_the_video_track() -> None:
    summary = summarize(fixture("cover"))

    assert summary.video is not None
    assert (summary.video.codec, summary.video.width) == ("h264", 1280)
    assert summary.audio[0].language == UNDEFINED_LANGUAGE  # "und" in the file
    assert summary.audio[0].channels == "mono"


def test_cover_only_means_no_video() -> None:
    summary = summarize(fixture("cover_only"))

    assert summary.video is None
    assert summary.warnings == (NO_VIDEO,)


def test_hdr10_in_4k() -> None:
    summary = summarize(fixture("hdr10"))

    assert summary.video is not None
    assert summary.video.hdr is True
    assert summary.warnings == (HDR, ABOVE_1080P)


def test_hlg_is_hdr() -> None:
    summary = summarize(fixture("hlg"))

    assert summary.video is not None
    assert summary.video.hdr is True
    assert summary.warnings == (HDR,)


def test_dvd_mpeg2() -> None:
    summary = summarize(fixture("dvd"))

    assert summary.video is not None
    assert summary.video.codec == "mpeg2video"
    assert summary.video.fps == pytest.approx(29.97, abs=0.001)
    assert summary.video.aspect == pytest.approx(16 / 9)
    assert summary.audio[0].language == UNDEFINED_LANGUAGE  # no tag at all
    assert summary.audio[0].channels == "estéreo"


def test_dolby_vision_profile_5_with_pgs() -> None:
    summary = summarize(fixture("dv5_pgs"))

    assert summary.video is not None
    assert summary.video.hdr is True
    assert summary.video.dolby_vision_5 is True
    assert summary.warnings == (HDR, DOLBY_VISION_5, ABOVE_1080P)
    assert summary.audio[0].channels == "7.1"
    assert summary.audio[0].default is True
    assert summary.subtitles[0].kind == "imagem"
    assert summary.subtitles[0].title == "Brazilian"


# Summary edge cases (small dicts)


def test_missing_values_do_not_break_the_summary() -> None:
    stream = video_stream(avg_frame_rate="0/0", r_frame_rate="0/0", display_aspect_ratio="0:1")

    summary = summarize(probe_data(stream, duration=None))

    assert summary.duration is None
    assert summary.video is not None
    assert summary.video.fps is None
    assert summary.video.aspect == pytest.approx(16 / 9)  # from the resolution
    assert summary.chapters == 0


def test_fps_falls_back_to_r_frame_rate() -> None:
    summary = summarize(probe_data(video_stream(avg_frame_rate="0/0", r_frame_rate="25/1")))

    assert summary.video is not None
    assert summary.video.fps == 25


def test_aspect_comes_from_the_sample_aspect_ratio_when_missing() -> None:
    stream = video_stream(width=720, height=480, sample_aspect_ratio="32:27")
    del stream["display_aspect_ratio"]

    summary = summarize(probe_data(stream))

    assert summary.video is not None
    assert summary.video.aspect == pytest.approx(16 / 9)


def test_garbage_values_are_unknown() -> None:
    stream = video_stream(avg_frame_rate="abc", r_frame_rate="", display_aspect_ratio="x")
    del stream["width"]

    summary = summarize(probe_data(stream, duration="N/A"))

    assert summary.duration is None
    assert summary.video is not None
    assert summary.video.fps is None
    assert summary.video.aspect is None


@pytest.mark.parametrize(
    ("fields", "label"),
    [
        ({"channel_layout": "5.1(side)", "channels": 6}, "5.1"),
        ({"channel_layout": "stereo", "channels": 2}, "estéreo"),
        ({"channel_layout": "quad", "channels": 4}, "quad"),
        ({"channels": 1}, "mono"),
        ({"channels": 2}, "estéreo"),
        ({"channels": 6}, "5.1"),
        ({"channels": 8}, "7.1"),
        ({"channels": 3}, "3 canais"),
        ({}, "?"),
    ],
)
def test_channel_labels(fields: dict[str, Any], label: str) -> None:
    summary = summarize(probe_data(video_stream(), {"codec_type": "audio", **fields}))

    assert summary.audio[0].channels == label


@pytest.mark.parametrize(
    ("tags", "language"),
    [({"language": "por"}, "por"), ({"language": "und"}, UNDEFINED_LANGUAGE), ({}, UNDEFINED_LANGUAGE)],
)
def test_language(tags: dict[str, str], language: str) -> None:
    summary = summarize(probe_data(video_stream(), {"codec_type": "audio", "tags": tags}))

    assert summary.audio[0].language == language


@pytest.mark.parametrize(
    ("codec", "kind"),
    [
        ("subrip", "texto"),
        ("ass", "texto"),
        ("mov_text", "texto"),
        ("webvtt", "texto"),
        ("hdmv_pgs_subtitle", "imagem"),
        ("dvd_subtitle", "imagem"),
        ("dvb_subtitle", "imagem"),
        ("xsub", "imagem"),
        ("eia_608", "desconhecido"),
    ],
)
def test_subtitle_kind(codec: str, kind: str) -> None:
    summary = summarize(probe_data(video_stream(), {"codec_type": "subtitle", "codec_name": codec}))

    assert summary.subtitles[0].kind == kind


@pytest.mark.parametrize(
    ("width", "height", "above"),
    [(1920, 1080, False), (1920, 800, False), (2048, 858, True), (1440, 1440, True)],
)
def test_above_1080p(width: int, height: int, above: bool) -> None:
    summary = summarize(probe_data(video_stream(width=width, height=height)))

    assert (ABOVE_1080P in summary.warnings) is above


def test_no_streams_at_all() -> None:
    summary = summarize({})

    assert summary.video is None
    assert summary.audio == ()
    assert summary.warnings == (NO_VIDEO,)
```

- [ ] **Step 4: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_probe.py -v --no-cov`
Expected: ERROR with `ModuleNotFoundError: No module named 'projeto_dvd.library'`

- [ ] **Step 5: Write `src/projeto_dvd/library/__init__.py` and `probe.py`**

`src/projeto_dvd/library/__init__.py`:
```python
"""Media library: input folders, ffprobe data and scanning."""
```

`src/projeto_dvd/library/probe.py`:
```python
"""Run ffprobe and turn its JSON into a summary for the library screens."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 60
ERROR_LIMIT = 500

# Warning texts shown in the UI (Portuguese).
READ_ERROR = "Não foi possível ler o arquivo"
NO_VIDEO = "Sem faixa de vídeo"
HDR = "HDR (precisa de conversão para SDR)"
DOLBY_VISION_5 = "Dolby Vision perfil 5 (conversão de cor a confirmar)"
ABOVE_1080P = "Acima de 1080p"

UNDEFINED_LANGUAGE = "não definido"

HDR_TRANSFERS = frozenset({"smpte2084", "arib-std-b67"})
DOVI_SIDE_DATA = "DOVI configuration record"
TEXT_SUBTITLES = frozenset({"subrip", "ass", "mov_text", "webvtt", "text"})
IMAGE_SUBTITLES = frozenset({"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"})
CHANNEL_LAYOUTS = {"mono": "mono", "stereo": "estéreo", "5.1": "5.1", "5.1(side)": "5.1", "7.1": "7.1"}
CHANNEL_COUNTS = {1: "mono", 2: "estéreo", 6: "5.1", 8: "7.1"}


class FfprobeMissingError(Exception):
    """ffprobe is not installed: the whole scan stops instead of marking every file."""


@dataclass(frozen=True)
class ProbeResult:
    json: str | None
    error: str | None


@dataclass(frozen=True)
class Video:
    codec: str
    width: int
    height: int
    fps: float | None
    aspect: float | None
    hdr: bool
    dolby_vision_5: bool


@dataclass(frozen=True)
class AudioTrack:
    language: str
    channels: str
    codec: str
    title: str | None
    default: bool
    forced: bool


@dataclass(frozen=True)
class SubtitleTrack:
    language: str
    kind: str  # "texto", "imagem" or "desconhecido"
    codec: str
    title: str | None
    default: bool
    forced: bool


@dataclass(frozen=True)
class Summary:
    duration: float | None
    video: Video | None
    audio: tuple[AudioTrack, ...]
    subtitles: tuple[SubtitleTrack, ...]
    chapters: int
    warnings: tuple[str, ...]


def ffprobe_command(path: Path) -> list[str]:
    # Absolute path, so a file named "-something.mkv" is never read as an option.
    return [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(path.absolute()),
    ]


def run_ffprobe(path: Path) -> ProbeResult:
    """Probe one file. ffprobe only reads the headers, so this is fast even for 50 GB files."""
    try:
        result = subprocess.run(
            ffprobe_command(path),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as error:
        raise FfprobeMissingError from error
    except subprocess.TimeoutExpired:
        return ProbeResult(json=None, error=f"ffprobe não respondeu em {TIMEOUT_SECONDS} s")
    if result.returncode != 0:
        message = result.stderr.strip() or f"ffprobe terminou com código {result.returncode}"
        return ProbeResult(json=None, error=message[:ERROR_LIMIT])
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError:
        return ProbeResult(json=None, error="ffprobe devolveu um JSON inválido")
    return ProbeResult(json=result.stdout, error=None)


def summarize(data: dict[str, Any]) -> Summary:
    """Summarize ffprobe JSON; missing or odd values become None or "?", never an error."""
    streams: list[dict[str, Any]] = data.get("streams", [])
    video_streams = [
        s
        for s in streams
        if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1
    ]
    video = _video(video_streams[0]) if video_streams else None
    return Summary(
        duration=_float(data.get("format", {}).get("duration")),
        video=video,
        audio=tuple(_audio(s) for s in streams if s.get("codec_type") == "audio"),
        subtitles=tuple(_subtitle(s) for s in streams if s.get("codec_type") == "subtitle"),
        chapters=len(data.get("chapters", [])),
        warnings=_warnings(video),
    )


def _video(stream: dict[str, Any]) -> Video:
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    dovi = [
        side
        for side in stream.get("side_data_list", [])
        if side.get("side_data_type") == DOVI_SIDE_DATA
    ]
    return Video(
        codec=stream.get("codec_name", "?"),
        width=width,
        height=height,
        fps=_ratio(stream.get("avg_frame_rate"), "/") or _ratio(stream.get("r_frame_rate"), "/"),
        aspect=_aspect(stream, width, height),
        hdr=stream.get("color_transfer") in HDR_TRANSFERS or bool(dovi),
        dolby_vision_5=any(side.get("dv_profile") == 5 for side in dovi),
    )


def _aspect(stream: dict[str, Any], width: int, height: int) -> float | None:
    display = _ratio(stream.get("display_aspect_ratio"), ":")
    if display is not None:
        return display
    if not width or not height:
        return None
    sample = _ratio(stream.get("sample_aspect_ratio"), ":") or 1.0
    return sample * width / height


def _audio(stream: dict[str, Any]) -> AudioTrack:
    return AudioTrack(
        language=_language(stream),
        channels=_channels(stream),
        codec=stream.get("codec_name", "?"),
        title=_tags(stream).get("title"),
        default=_disposition(stream, "default"),
        forced=_disposition(stream, "forced"),
    )


def _subtitle(stream: dict[str, Any]) -> SubtitleTrack:
    codec = stream.get("codec_name", "?")
    if codec in TEXT_SUBTITLES:
        kind = "texto"
    elif codec in IMAGE_SUBTITLES:
        kind = "imagem"
    else:
        kind = "desconhecido"
    return SubtitleTrack(
        language=_language(stream),
        kind=kind,
        codec=codec,
        title=_tags(stream).get("title"),
        default=_disposition(stream, "default"),
        forced=_disposition(stream, "forced"),
    )


def _warnings(video: Video | None) -> tuple[str, ...]:
    if video is None:
        return (NO_VIDEO,)
    warnings = []
    if video.hdr:
        warnings.append(HDR)
    if video.dolby_vision_5:
        warnings.append(DOLBY_VISION_5)
    if video.width > 1920 or video.height > 1080:
        warnings.append(ABOVE_1080P)
    return tuple(warnings)


def _channels(stream: dict[str, Any]) -> str:
    layout = stream.get("channel_layout")
    if layout:
        return CHANNEL_LAYOUTS.get(layout, layout)
    count = stream.get("channels")
    if isinstance(count, int):
        return CHANNEL_COUNTS.get(count, f"{count} canais")
    return "?"


def _language(stream: dict[str, Any]) -> str:
    language = _tags(stream).get("language")
    return UNDEFINED_LANGUAGE if not language or language == "und" else language


def _tags(stream: dict[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = stream.get("tags") or {}
    return tags


def _disposition(stream: dict[str, Any], name: str) -> bool:
    return bool(stream.get("disposition", {}).get(name) == 1)


def _ratio(value: str | None, separator: str) -> float | None:
    """'24000/1001' or '16:9' as a float; None for missing, zero or invalid values."""
    numerator, _, denominator = (value or "").partition(separator)
    try:
        top, bottom = float(numerator), float(denominator)
    except ValueError:
        return None
    return top / bottom if top and bottom else None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
```

- [ ] **Step 6: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_probe.py -v --no-cov`
Expected: all passed. If a fixture value differs from the test (e.g. the movie duration), check the JSON: the test is the spec, the fixture is real ffprobe output; never edit the JSON by hand except `dv5_pgs.json`.

- [ ] **Step 7: Full gate and commit**

Run: `make lint && make test`
Expected: clean; coverage of `library/probe.py` 100% (lines and branches).

```bash
git add Makefile src/projeto_dvd/library tests/fixtures tests/unit/test_probe.py
git commit -m "feat: read and summarize ffprobe output"
```

---

### Task 3: Folders, external subtitles and incremental scan

**Files:**
- Create: `src/projeto_dvd/library/files.py`, `src/projeto_dvd/library/scan.py`
- Create: `tests/unit/test_files.py`, `tests/unit/test_scan.py`, `tests/tree.py`

**Interfaces:**
- Consumes: `MediaFile` (Task 1), `ProbeResult`, `run_ffprobe`, `summarize`, `Summary`, `READ_ERROR` (Task 2), fixtures `session`, `engine` (Task 1)
- Produces:
  - `files.nfc(text: str) -> str`, `files.natural_key(text: str) -> tuple[tuple[int, str], ...]`
  - `files.list_disc_folders(media_dir: Path) -> dict[str, Path]` (NFC name → real path, natural order)
  - `files.ExternalSubtitle(name: str, language: str | None, image: bool)`
  - `files.VideoFile(path: str, absolute: Path, size: int, mtime_ns: int, subtitles: tuple[ExternalSubtitle, ...])`
  - `files.find_videos(media_dir: Path, folder: Path) -> list[VideoFile]`
  - `files.match_subtitles(filenames: list[str]) -> dict[str, tuple[ExternalSubtitle, ...]]`
  - `scan.Prober = Callable[[Path], ProbeResult]`
  - `scan.scan_folder(session: Session, media_dir: Path, name: str, folder: Path, probe: Prober) -> int` (number of files sent to ffprobe)
  - `scan.purge_missing_folders(session: Session, names: Iterable[str]) -> None`
  - `scan.Status` (StrEnum: `EMPTY="vazia"`, `NOT_SCANNED="não escaneada"`, `CHANGED="mudou"`, `WARNINGS="com avisos"`, `OK="ok"`)
  - `scan.FileView(video: VideoFile, summary: Summary | None, error: str | None)` with `.warnings: tuple[str, ...]`
  - `scan.FolderView(name: str, status: Status, files: tuple[FileView, ...], size: int, duration: float | None)` with `.warning_count: int`
  - `scan.folder_view(session: Session, media_dir: Path, name: str, folder: Path) -> FolderView`
  - `tests/tree.py: snapshot(root: Path) -> dict[str, tuple[int, int]]`

- [ ] **Step 1: Write the failing tests for `files.py`**

Create empty `tests/__init__.py` and `tests/unit/__init__.py`: with them pytest puts the project
root on `sys.path` and mypy sees `tests.tree` as a module, so tests can share helpers.

`tests/tree.py`:
```python
"""Helpers to build and compare folder trees in tests."""

import os
from pathlib import Path


def make_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Every entry under root (without following links): relative path -> (size, mtime_ns)."""
    entries: dict[str, tuple[int, int]] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in [*dirnames, *filenames]:
            path = Path(dirpath) / name
            stat = path.lstat()
            entries[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return entries
```

`tests/unit/test_files.py`:
```python
import os
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library.files import (
    ExternalSubtitle,
    find_videos,
    list_disc_folders,
    match_subtitles,
    natural_key,
)
from tests.tree import make_file

NOT_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")


def test_natural_order() -> None:
    names = ["S01E10.mkv", "S01E02.mkv", "s01e01.mkv", "Extra.mkv"]

    assert sorted(names, key=natural_key) == ["Extra.mkv", "s01e01.mkv", "S01E02.mkv", "S01E10.mkv"]


# Disc folders


def test_lists_immediate_subfolders_in_natural_order(tmp_path: Path) -> None:
    for name in ["Disco 10", "Disco 2", "Senhor dos Aneis"]:
        (tmp_path / name).mkdir()
    make_file(tmp_path / "solto.mkv")  # files at the root are ignored

    folders = list_disc_folders(tmp_path)

    assert list(folders) == ["Disco 2", "Disco 10", "Senhor dos Aneis"]
    assert folders["Disco 2"] == tmp_path / "Disco 2"


def test_missing_media_dir_has_no_folders(tmp_path: Path) -> None:
    assert list_disc_folders(tmp_path / "nao-montado") == {}


def test_symlinked_folder_is_ignored(tmp_path: Path) -> None:
    outside = tmp_path / "fora"
    outside.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    (media / "link").symlink_to(outside, target_is_directory=True)

    assert list_disc_folders(media) == {}


@NOT_ROOT
def test_unreadable_folder_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "ok").mkdir()
    locked = tmp_path / "System Volume Information"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        assert list(list_disc_folders(tmp_path)) == ["ok"]
    finally:
        locked.chmod(0o755)


def test_folder_names_are_nfc(tmp_path: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "Ação")
    (tmp_path / decomposed).mkdir()

    folders = list_disc_folders(tmp_path)

    assert list(folders) == ["Ação"]
    assert folders["Ação"] == tmp_path / decomposed  # the real path is kept for reading


# Videos


def test_finds_videos_recursively_with_stat(tmp_path: Path) -> None:
    disc = tmp_path / "Friends T1"
    make_file(disc / "Temporada 1" / "S01E10.mkv", b"12345")
    make_file(disc / "Temporada 1" / "S01E02.MP4")
    make_file(disc / "capa.jpg")
    make_file(disc / "Thumbs.db")
    make_file(disc / "info.nfo")

    videos = find_videos(tmp_path, disc)

    assert [v.path for v in videos] == [
        "Friends T1/Temporada 1/S01E02.MP4",
        "Friends T1/Temporada 1/S01E10.mkv",
    ]
    stat = (disc / "Temporada 1" / "S01E10.mkv").stat()
    assert (videos[1].size, videos[1].mtime_ns) == (5, stat.st_mtime_ns)
    assert videos[1].absolute == disc / "Temporada 1" / "S01E10.mkv"


@pytest.mark.parametrize("extension", [".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts"])
def test_video_extensions(tmp_path: Path, extension: str) -> None:
    make_file(tmp_path / "d" / f"a{extension.upper()}")

    assert len(find_videos(tmp_path, tmp_path / "d")) == 1


def test_symlinks_inside_a_disc_folder_are_ignored(tmp_path: Path) -> None:
    outside = make_file(tmp_path / "fora" / "segredo.mkv").parent
    disc = tmp_path / "media" / "d"
    make_file(disc / "real.mkv")
    (disc / "arquivo.mkv").symlink_to(outside / "segredo.mkv")
    (disc / "pasta").symlink_to(outside, target_is_directory=True)
    (disc / "laco").symlink_to(disc, target_is_directory=True)

    videos = find_videos(tmp_path / "media", disc)

    assert [v.path for v in videos] == ["d/real.mkv"]


def test_file_removed_before_stat_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_file(tmp_path / "d" / "a.mkv")
    make_file(tmp_path / "d" / "b.mkv")
    real_stat = Path.stat

    def stat(self: Path, **kwargs: Any) -> os.stat_result:
        if self.name == "a.mkv":
            raise FileNotFoundError(self)
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)

    assert [v.path for v in find_videos(tmp_path, tmp_path / "d")] == ["d/b.mkv"]


def test_video_paths_are_nfc(tmp_path: Path) -> None:
    make_file(tmp_path / "d" / unicodedata.normalize("NFD", "Coração.mkv"))

    assert find_videos(tmp_path, tmp_path / "d")[0].path == "d/Coração.mkv"


def test_external_subtitles_are_attached(tmp_path: Path) -> None:
    make_file(tmp_path / "d" / "Filme.mkv")
    make_file(tmp_path / "d" / "Filme.pt-BR.srt")

    video = find_videos(tmp_path, tmp_path / "d")[0]

    assert video.subtitles == (ExternalSubtitle(name="Filme.pt-BR.srt", language="pt-BR", image=False),)


# External subtitles (pure)


def test_subtitle_without_language() -> None:
    assert match_subtitles(["Filme.mkv", "Filme.srt"]) == {
        "Filme.mkv": (ExternalSubtitle(name="Filme.srt", language=None, image=False),)
    }


def test_subtitle_languages_and_kinds() -> None:
    result = match_subtitles(
        ["Filme.mkv", "Filme.en.forced.ass", "Filme.pt.sup", "Filme.pt-BR.ssa"]
    )

    assert result["Filme.mkv"] == (
        ExternalSubtitle(name="Filme.en.forced.ass", language="en.forced", image=False),
        ExternalSubtitle(name="Filme.pt.sup", language="pt", image=True),
        ExternalSubtitle(name="Filme.pt-BR.ssa", language="pt-BR", image=False),
    )


def test_idx_needs_its_sub() -> None:
    assert match_subtitles(["Filme.mkv", "Filme.idx"]) == {"Filme.mkv": ()}
    assert match_subtitles(["Filme.mkv", "Filme.IDX", "Filme.sub"]) == {
        "Filme.mkv": (ExternalSubtitle(name="Filme.IDX", language=None, image=True),)
    }


def test_longest_video_name_wins() -> None:
    result = match_subtitles(["Filme.mkv", "Filme.2.mkv", "Filme.2.pt-BR.srt", "Filme.pt.srt"])

    assert result == {
        "Filme.mkv": (ExternalSubtitle(name="Filme.pt.srt", language="pt", image=False),),
        "Filme.2.mkv": (ExternalSubtitle(name="Filme.2.pt-BR.srt", language="pt-BR", image=False),),
    }


def test_matching_ignores_case() -> None:
    result = match_subtitles(["Filme.mkv", "FILME.PT-BR.SRT"])

    assert result["Filme.mkv"] == (
        ExternalSubtitle(name="FILME.PT-BR.SRT", language="PT-BR", image=False),
    )


def test_same_name_videos_share_the_subtitle() -> None:
    result = match_subtitles(["Filme.mkv", "Filme.mp4", "Filme.srt"])

    assert result["Filme.mkv"] == result["Filme.mp4"] != ()


def test_unrelated_files_are_not_subtitles() -> None:
    assert match_subtitles(["Filme.mkv", "Outro.srt", "Filmes.srt", "Filme.nfo", "Filme.sub"]) == {
        "Filme.mkv": ()
    }


def test_subtitles_only_match_videos_in_the_same_folder(tmp_path: Path) -> None:
    make_file(tmp_path / "d" / "Filme.mkv")
    make_file(tmp_path / "d" / "legendas" / "Filme.srt")

    assert find_videos(tmp_path, tmp_path / "d")[0].subtitles == ()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_files.py -v --no-cov`
Expected: ERROR with `ModuleNotFoundError: No module named 'projeto_dvd.library.files'`

- [ ] **Step 3: Write `src/projeto_dvd/library/files.py`**

```python
"""Find disc folders, videos and external subtitles. Read-only: nothing here writes."""

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = frozenset({".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts"})
# .idx counts only next to its .sub (VobSub keeps the images in the .sub).
SUBTITLE_EXTENSIONS = frozenset({".srt", ".ass", ".ssa", ".sup", ".idx"})
IMAGE_SUBTITLE_EXTENSIONS = frozenset({".sup", ".idx"})


@dataclass(frozen=True)
class ExternalSubtitle:
    name: str
    language: str | None  # the middle part of the name, as is ("pt-BR", "en.forced")
    image: bool


@dataclass(frozen=True)
class VideoFile:
    path: str  # relative to the input folder, POSIX, NFC
    absolute: Path  # the real path, for reading
    size: int
    mtime_ns: int
    subtitles: tuple[ExternalSubtitle, ...] = ()


def nfc(text: str) -> str:
    # Accented names copied from Windows can arrive decomposed (NFD).
    return unicodedata.normalize("NFC", text)


def natural_key(text: str) -> tuple[tuple[int, str], ...]:
    """Sort key that puts S01E02 before S01E10, ignoring case."""
    return tuple(
        (int(part), "") if part.isdigit() else (0, part.casefold())
        for part in re.split(r"(\d+)", text)
    )


def list_disc_folders(media_dir: Path) -> dict[str, Path]:
    """Readable, non-link subfolders of the input folder: NFC name -> real path."""
    try:
        entries = list(os.scandir(media_dir))
    except OSError:
        return {}
    folders = {
        nfc(entry.name): Path(entry.path)
        for entry in entries
        if entry.is_dir(follow_symlinks=False) and _readable(entry.path)
    }
    return dict(sorted(folders.items(), key=lambda item: natural_key(item[0])))


def find_videos(media_dir: Path, folder: Path) -> list[VideoFile]:
    """Videos under a disc folder (recursive, links skipped), stat taken now, natural order."""
    videos = []
    for dirpath, _, filenames in os.walk(folder, followlinks=False):
        directory = Path(dirpath)
        names = [name for name in filenames if not (directory / name).is_symlink()]
        for name, subtitles in match_subtitles(names).items():
            absolute = directory / name
            try:
                stat = absolute.stat()
            except OSError:  # removed (or unreadable) since the listing
                continue
            videos.append(
                VideoFile(
                    path=nfc(absolute.relative_to(media_dir).as_posix()),
                    absolute=absolute,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    subtitles=subtitles,
                )
            )
    return sorted(videos, key=lambda video: natural_key(video.path))


def match_subtitles(filenames: list[str]) -> dict[str, tuple[ExternalSubtitle, ...]]:
    """Map each video in one folder to its external subtitles.

    A subtitle belongs to the video whose name (without extension) starts it, followed by a
    dot; when several videos match, only the longest name wins ("Filme.2.pt.srt" belongs to
    "Filme.2.mkv", not to "Filme.mkv").
    """
    lower_names = {name.lower() for name in filenames}
    stems = {
        name: Path(name).stem for name in filenames if Path(name).suffix.lower() in VIDEO_EXTENSIONS
    }
    result: dict[str, list[ExternalSubtitle]] = {name: [] for name in stems}
    for name in sorted(filenames, key=natural_key):
        suffix = Path(name).suffix.lower()
        if suffix not in SUBTITLE_EXTENSIONS:
            continue
        if suffix == ".idx" and Path(name).with_suffix(".sub").name.lower() not in lower_names:
            continue
        base = name[: -len(suffix)]
        matches = {
            video: stem
            for video, stem in stems.items()
            if base.lower() == stem.lower() or base.lower().startswith(stem.lower() + ".")
        }
        if not matches:
            continue
        longest = max(len(stem) for stem in matches.values())
        for video, stem in matches.items():
            if len(stem) == longest:
                language = base[len(stem) + 1 :]
                result[video].append(
                    ExternalSubtitle(
                        name=nfc(name),
                        language=nfc(language) or None,
                        image=suffix in IMAGE_SUBTITLE_EXTENSIONS,
                    )
                )
    return {video: tuple(subtitles) for video, subtitles in result.items()}


def _readable(path: str) -> bool:
    try:
        with os.scandir(path):
            return True
    except OSError:
        return False
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_files.py -v --no-cov`
Expected: all passed

- [ ] **Step 5: Write the failing tests for `scan.py`**

`tests/unit/test_scan.py`:
```python
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, select

from projeto_dvd.db.models import MediaFile
from projeto_dvd.library.probe import NO_VIDEO, READ_ERROR, FfprobeMissingError, ProbeResult
from projeto_dvd.library.scan import Status, folder_view, purge_missing_folders, scan_folder
from tests.tree import make_file, snapshot

NOT_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")

VIDEO_JSON = json.dumps(
    {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"codec_type": "audio", "codec_name": "ac3", "channels": 6},
        ],
        "format": {"duration": "3600.0"},
    }
)
AUDIO_ONLY_JSON = json.dumps({"streams": [], "format": {"duration": "60.0"}})


class FakeProbe:
    """Records which files were probed; answers with a fixed result per file name."""

    def __init__(self, results: dict[str, ProbeResult] | None = None) -> None:
        self.results = results or {}
        self.calls: list[str] = []

    def __call__(self, path: Path) -> ProbeResult:
        self.calls.append(path.name)
        return self.results.get(path.name, ProbeResult(json=VIDEO_JSON, error=None))


@pytest.fixture
def media(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    make_file(root / "Disco" / "a.mkv", b"aaa")
    make_file(root / "Disco" / "b.mkv", b"bbb")
    return root


def scan(session: Session, media: Path, probe: FakeProbe, name: str = "Disco") -> int:
    return scan_folder(session, media, name, media / name, probe)


def rows(session: Session) -> dict[str, MediaFile]:
    return {row.path: row for row in session.exec(select(MediaFile)).all()}


# Incremental scan


def test_first_scan_probes_every_video(session: Session, media: Path) -> None:
    probe = FakeProbe()

    assert scan(session, media, probe) == 2
    assert sorted(probe.calls) == ["a.mkv", "b.mkv"]
    saved = rows(session)["Disco/a.mkv"]
    assert (saved.folder, saved.size, saved.probe_json, saved.error) == ("Disco", 3, VIDEO_JSON, None)
    assert saved.mtime_ns == (media / "Disco" / "a.mkv").stat().st_mtime_ns


def test_second_scan_without_changes_does_not_probe(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    probe = FakeProbe()

    assert scan(session, media, probe) == 0
    assert probe.calls == []


def test_new_and_changed_files_are_probed(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    make_file(media / "Disco" / "c.mkv")
    (media / "Disco" / "a.mkv").write_bytes(b"changed")
    probe = FakeProbe()

    scan(session, media, probe)

    assert sorted(probe.calls) == ["a.mkv", "c.mkv"]
    assert rows(session)["Disco/a.mkv"].size == 7


def test_older_mtime_counts_as_a_change(session: Session, media: Path) -> None:
    # Windows Explorer keeps the original mtime when copying a file over another one.
    scan(session, media, FakeProbe())
    os.utime(media / "Disco" / "a.mkv", ns=(1, 1))
    probe = FakeProbe()

    scan(session, media, probe)

    assert probe.calls == ["a.mkv"]


def test_removed_files_leave_the_database(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    (media / "Disco" / "b.mkv").unlink()

    scan(session, media, FakeProbe())

    assert list(rows(session)) == ["Disco/a.mkv"]


def test_files_with_a_previous_error_are_probed_again(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe({"a.mkv": ProbeResult(json=None, error="boom")}))
    assert rows(session)["Disco/a.mkv"].error == "boom"
    probe = FakeProbe()

    scan(session, media, probe)

    assert probe.calls == ["a.mkv"]
    assert rows(session)["Disco/a.mkv"].error is None


def test_a_bad_file_does_not_stop_the_scan(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe({"a.mkv": ProbeResult(json=None, error="Invalid data")}))

    saved = rows(session)
    assert (saved["Disco/a.mkv"].probe_json, saved["Disco/a.mkv"].error) == (None, "Invalid data")
    assert saved["Disco/b.mkv"].probe_json == VIDEO_JSON


def test_file_growing_during_scan_is_probed_again_next_time(session: Session, media: Path) -> None:
    # The stat stored is the one taken before ffprobe: a copy still in progress looks changed.
    def growing(path: Path) -> ProbeResult:
        with path.open("ab") as file:
            file.write(b"more")
        return ProbeResult(json=VIDEO_JSON, error=None)

    scan_folder(session, media, "Disco", media / "Disco", growing)
    probe = FakeProbe()

    scan(session, media, probe)

    assert sorted(probe.calls) == ["a.mkv", "b.mkv"]


def test_file_removed_before_probing_is_skipped(session: Session, media: Path) -> None:
    def vanish(path: Path) -> ProbeResult:
        path.unlink()
        return ProbeResult(json=None, error="No such file or directory")

    scan_folder(session, media, "Disco", media / "Disco", vanish)

    assert rows(session) == {}


def test_missing_ffprobe_stops_the_scan_without_marking_files(
    session: Session, media: Path
) -> None:
    def missing(path: Path) -> ProbeResult:
        raise FfprobeMissingError

    with pytest.raises(FfprobeMissingError):
        scan_folder(session, media, "Disco", media / "Disco", missing)

    assert rows(session) == {}


def test_scan_only_touches_its_own_folder(session: Session, media: Path) -> None:
    make_file(media / "Outro" / "x.mkv")
    scan(session, media, FakeProbe(), name="Outro")

    scan(session, media, FakeProbe())

    assert sorted(rows(session)) == ["Disco/a.mkv", "Disco/b.mkv", "Outro/x.mkv"]


def test_rescan_updates_the_same_row(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    first_id = rows(session)["Disco/a.mkv"].id
    (media / "Disco" / "a.mkv").write_bytes(b"changed")

    scan(session, media, FakeProbe())

    assert rows(session)["Disco/a.mkv"].id == first_id
    assert len(rows(session)) == 2


def test_purge_removes_rows_of_folders_that_are_gone(session: Session, media: Path) -> None:
    make_file(media / "Outro" / "x.mkv")
    scan(session, media, FakeProbe())
    scan(session, media, FakeProbe(), name="Outro")

    purge_missing_folders(session, ["Disco"])

    assert sorted(rows(session)) == ["Disco/a.mkv", "Disco/b.mkv"]


# Read-only


def test_scan_never_writes_to_the_media_folder(session: Session, media: Path) -> None:
    make_file(media / "Disco" / "a.pt-BR.srt")
    before = snapshot(media)

    scan(session, media, FakeProbe())
    folder_view(session, media, "Disco", media / "Disco")

    assert snapshot(media) == before


@NOT_ROOT
def test_scan_works_on_a_read_only_folder(session: Session, media: Path) -> None:
    disc = media / "Disco"
    for file in disc.iterdir():
        file.chmod(0o444)
    disc.chmod(0o555)
    media.chmod(0o555)
    try:
        assert scan(session, media, FakeProbe()) == 2
    finally:
        media.chmod(0o755)
        disc.chmod(0o755)


# Status and view


def test_status_empty(session: Session, tmp_path: Path) -> None:
    make_file(tmp_path / "Vazia" / "Filme.srt")  # subtitles alone are not videos

    result = folder_view(session, tmp_path, "Vazia", tmp_path / "Vazia")

    assert result.status == Status.EMPTY
    assert result.files == ()


def test_status_not_scanned(session: Session, media: Path) -> None:
    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.NOT_SCANNED
    assert result.size == 6
    assert result.duration is None
    assert [f.summary for f in result.files] == [None, None]


def test_status_ok_with_total_duration(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())

    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.OK
    assert result.duration == 7200.0
    assert result.warning_count == 0


def test_status_with_warnings(session: Session, media: Path) -> None:
    scan(
        session,
        media,
        FakeProbe(
            {
                "a.mkv": ProbeResult(json=None, error="Invalid data"),
                "b.mkv": ProbeResult(json=AUDIO_ONLY_JSON, error=None),
            }
        ),
    )

    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.WARNINGS
    assert result.warning_count == 2
    assert [f.warnings for f in result.files] == [(READ_ERROR,), (NO_VIDEO,)]
    assert result.files[0].error == "Invalid data"


@pytest.mark.parametrize("change", ["added", "removed", "modified"])
def test_status_changed(session: Session, media: Path, change: str) -> None:
    scan(session, media, FakeProbe())
    if change == "added":
        make_file(media / "Disco" / "c.mkv")
    elif change == "removed":
        (media / "Disco" / "b.mkv").unlink()
    else:
        (media / "Disco" / "a.mkv").write_bytes(b"changed")

    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.CHANGED


def test_empty_folder_with_old_rows_has_changed(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    for file in (media / "Disco").iterdir():
        file.unlink()

    assert folder_view(session, media, "Disco", media / "Disco").status == Status.CHANGED


def test_duration_ignores_files_without_one(session: Session, media: Path) -> None:
    no_duration = json.dumps({"streams": [], "format": {}})
    scan(session, media, FakeProbe({"a.mkv": ProbeResult(json=no_duration, error=None)}))

    assert folder_view(session, media, "Disco", media / "Disco").duration == 3600.0


def test_rows_from_other_folders_do_not_leak(session: Session, media: Path) -> None:
    session.add(
        MediaFile(
            folder="Disco 2",
            path="Disco 2/a.mkv",
            size=1,
            mtime_ns=1,
            scanned_at=datetime.now(UTC),
        )
    )
    session.commit()

    assert folder_view(session, media, "Disco", media / "Disco").status == Status.NOT_SCANNED
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_scan.py -v --no-cov`
Expected: ERROR with `ModuleNotFoundError: No module named 'projeto_dvd.library.scan'`

- [ ] **Step 7: Write `src/projeto_dvd/library/scan.py`**

```python
"""Incremental scan of a disc folder and the view models of the library screens."""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from sqlmodel import Session, col, select

from projeto_dvd.db.models import MediaFile
from projeto_dvd.library.files import VideoFile, find_videos
from projeto_dvd.library.probe import READ_ERROR, ProbeResult, Summary, summarize

Prober = Callable[[Path], ProbeResult]


class Status(StrEnum):
    EMPTY = "vazia"
    NOT_SCANNED = "não escaneada"
    CHANGED = "mudou"
    WARNINGS = "com avisos"
    OK = "ok"


@dataclass(frozen=True)
class FileView:
    video: VideoFile
    summary: Summary | None  # None until scanned (or when ffprobe failed)
    error: str | None

    @property
    def warnings(self) -> tuple[str, ...]:
        if self.error is not None:
            return (READ_ERROR,)
        return self.summary.warnings if self.summary else ()


@dataclass(frozen=True)
class FolderView:
    name: str
    status: Status
    files: tuple[FileView, ...]
    size: int
    duration: float | None

    @property
    def warning_count(self) -> int:
        return sum(1 for file in self.files if file.warnings)


def scan_folder(session: Session, media_dir: Path, name: str, folder: Path, probe: Prober) -> int:
    """Probe new, changed and previously failed videos; drop rows of removed ones.

    Returns how many files were sent to ffprobe. Each file is committed on its own, so a long
    scan keeps what it already read if something stops it.
    """
    known = _rows(session, name)
    videos = find_videos(media_dir, folder)
    probed = 0
    for video in videos:
        row = known.get(video.path)
        if row is not None and row.error is None and _unchanged(row, video):
            continue
        result = probe(video.absolute)
        probed += 1
        if result.error is not None and not video.absolute.exists():
            continue  # removed while scanning
        row = row or MediaFile(folder=name, path=video.path, size=0, mtime_ns=0, scanned_at=_now())
        # The stat from before ffprobe: a file still being copied will look changed next time.
        row.size, row.mtime_ns = video.size, video.mtime_ns
        row.probe_json, row.error, row.scanned_at = result.json, result.error, _now()
        session.add(row)
        session.commit()
    current = {video.path for video in videos}
    for path, row in known.items():
        if path not in current:
            session.delete(row)
    session.commit()
    return probed


def purge_missing_folders(session: Session, names: Iterable[str]) -> None:
    """Delete rows of disc folders that no longer exist."""
    stale = select(MediaFile).where(col(MediaFile.folder).not_in(list(names)))
    for row in session.exec(stale).all():
        session.delete(row)
    session.commit()


def folder_view(session: Session, media_dir: Path, name: str, folder: Path) -> FolderView:
    """Everything the screens show about one disc folder. Only stat, never ffprobe."""
    rows = _rows(session, name)
    videos = find_videos(media_dir, folder)
    files = tuple(_file_view(video, rows.get(video.path)) for video in videos)
    durations = [f.summary.duration for f in files if f.summary and f.summary.duration is not None]
    return FolderView(
        name=name,
        status=_status(videos, rows, files),
        files=files,
        size=sum(video.size for video in videos),
        duration=sum(durations) if durations else None,
    )


def _status(videos: list[VideoFile], rows: dict[str, MediaFile], files: tuple[FileView, ...]) -> Status:
    if not videos and not rows:
        return Status.EMPTY
    if not rows:
        return Status.NOT_SCANNED
    current = {video.path: video for video in videos}
    if current.keys() != rows.keys() or not all(
        _unchanged(rows[path], video) for path, video in current.items()
    ):
        return Status.CHANGED
    if any(file.warnings for file in files):
        return Status.WARNINGS
    return Status.OK


def _file_view(video: VideoFile, row: MediaFile | None) -> FileView:
    if row is None:
        return FileView(video=video, summary=None, error=None)
    summary = summarize(json.loads(row.probe_json)) if row.probe_json else None
    return FileView(video=video, summary=summary, error=row.error)


def _rows(session: Session, name: str) -> dict[str, MediaFile]:
    query = select(MediaFile).where(MediaFile.folder == name)
    return {row.path: row for row in session.exec(query).all()}


def _unchanged(row: MediaFile, video: VideoFile) -> bool:
    # Equality, not "newer than": Explorer keeps the original mtime when copying.
    return row.size == video.size and row.mtime_ns == video.mtime_ns


def _now() -> datetime:
    return datetime.now(UTC)
```

- [ ] **Step 8: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_scan.py tests/unit/test_files.py -v --no-cov`
Expected: all passed

- [ ] **Step 9: Full gate and commit**

Run: `make lint && make test`
Expected: clean; `library/files.py` and `library/scan.py` at 100% lines and branches (no pragma).

```bash
git add src/projeto_dvd/library/files.py src/projeto_dvd/library/scan.py tests/__init__.py tests/unit/__init__.py tests/tree.py tests/unit/test_files.py tests/unit/test_scan.py
git commit -m "feat: scan disc folders incrementally"
```

---

### Task 4: Web screens

**Files:**
- Create: `src/projeto_dvd/api/__init__.py`, `src/projeto_dvd/api/health.py`, `src/projeto_dvd/api/formatting.py`, `src/projeto_dvd/api/library.py`
- Modify: `src/projeto_dvd/app.py` (factory)
- Create: `src/projeto_dvd/web/templates/base.html`, `library.html`, `folder.html`, `_folder_body.html`
- Delete: `src/projeto_dvd/web/templates/index.html`
- Create: `src/projeto_dvd/web/static/app.css`, `src/projeto_dvd/web/static/htmx.min.js` (downloaded)
- Modify: `tests/unit/test_app.py` (rewritten), Create: `tests/unit/test_formatting.py`, `tests/unit/test_library_routes.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `make_engine`, `migrate` (Task 1), `list_disc_folders`, `VideoFile` (Task 3), `scan_folder`, `folder_view`, `purge_missing_folders`, `Status`, `FolderView`, `FileView` (Task 3), `run_ffprobe`, `FfprobeMissingError`, `Video` (Task 2)
- Produces:
  - `projeto_dvd.app.create_app(settings: Settings | None = None) -> FastAPI` (state: `settings`, `engine`)
  - route names `library`, `folder`, `scan_folder`, `health`, `static`
  - `formatting.format_size(size: int) -> str`, `format_duration(seconds: float | None) -> str`, `format_fps(fps: float | None) -> str`, `format_aspect(ratio: float | None) -> str | None`, `video_label(video: Video) -> str`
  - `api.library._scan_lock: threading.Lock`

- [ ] **Step 1: Write the failing formatting tests**

`tests/unit/test_formatting.py`:
```python
import pytest

from projeto_dvd.api.formatting import (
    format_aspect,
    format_duration,
    format_fps,
    format_size,
    video_label,
)
from projeto_dvd.library.probe import Video


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (38_000_000_000, "38 GB"),
        (4_230_000_000, "4,2 GB"),
        (1_000_000_000, "1 GB"),
        (512_000_000, "512 MB"),
        (2_500, "2,5 KB"),
        (0, "0 KB"),
        (1_200_000_000_000, "1,2 TB"),
    ],
)
def test_format_size(size: int, text: str) -> None:
    assert format_size(size) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(10680, "2h58"), (3600, "1h00"), (2700, "45 min"), (20, "0 min"), (None, "?")],
)
def test_format_duration(seconds: float | None, text: str) -> None:
    assert format_duration(seconds) == text


@pytest.mark.parametrize(
    ("fps", "text"),
    [(24000 / 1001, "23,976"), (24.0, "24"), (30000 / 1001, "29,97"), (25.0, "25"), (None, "?")],
)
def test_format_fps(fps: float | None, text: str) -> None:
    assert format_fps(fps) == text


@pytest.mark.parametrize(
    ("ratio", "text"),
    [(16 / 9, None), (1.77, None), (None, None), (4 / 3, "1,33:1"), (2.4, "2,40:1")],
)
def test_format_aspect_hides_16_9(ratio: float | None, text: str | None) -> None:
    assert format_aspect(ratio) == text


def make_video(codec: str, width: int, height: int, fps: float | None = 24.0) -> Video:
    return Video(
        codec=codec, width=width, height=height, fps=fps, aspect=None, hdr=False, dolby_vision_5=False
    )


@pytest.mark.parametrize(
    ("video", "text"),
    [
        (make_video("h264", 1920, 800, 24000 / 1001), "1080p · H.264 · 23,976"),
        (make_video("hevc", 3840, 2160), "2160p · HEVC · 24"),
        (make_video("hevc", 2048, 858), "2048x858 · HEVC · 24"),
        (make_video("mpeg2video", 720, 480, 30000 / 1001), "720x480 · MPEG-2 · 29,97"),
        (make_video("h264", 1280, 720), "720p · H.264 · 24"),
        (make_video("vp9", 1920, 1080, None), "1080p · VP9 · ?"),
    ],
)
def test_video_label(video: Video, text: str) -> None:
    assert video_label(video) == text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_formatting.py -v --no-cov`
Expected: ERROR with `ModuleNotFoundError: No module named 'projeto_dvd.api'`

- [ ] **Step 3: Write `api/__init__.py` and `api/formatting.py`**

`src/projeto_dvd/api/__init__.py`:
```python
"""HTTP routes: HTML pages, HTMX fragments and the health check."""
```

`src/projeto_dvd/api/formatting.py`:
```python
"""Brazilian Portuguese formatting for the templates (Jinja filters)."""

from projeto_dvd.library.probe import Video

VIDEO_CODECS = {
    "h264": "H.264",
    "hevc": "HEVC",
    "mpeg2video": "MPEG-2",
    "mpeg4": "MPEG-4",
    "av1": "AV1",
    "vc1": "VC-1",
}
SIXTEEN_NINE = 16 / 9


def format_size(size: int) -> str:
    """Decimal units, like disc capacities (4,7 GB)."""
    for unit, factor in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if size >= factor:
            return f"{_decimal(size / factor)} {unit}"
    return f"{_decimal(size / 1e3)} KB"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours}h{minutes:02d}" if hours else f"{minutes} min"


def format_fps(fps: float | None) -> str:
    if fps is None:
        return "?"
    return f"{fps:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def format_aspect(ratio: float | None) -> str | None:
    """None for 16:9 (the common case is not shown) and for unknown ratios."""
    if ratio is None or abs(ratio - SIXTEEN_NINE) < 0.02:
        return None
    return f"{ratio:.2f}:1".replace(".", ",")


def video_label(video: Video) -> str:
    codec = VIDEO_CODECS.get(video.codec, video.codec.upper())
    return f"{_resolution(video.width, video.height)} · {codec} · {format_fps(video.fps)}"


def _resolution(width: int, height: int) -> str:
    # Scope movies are 1920 wide but less than 1080 high: the width decides.
    if width == 3840 or height == 2160:
        return "2160p"
    if width > 1920 or height > 1080 or width < 1280:
        return f"{width}x{height}"
    return "1080p" if width > 1280 or height > 720 else "720p"


def _decimal(value: float) -> str:
    text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
    return text.removesuffix(".0").replace(".", ",")
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_formatting.py -v --no-cov`
Expected: all passed

- [ ] **Step 5: Vendor HTMX**

Run:
```bash
mkdir -p src/projeto_dvd/web/static
curl -fsSL https://unpkg.com/htmx.org@2.0.11/dist/htmx.min.js -o src/projeto_dvd/web/static/htmx.min.js
sha256sum src/projeto_dvd/web/static/htmx.min.js
curl -fsS https://registry.npmjs.org/htmx.org/2.0.11 | python3 -c "import json,sys;print(json.load(sys.stdin)['dist']['integrity'])"
openssl dgst -sha512 -binary src/projeto_dvd/web/static/htmx.min.js | openssl base64 -A; echo
```
Expected: the file starts with `var htmx=`; note the sha256 for the README (Task 6). The npm integrity covers the package tarball, not this file, so it is only a sanity check that the version exists; the sha256 printed here is the one recorded.

- [ ] **Step 6: Write the failing route tests**

`tests/unit/test_app.py` (rewritten; health moved to `api/health.py`):
```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from projeto_dvd.api import health
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings

ALL_FOUND: dict[str, str | None] = {
    "ffmpeg": "7.1.5-0+deb13u1",
    "ffprobe": "7.1.5-0+deb13u1",
    "dvdauthor": "0.7.2",
    "spumux": "0.7.2",
    "xorriso": "1.5.6",
    "tsMuxeR": "2.7.0",
}


@pytest.fixture
def client(tmp_path: Path, database_url: str) -> TestClient:
    return TestClient(create_app(Settings(media_dir=tmp_path, database_url=database_url)))


def fake_versions(monkeypatch: pytest.MonkeyPatch, versions: dict[str, str | None]) -> None:
    monkeypatch.setattr(health, "detect_versions", lambda: versions)


def test_startup_migrates_an_empty_database(tmp_path: Path, database_url: str) -> None:
    app = create_app(Settings(media_dir=tmp_path, database_url=database_url))

    with TestClient(app):
        assert "media_file" in inspect(app.state.engine).get_table_names()


def test_default_settings_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))

    assert create_app().state.settings.media_dir == tmp_path


def test_health_returns_200_when_all_tools_are_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_versions(monkeypatch, ALL_FOUND)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "tools": ALL_FOUND}


def test_health_returns_503_with_null_for_a_missing_tool(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = {**ALL_FOUND, "tsMuxeR": None}
    fake_versions(monkeypatch, versions)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "missing", "tools": versions}


def test_health_returns_503_when_nothing_is_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions: dict[str, str | None] = dict.fromkeys(ALL_FOUND)
    fake_versions(monkeypatch, versions)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "missing", "tools": versions}


@pytest.mark.parametrize(
    ("path", "content"), [("/static/app.css", "--accent"), ("/static/htmx.min.js", "htmx")]
)
def test_static_files_are_served(client: TestClient, path: str, content: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert content in response.text
```

`tests/unit/test_library_routes.py`:
```python
import json
import re
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from projeto_dvd.api import library
from projeto_dvd.app import create_app
from projeto_dvd.config import Settings
from projeto_dvd.library.probe import FfprobeMissingError, ProbeResult
from tests.tree import make_file, snapshot

MOVIE_JSON = json.dumps(
    {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 800,
                "avg_frame_rate": "24000/1001",
                "display_aspect_ratio": "12:5",
            },
            {
                "codec_type": "audio",
                "codec_name": "ac3",
                "channel_layout": "5.1(side)",
                "tags": {"language": "por"},
            },
            {"codec_type": "audio", "codec_name": "aac", "channel_layout": "stereo"},
            {
                "codec_type": "subtitle",
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "por"},
            },
        ],
        "format": {"duration": "10680.0"},
        "chapters": [{}, {}, {}],
    }
)


@pytest.fixture
def media(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    make_file(root / "Senhor dos Aneis" / "A Sociedade do Anel.mkv", b"x" * 2000)
    make_file(root / "Senhor dos Aneis" / "A Sociedade do Anel.pt-BR.srt")
    return root


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake(path: Path) -> ProbeResult:
        calls.append(path.name)
        if path.name.startswith("ruim"):
            return ProbeResult(json=None, error="Invalid data found when processing input")
        return ProbeResult(json=MOVIE_JSON, error=None)

    monkeypatch.setattr(library, "run_ffprobe", fake)
    return calls


@pytest.fixture
def client(media: Path, database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(media_dir=media, database_url=database_url))) as client:
        yield client


def folder_url(name: str) -> str:
    return f"/folders/{quote(name)}"


# Library page


def test_library_lists_disc_folders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Senhor dos Aneis" in response.text
    assert "1 vídeo" in response.text
    assert "2 KB" in response.text
    assert "não escaneada" in response.text
    assert "escaneie para ver" in response.text


def test_library_shows_duration_after_scan(client: TestClient, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")

    response = client.get("/")

    assert "2h58" in response.text
    assert "escaneie para ver" not in response.text


def test_library_without_folders_shows_help(tmp_path: Path, database_url: str) -> None:
    app = create_app(Settings(media_dir=tmp_path / "vazio", database_url=database_url))
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "HOST_MEDIA_DIR" in response.text


def test_library_purges_rows_of_removed_folders(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    for file in (media / "Senhor dos Aneis").iterdir():
        file.unlink()
    (media / "Senhor dos Aneis").rmdir()
    client.get("/")
    make_file(media / "Senhor dos Aneis" / "A Sociedade do Anel.mkv", b"x" * 2000)

    response = client.get("/")

    assert "não escaneada" in response.text  # the old row is gone, not "mudou"


def test_folder_with_special_characters_opens_from_library_link(
    client: TestClient, media: Path
) -> None:
    make_file(media / "Ação #1? 100%" / "Filme.mkv")

    library_page = client.get("/").text
    links = re.findall(r'href="([^"]*/folders/[^"]*)"', library_page)
    link = next(link for link in links if "A%C3%A7%C3%A3o" in link)
    response = client.get(link)

    assert response.status_code == 200
    assert "Ação #1? 100%" in response.text


# Folder page


def test_folder_page_before_scan(client: TestClient) -> None:
    response = client.get(folder_url("Senhor dos Aneis"))

    assert response.status_code == 200
    assert "ainda não foi escaneada" in response.text
    assert 'hx-post="' in response.text


def test_scan_returns_the_table_fragment(client: TestClient, probes: list[str]) -> None:
    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert response.status_code == 200
    assert "<html" not in response.text
    assert probes == ["A Sociedade do Anel.mkv"]
    text = response.text
    assert "Scan concluído: 1 arquivo lido pelo ffprobe." in text
    assert "1080p · H.264 · 23,976" in text
    assert "2,40:1" in text
    assert "por 5.1" in text and "não definido estéreo" in text
    assert "2 (1 imagem)" in text  # PGS inside + external .srt
    assert "pt-BR" in text  # external subtitle in the details
    assert "2h58" in text


def test_second_scan_reports_nothing_read(client: TestClient, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert "Scan concluído: 0 arquivos lidos pelo ffprobe." in response.text
    assert probes == ["A Sociedade do Anel.mkv"]


def test_folder_page_after_scan_shows_the_table(client: TestClient, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")

    response = client.get(folder_url("Senhor dos Aneis"))

    assert "1080p · H.264 · 23,976" in response.text
    assert "Scan concluído" not in response.text


def test_unreadable_file_is_shown_with_its_error(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    make_file(media / "Senhor dos Aneis" / "ruim.mkv")

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert "Não foi possível ler o arquivo" in response.text
    assert "Invalid data found" in response.text
    assert "1 arquivo com aviso" in response.text


def test_changed_files_are_announced(client: TestClient, media: Path, probes: list[str]) -> None:
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    make_file(media / "Senhor dos Aneis" / "As Duas Torres.mkv")

    response = client.get(folder_url("Senhor dos Aneis"))

    assert "Arquivos mudaram desde o último scan" in response.text


def test_missing_ffprobe_shows_one_message(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(path: Path) -> ProbeResult:
        raise FfprobeMissingError

    monkeypatch.setattr(library, "run_ffprobe", missing)

    response = client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert response.status_code == 200
    assert "ffprobe não foi encontrado" in response.text
    assert "Não foi possível ler o arquivo" not in response.text


def test_scan_while_another_is_running_reports_it(client: TestClient, probes: list[str]) -> None:
    assert library._scan_lock.acquire(blocking=False)
    try:
        response = client.post(folder_url("Senhor dos Aneis") + "/scan")
    finally:
        library._scan_lock.release()

    assert "Já existe um scan em andamento" in response.text
    assert probes == []


def test_lock_is_released_after_an_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(path: Path) -> ProbeResult:
        raise FfprobeMissingError

    monkeypatch.setattr(library, "run_ffprobe", missing)
    client.post(folder_url("Senhor dos Aneis") + "/scan")

    assert not library._scan_lock.locked()


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "name",
    ["%2E%2E", "a%2Fb", "nao-existe", "solto.mkv", "link", "Senhor%20dos%20aneis"],
)
def test_unknown_folders_are_404(
    client: TestClient, media: Path, tmp_path: Path, method: str, name: str
) -> None:
    make_file(media / "solto.mkv")
    (tmp_path / "fora").mkdir()
    (media / "link").symlink_to(tmp_path / "fora", target_is_directory=True)
    url = f"/folders/{name}" + ("/scan" if method == "POST" else "")

    assert client.request(method, url).status_code == 404


def test_routes_never_write_to_the_media_folder(
    client: TestClient, media: Path, probes: list[str]
) -> None:
    before = snapshot(media)

    client.get("/")
    client.get(folder_url("Senhor dos Aneis"))
    client.post(folder_url("Senhor dos Aneis") + "/scan")
    client.get(folder_url("Senhor dos Aneis"))

    assert snapshot(media) == before
```

- [ ] **Step 7: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_app.py tests/unit/test_library_routes.py -v --no-cov`
Expected: ERROR with `ImportError: cannot import name 'health' from 'projeto_dvd.api'` (or `create_app`)

- [ ] **Step 8: Write the routes and the app factory**

`src/projeto_dvd/api/health.py`:
```python
"""Health check: media tool versions."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from projeto_dvd.tools import detect_versions

router = APIRouter()


@router.get("/health", name="health")
def health() -> JSONResponse:
    """Report media tool versions; 503 if any tool is missing (the image is broken)."""
    tools = detect_versions()
    ok = all(tools.values())
    return JSONResponse(
        {"status": "ok" if ok else "missing", "tools": tools},
        status_code=200 if ok else 503,
    )
```

`src/projeto_dvd/api/library.py`:
```python
"""Library pages: disc folders, one folder's files, and the scan."""

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from projeto_dvd.api.formatting import (
    format_aspect,
    format_duration,
    format_fps,
    format_size,
    video_label,
)
from projeto_dvd.config import Settings
from projeto_dvd.library.files import list_disc_folders
from projeto_dvd.library.probe import FfprobeMissingError, run_ffprobe
from projeto_dvd.library.scan import folder_view, purge_missing_folders, scan_folder

WEB_DIR = Path(__file__).parent.parent / "web"

router = APIRouter()
templates = Jinja2Templates(directory=WEB_DIR / "templates")
templates.env.filters.update(
    size=format_size,
    duration=format_duration,
    fps=format_fps,
    aspect=format_aspect,
    video_label=video_label,
)

# One scan at a time: ffprobe is heavy on a USB drive, and two scans of the same folder
# would race on the same rows.
_scan_lock = threading.Lock()

SCAN_RUNNING = "Já existe um scan em andamento. Aguarde ele terminar."
FFPROBE_MISSING = (
    "O ffprobe não foi encontrado, então nada foi lido. Confira as ferramentas em /health."
)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_media_dir(request: Request) -> Path:
    settings: Settings = request.app.state.settings
    return settings.media_dir


MediaDirDep = Annotated[Path, Depends(get_media_dir)]


def disc_folder(media_dir: MediaDirDep, name: str) -> Path:
    """The real path of a disc folder; 404 for anything that is not one (no traversal)."""
    folder = list_disc_folders(media_dir).get(name)
    if folder is None:
        raise HTTPException(status_code=404)
    return folder


FolderDep = Annotated[Path, Depends(disc_folder)]


@router.get("/", response_class=HTMLResponse, name="library")
def library_page(request: Request, session: SessionDep, media_dir: MediaDirDep) -> HTMLResponse:
    folders = list_disc_folders(media_dir)
    purge_missing_folders(session, folders)
    views = [folder_view(session, media_dir, name, path) for name, path in folders.items()]
    return templates.TemplateResponse(request, "library.html", {"folders": views})


@router.get("/folders/{name}", response_class=HTMLResponse, name="folder")
def folder_page(
    request: Request, name: str, folder: FolderDep, session: SessionDep, media_dir: MediaDirDep
) -> HTMLResponse:
    view = folder_view(session, media_dir, name, folder)
    return templates.TemplateResponse(request, "folder.html", {"folder": view})


@router.post("/folders/{name}/scan", response_class=HTMLResponse, name="scan_folder")
def scan(
    request: Request, name: str, folder: FolderDep, session: SessionDep, media_dir: MediaDirDep
) -> HTMLResponse:
    """Scan synchronously (sync route: runs in the thread pool) and return the folder body."""
    error = None
    probed = None
    if not _scan_lock.acquire(blocking=False):
        error = SCAN_RUNNING
    else:
        try:
            probed = scan_folder(session, media_dir, name, folder, run_ffprobe)
        except FfprobeMissingError:
            error = FFPROBE_MISSING
        finally:
            _scan_lock.release()
    view = folder_view(session, media_dir, name, folder)
    context = {"folder": view, "scan_error": error, "probed": probed}
    return templates.TemplateResponse(request, "_folder_body.html", context)
```

`src/projeto_dvd/app.py`:
```python
"""Web application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from projeto_dvd.api import health, library
from projeto_dvd.config import Settings
from projeto_dvd.db.session import make_engine, migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. uvicorn calls it with --factory; tests pass their own settings."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        migrate(settings.database_url)
        yield
        app.state.engine.dispose()

    app = FastAPI(title="projeto-dvd", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.mount("/static", StaticFiles(directory=library.WEB_DIR / "static"), name="static")
    app.include_router(health.router)
    app.include_router(library.router)
    return app
```

Delete `src/projeto_dvd/web/templates/index.html`.

- [ ] **Step 9: Write the templates**

`src/projeto_dvd/web/templates/base.html`:
```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Biblioteca{% endblock %} · projeto-dvd</title>
  <link rel="stylesheet" href="{{ url_for('static', path='app.css') }}">
  <script src="{{ url_for('static', path='htmx.min.js') }}" defer></script>
</head>
<body>
  <main class="page">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

`src/projeto_dvd/web/templates/library.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Biblioteca</h1>
{% if folders %}
<ul class="cards">
  {% for folder in folders %}
  <li>
    <a class="card" href="{{ url_for('folder', name=folder.name | urlencode) }}">
      <span class="card-title">
        <span class="folder-name">{{ folder.name }}</span>
        <span class="badge badge-{{ folder.status.name | lower }}">{{ folder.status }}</span>
      </span>
      <span class="muted numbers">
        {{ folder.files | length }} vídeo{{ "s" if folder.files | length != 1 }} · {{ folder.size | size }}
      </span>
      <span class="muted numbers">
        {% if folder.status.name in ("EMPTY", "NOT_SCANNED") %}escaneie para ver{% else %}{{ folder.duration | duration }}{% endif %}
      </span>
    </a>
  </li>
  {% endfor %}
</ul>
{% else %}
<section class="help">
  <h2>Nenhuma pasta encontrada</h2>
  <p>Crie uma subpasta para cada disco dentro da pasta de entrada e confira o
     <code>HOST_MEDIA_DIR</code> no arquivo <code>.env</code>. Exemplo:</p>
  <pre>entrada\
  Senhor dos Aneis\
    A Sociedade do Anel.mkv
    As Duas Torres.mkv
  Friends T1\
    S01E01.mkv</pre>
</section>
{% endif %}
{% endblock %}
```

`src/projeto_dvd/web/templates/folder.html`:
```html
{% extends "base.html" %}
{% block title %}{{ folder.name }}{% endblock %}
{% block content %}
<a class="back" href="{{ url_for('library') }}">← Biblioteca</a>
<header class="folder-header">
  <h1 class="folder-name">{{ folder.name }}</h1>
  <button class="primary" type="button"
          hx-post="{{ url_for('scan_folder', name=folder.name | urlencode) }}"
          hx-target="#folder-body" hx-swap="innerHTML"
          hx-disabled-elt="this" hx-sync="this:drop"
          hx-indicator="#folder-body, #scanning">Escanear</button>
  <span id="scanning" class="scanning">Escaneando... (pode levar alguns minutos)</span>
</header>
<div id="folder-body">
  {% include "_folder_body.html" %}
</div>
{% endblock %}
```

`src/projeto_dvd/web/templates/_folder_body.html`:
```html
<p class="muted numbers">
  {{ folder.files | length }} vídeo{{ "s" if folder.files | length != 1 }} · {{ folder.size | size }}{% if folder.duration is not none %} · {{ folder.duration | duration }}{% endif %}
</p>
{% if scan_error %}<p class="banner banner-error">{{ scan_error }}</p>{% endif %}
{% if probed is not none %}
<p class="banner banner-ok">Scan concluído: {{ probed }} arquivo{{ "s" if probed != 1 }} lido{{ "s" if probed != 1 }} pelo ffprobe.</p>
{% endif %}
{% if folder.status.name == "CHANGED" %}
<p class="banner banner-warning">Arquivos mudaram desde o último scan. Escaneie de novo.</p>
{% endif %}
{% if folder.warning_count %}
<p class="banner banner-warning">{{ folder.warning_count }} arquivo{{ "s" if folder.warning_count != 1 }} com aviso</p>
{% endif %}
{% if folder.status.name == "EMPTY" %}
<p class="empty">Nenhum vídeo nesta pasta.</p>
{% elif folder.status.name == "NOT_SCANNED" %}
<p class="empty">Esta pasta ainda não foi escaneada. O scan lê os dados técnicos de cada vídeo
   com o ffprobe, sem alterar os arquivos.</p>
{% else %}
<div class="table-wrap">
<table class="files">
  <thead>
    <tr>
      <th>Arquivo</th><th>Duração</th><th>Tamanho</th><th>Vídeo</th><th>Áudio</th>
      <th>Leg.</th><th>Cap.</th><th><span class="sr-only">Avisos</span></th>
    </tr>
  </thead>
  <tbody>
  {% for file in folder.files %}
    {% set name = file.video.path.split("/", 1)[1] %}
    {% if file.error is not none %}
    <tr class="row-error">
      <td>{{ name }}</td>
      <td colspan="7">Não foi possível ler o arquivo: {{ file.error }}</td>
    </tr>
    {% elif file.summary is none %}
    <tr>
      <td>{{ name }}</td>
      <td colspan="2" class="numbers">{{ file.video.size | size }}</td>
      <td colspan="5" class="muted">ainda não escaneado</td>
    </tr>
    {% else %}
    {% set s = file.summary %}
    {% set external = file.video.subtitles %}
    {% set images = (s.subtitles | selectattr("kind", "equalto", "imagem") | list | length) + (external | selectattr("image") | list | length) %}
    {% set subtitle_count = (s.subtitles | length) + (external | length) %}
    <tr>
      <td>
        <details>
          <summary>{{ name }}</summary>
          <ul class="tracks">
            {% for track in s.audio %}
            <li>Áudio: {{ track.language }} {{ track.channels }} · {{ track.codec }}{% if track.title %} · {{ track.title }}{% endif %}{% if track.default %} · padrão{% endif %}{% if track.forced %} · forçada{% endif %}</li>
            {% endfor %}
            {% for track in s.subtitles %}
            <li>Legenda: {{ track.language }} · {{ track.kind }} · {{ track.codec }}{% if track.title %} · {{ track.title }}{% endif %}{% if track.default %} · padrão{% endif %}{% if track.forced %} · forçada{% endif %}</li>
            {% endfor %}
            {% for sub in external %}
            <li>Legenda externa: {{ sub.language or "não definido" }} · {{ "imagem" if sub.image else "texto" }} · {{ sub.name }}</li>
            {% endfor %}
            {% for warning in file.warnings %}
            <li class="warning-text">⚠ {{ warning }}</li>
            {% endfor %}
          </ul>
        </details>
      </td>
      <td class="numbers">{{ s.duration | duration }}</td>
      <td class="numbers">{{ file.video.size | size }}</td>
      <td class="numbers">
        {% if s.video %}{{ s.video | video_label }}{% set aspect = s.video.aspect | aspect %}{% if aspect %} · {{ aspect }}{% endif %}{% if s.video.hdr %} <span class="badge badge-warnings">HDR</span>{% endif %}{% else %}sem vídeo{% endif %}
      </td>
      <td>
        {% if s.audio %}{{ s.audio | length }} faixa{{ "s" if s.audio | length != 1 }}: {% for track in s.audio %}{{ track.language }} {{ track.channels }}{{ ", " if not loop.last }}{% endfor %}{% else %}nenhum{% endif %}
      </td>
      <td class="numbers">{{ subtitle_count }}{% if images %} ({{ images }} imagem){% endif %}</td>
      <td class="numbers">{{ s.chapters }}</td>
      <td>{% if file.warnings %}<span class="warning-icon" title="{{ file.warnings | join(', ') }}">⚠</span>{% endif %}</td>
    </tr>
    {% endif %}
  {% endfor %}
  </tbody>
</table>
</div>
{% endif %}
```

Note: in Jinja, `{% set %}` inside `{% if %}` within a `for` loop is scoped to the loop iteration, which is what the template needs.

- [ ] **Step 10: Write `src/projeto_dvd/web/static/app.css`**

```css
/* projeto-dvd: dark "movie theater" theme. Colors as variables; no build step. */
:root {
  --bg: #121212;
  --surface: #1c1c1e;
  --border: #2c2c2e;
  --text: #ececec;
  --muted: #9a9a9a;
  --accent: #e0a526;
  --ok: #4caf50;
  --warning: #e0a526;
  --error: #e5534b;
  --radius: 8px;
  color-scheme: dark;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

h1 { font-size: 1.8rem; margin: 0 0 16px; }
h2 { font-size: 1.2rem; margin: 0 0 8px; }
a { color: var(--text); }
code, pre { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; }

.folder-name { font-family: Georgia, serif; }
.muted { color: var(--muted); }
.numbers { font-variant-numeric: tabular-nums; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* Library cards */
.cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 100%;
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-decoration: none;
}

.card:hover { border-color: var(--muted); }

.card-title {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 8px;
  font-size: 1.15rem;
}

/* Status badges: "mudou" stands out more than "ok" because it asks for action. */
.badge {
  flex: none;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  font: 600 0.75rem/1.6 system-ui, sans-serif;
  color: var(--muted);
  white-space: nowrap;
}

.badge-ok { color: var(--ok); border-color: var(--ok); }
.badge-warnings { color: var(--warning); border-color: var(--warning); }
.badge-changed { color: var(--bg); background: var(--warning); border-color: var(--warning); }

.help {
  max-width: 560px;
  margin: 48px auto;
  padding: 24px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.help pre {
  padding: 12px;
  background: var(--bg);
  border-radius: var(--radius);
  color: var(--muted);
  overflow-x: auto;
}

/* Folder page */
.back { color: var(--muted); text-decoration: none; }
.back:hover { color: var(--text); }

.folder-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin: 8px 0;
}

.folder-header h1 { margin: 0; flex: 1 1 auto; }

button.primary {
  padding: 8px 20px;
  border: 0;
  border-radius: var(--radius);
  background: var(--accent);
  color: #121212;
  font: 600 1rem system-ui, sans-serif;
  cursor: pointer;
}

button.primary[disabled] { opacity: 0.5; cursor: progress; }

/* HTMX adds .htmx-request to the indicators while the scan runs. */
.scanning { display: none; color: var(--muted); }
.scanning.htmx-request { display: inline; }
#folder-body.htmx-request { opacity: 0.4; transition: opacity 0.2s; }

.banner {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 4px solid var(--muted);
  background: var(--surface);
  border-radius: 0 var(--radius) var(--radius) 0;
}

.banner-ok { border-color: var(--ok); }
.banner-warning { border-color: var(--warning); }
.banner-error { border-color: var(--error); }

.empty { margin: 32px 0; color: var(--muted); }

/* File table: scrolls sideways on narrow screens instead of squeezing. */
.table-wrap { overflow-x: auto; margin-top: 16px; }

.files {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.95rem;
}

.files th,
.files td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.files th { color: var(--muted); font-weight: 600; white-space: nowrap; }
.files td.numbers { white-space: nowrap; }

.files summary { cursor: pointer; }
.tracks { margin: 8px 0 0; padding-left: 16px; color: var(--muted); font-size: 0.85rem; }

.row-error td { background: rgba(229, 83, 75, 0.12); }
.row-error td:first-child { border-left: 4px solid var(--error); }

.warning-icon, .warning-text { color: var(--warning); }
```

- [ ] **Step 11: Run the route tests**

Run: `uv run pytest tests/unit/test_app.py tests/unit/test_library_routes.py -v --no-cov`
Expected: all passed. If a template assertion fails, read the rendered HTML (`print(response.text)`) before changing anything; the test texts come from the spec.

- [ ] **Step 12: Update the Dockerfile command for the factory**

In `Dockerfile`, change the last line to:
```dockerfile
CMD ["uvicorn", "projeto_dvd.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```
(The image is rebuilt and checked in Task 5.)

- [ ] **Step 13: Look at the screens in the browser**

Run:
```bash
mkdir -p /tmp/claude-1000/entrada-demo/"Senhor dos Aneis" /tmp/claude-1000/entrada-demo/"Friends T1"
MEDIA_DIR=/tmp/claude-1000/entrada-demo DATABASE_URL=sqlite:////tmp/claude-1000/demo.db \
  uv run uvicorn projeto_dvd.app:create_app --factory --port 8001
```
Expected: `http://127.0.0.1:8001/` shows the two cards on the dark theme; the folder page opens; "Escanear" disables while running. Take screenshots for the designer review at the checkpoint. Stop the server afterwards.

- [ ] **Step 14: Full gate and commit**

Run: `make lint && make test`
Expected: clean; coverage ≥ 90%.

```bash
git add -A src/projeto_dvd tests/unit Dockerfile
git commit -m "feat: add library and folder screens"
```

---

### Task 5: Docker and CI

**Files:**
- Modify: `Dockerfile` (stages `runtime` and `test`, `/data`)
- Modify: `.dockerignore` (`!tests`)
- Modify: `docker-compose.yml` (`target: runtime`, volume `data`)
- Modify: `Makefile` (`test-slow`)
- Modify: `.github/workflows/ci.yml` (slow tests in the image, bigger smoke test)
- Create: `tests/integration/__init__.py` (empty), `tests/integration/test_media.py`

**Interfaces:**
- Consumes: `make_fixtures.sh` (Task 2), `summarize`, `run_ffprobe` (Task 2), `scan_folder`, `folder_view`, `Status` (Task 3), `session` fixture (Task 1)
- Produces: image stages `runtime` and `test`; `make test-slow`

- [ ] **Step 1: Write the slow integration tests**

`tests/integration/test_media.py`:
```python
"""Real ffmpeg/ffprobe: run inside the Docker image (make test-slow)."""

import json
import subprocess
from pathlib import Path

import pytest
from sqlmodel import Session

from projeto_dvd.library.probe import READ_ERROR, run_ffprobe, summarize
from projeto_dvd.library.scan import Status, folder_view, scan_folder
from tests.tree import make_file

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).parent.parent / "fixtures"
GENERATED = ["movie", "cover", "cover_only", "hdr10", "hlg", "dvd"]


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("probe")
    subprocess.run(["sh", str(FIXTURES / "make_fixtures.sh"), str(out)], check=True)
    return out


@pytest.mark.parametrize("name", GENERATED)
def test_committed_fixtures_match_the_image_ffprobe(regenerated: Path, name: str) -> None:
    committed = json.loads((FIXTURES / "probe" / f"{name}.json").read_text())
    fresh = json.loads((regenerated / f"{name}.json").read_text())

    assert summarize(fresh) == summarize(committed)


def test_scan_end_to_end(session: Session, tmp_path: Path) -> None:
    media = tmp_path / "media"
    disc = media / "Disco Teste"
    disc.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=s=1280x720:r=25:d=2",
            "-f", "lavfi", "-i", "sine=d=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "ac3",
            str(disc / "Filme.mkv"),
        ],
        check=True,
    )  # fmt: skip
    make_file(disc / "quebrado.mkv", b"not a video")

    probed = scan_folder(session, media, "Disco Teste", disc, run_ffprobe)
    view = folder_view(session, media, "Disco Teste", disc)

    assert probed == 2
    assert view.status == Status.WARNINGS
    good, broken = view.files
    assert good.summary is not None and good.summary.video is not None
    assert good.summary.video.width == 1280
    assert good.summary.duration == pytest.approx(2, abs=0.1)
    assert broken.warnings == (READ_ERROR,)
    assert broken.error is not None and "Invalid data" in broken.error
```

- [ ] **Step 2: Stage the Dockerfile**

Full `Dockerfile`:
```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime

# Media toolchain. Versions are pinned on purpose: when Debian ships a security update the
# build breaks, so every toolchain upgrade is a deliberate, reviewed commit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dvdauthor=0.7.2-3 \
        ffmpeg=7:7.1.5-0+deb13u1 \
        xorriso=1.5.6-1.2+b1 \
    && rm -rf /var/lib/apt/lists/*

# tsMuxeR (Blu-ray muxing) is not packaged by Debian. The release is a static binary,
# pinned by checksum.
ADD --checksum=sha256:ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987 \
    https://github.com/justdan96/tsMuxer/releases/download/2.7.0/tsMuxer-2.7.0-linux.zip \
    /tmp/tsmuxer.zip
RUN python -I -m zipfile -e /tmp/tsmuxer.zip /usr/local/bin/ \
    && chmod 755 /usr/local/bin/tsMuxeR \
    && rm /tmp/tsmuxer.zip

COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 \
    /uv /usr/local/bin/uv

# Same UID/GID as the default WSL user, so files written to /work and /output belong to it.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" app && useradd --uid "${UID}" --gid "${GID}" --create-home app \
    # The SQLite database lives in the "data" volume; a new volume copies this owner.
    && mkdir /data && chown app:app /data

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
CMD ["uvicorn", "projeto_dvd.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# Test stage: the runtime image plus dev dependencies and the tests, for the slow tests
# that need the real media toolchain. Never shipped.
FROM runtime AS test
USER root
RUN uv sync --frozen
COPY tests ./tests
USER app
CMD ["pytest", "-m", "slow", "--no-cov", "-p", "no:cacheprovider"]
```

`.dockerignore` (add `!tests`):
```
# Allowlist: only what the image needs. Keeps .env, media files and caches out of the
# build context by default. tests/ is used only by the "test" stage.
*
!pyproject.toml
!uv.lock
!README.md
!src
!tests
**/__pycache__
```

`docker-compose.yml`:
```yaml
services:
  web:
    build:
      context: .
      target: runtime
    ports:
      # Local only: the app has no authentication and can read the media drive.
      - "127.0.0.1:8000:8000"
    # The host folders must exist before "up": if one is missing, Docker creates it owned
    # by root and the app (uid 1000) cannot write there. Docker Desktop ignores
    # create_host_path: false, so this is documented in .env.example instead.
    volumes:
      - ${HOST_MEDIA_DIR:?set HOST_MEDIA_DIR in .env}:/media:ro
      - ${HOST_WORK_DIR:?set HOST_WORK_DIR in .env}:/work
      - ${HOST_OUTPUT_DIR:?set HOST_OUTPUT_DIR in .env}:/output
      - data:/data

volumes:
  # SQLite database (the scan cache). Survives rebuilds; "docker compose down -v" erases it.
  data:
```

`Makefile` (full):
```make
.PHONY: dev test test-slow lint format fixtures

dev:
	docker compose up --build

test:
	uv run pytest

# Integration tests with the real media toolchain, inside the image, without network.
test-slow:
	docker build --target test -t projeto-dvd-test .
	docker run --rm --network none projeto-dvd-test

lint:
	uv run ruff check
	uv run ruff format --check
	uv run mypy

format:
	uv run ruff format
	uv run ruff check --fix

# Regenerate tests/fixtures/probe/*.json with the ffmpeg pinned in the image.
fixtures:
	docker build --target runtime -t projeto-dvd-fixtures .
	docker run --rm --network none -v "$(CURDIR)/tests/fixtures:/fixtures" \
		--user "$$(id -u):$$(id -g)" projeto-dvd-fixtures sh /fixtures/make_fixtures.sh /fixtures/probe
```

- [ ] **Step 3: Run the slow tests in the image**

Run: `make test-slow`
Expected: `7 passed` (6 fixture comparisons + end-to-end). A fixture mismatch means the committed JSON was made with a different ffmpeg: run `make fixtures` and inspect the diff before committing.

Also run: `make test` (local, not slow)
Expected: green; the slow tests are deselected.

- [ ] **Step 4: Update the CI workflow**

Full `.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  quality:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v7
      # Third-party action pinned by commit SHA (tags can be moved).
      - uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78 # v7.6.0
        with:
          version: "0.13.1"
      - run: uv sync --frozen
      - run: make lint
      - run: make test

  docker:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v7

      - name: Compose refuses to start without host paths
        run: |
          if out=$(docker compose config 2>&1); then
            echo "docker-compose.yml must require the HOST_* variables"
            exit 1
          fi
          echo "$out" | grep -q "set HOST_MEDIA_DIR in .env"

      - name: Integration tests inside the image (no network)
        run: make test-slow

      - name: Create test environment
        run: |
          mkdir -p "/tmp/ci/media/Disco Teste" /tmp/ci/work /tmp/ci/output
          echo "not a video" > "/tmp/ci/media/Disco Teste/x.mkv"
          # The app runs as uid 1000 and the runner user is 1001: hand the folders over.
          sudo chown 1000:1000 /tmp/ci/work /tmp/ci/output
          printf 'HOST_MEDIA_DIR=/tmp/ci/media\nHOST_WORK_DIR=/tmp/ci/work\nHOST_OUTPUT_DIR=/tmp/ci/output\n' > .env

      - name: Build and start (waits for the healthcheck)
        run: docker compose up -d --build --wait --wait-timeout 120

      - name: Smoke test
        run: |
          curl -fsS http://127.0.0.1:8000/ -o index.html
          grep -q "Disco Teste" index.html
          curl -fsS -X POST "http://127.0.0.1:8000/folders/Disco%20Teste/scan" -o scan.html
          grep -q "Não foi possível ler o arquivo" scan.html
          curl -fsS http://127.0.0.1:8000/static/app.css | grep -q -- "--accent"
          curl -fsS http://127.0.0.1:8000/health -o health.json
          cat health.json
          jq -e '.status == "ok" and ([.tools[]] | length == 6 and all(. != null))' health.json
          # Assign first: a failing command inside $(...) passed to test would not stop the step.
          uid="$(docker compose exec -T web id -u)"
          test "$uid" -ne 0
          docker compose exec -T web touch /work/ci-check /output/ci-check /data/ci-check
          # The input folder must be read-only inside the container.
          if docker compose exec -T web touch /media/ci-check; then
            echo "/media is writable"
            exit 1
          fi

      - name: Show logs on failure
        if: failure()
        run: docker compose logs || true
```

- [ ] **Step 5: Run the smoke test locally**

Run (same steps as CI, with a scratch folder):
```bash
S=/tmp/claude-1000/ci && mkdir -p "$S/media/Disco Teste" "$S/work" "$S/output"
echo "not a video" > "$S/media/Disco Teste/x.mkv"
cp .env .env.bak 2>/dev/null || true
printf "HOST_MEDIA_DIR=$S/media\nHOST_WORK_DIR=$S/work\nHOST_OUTPUT_DIR=$S/output\n" > .env
docker compose up -d --build --wait --wait-timeout 120
curl -fsS http://127.0.0.1:8000/ | grep -c "Disco Teste"
curl -fsS -X POST "http://127.0.0.1:8000/folders/Disco%20Teste/scan" | grep -c "Não foi possível ler o arquivo"
docker compose exec -T web touch /data/ci-check && echo data-ok
docker compose exec -T web touch /media/ci-check || echo media-read-only
docker compose down -v
mv .env.bak .env 2>/dev/null || rm .env
```
Expected: counts ≥ 1, `data-ok`, `media-read-only` (touch prints "Read-only file system"). **Ask Vini before overwriting an existing `.env`** (the commands above back it up and restore it).

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml Makefile .github/workflows/ci.yml tests/integration
git commit -m "ci: run integration tests inside the image and extend the smoke test"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md`, `README.pt-BR.md`, `.env.example`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above (paths, variables, make targets, the HTMX sha256 from Task 4 Step 5)

- [ ] **Step 1: `.env.example`**

Full file:
```sh
# Copy to .env and adjust. Paths are on the WSL side and are mounted by docker compose.
# Create the work and output folders before the first "docker compose up" (mkdir -p): a
# missing folder is created by Docker owned by root, and the app cannot write there.

# Input folder: one subfolder per disc (e.g. "Senhor dos Aneis" with the three movies).
# Mounted read-only at /media: the app never changes the originals. It can live on C: or on
# the external drive; copying 30 to 50 GB movies to C: takes space.
HOST_MEDIA_DIR=/mnt/c/Users/your-user/Videos/entrada

# Intermediate files (encodes can need more than 100 GB for a BD-50).
# Keep this on the WSL ext4 filesystem, never under /mnt/c: it is much faster.
HOST_WORK_DIR=/home/your-user/projeto-dvd-work

# Final .iso and PDF files. A Windows folder makes burning and printing easy.
HOST_OUTPUT_DIR=/mnt/c/Users/your-user/Videos/projeto-dvd
```

- [ ] **Step 2: `README.md` and `README.pt-BR.md`**

Changes (both languages, kept in sync; show Vini the full files):
- Status: "Phase 1 (library)": lists each disc folder of the input folder and reads the technical data of its videos with ffprobe.
- New section "How the input folder works" / "Como funciona a pasta de entrada" with the tree from the spec and the rule "one subfolder = one disc".
- Stack: "Jinja2, HTMX and a small hand-written CSS (no build step)"; SQLite with SQLModel and Alembic.
- Running locally without Docker: `MEDIA_DIR=... DATABASE_URL=sqlite:///./projeto_dvd.db uv run uvicorn projeto_dvd.app:create_app --factory`.
- Development table: add `make test-slow` and `make fixtures`.
- Maintenance: HTMX 2.0.11 vendored at `src/projeto_dvd/web/static/htmx.min.js`, sha256 `<value from Task 4 Step 5>`, source `https://unpkg.com/htmx.org@2.0.11/dist/htmx.min.js`.
- `docker compose down -v` erases the scan cache (the `data` volume), never the media.

- [ ] **Step 3: `CLAUDE.md`**

- 3.1: one input folder with one subfolder per disc; video and subtitle extensions; incremental by `(path, size, mtime_ns)`.
- 5.3: the input folder can be on `C:` or on the external drive, mounted `ro`.
- 6: Frontend row becomes "Jinja2 + HTMX + CSS próprio (sem build; reavaliar no editor de menus, Fase 4)"; Mídia row unchanged.
- 6.1: `MEDIA_DIR=/media` replaces `MEDIA_ROOTS`; `DATABASE_URL` (Fase 1); `WORK_DIR` and `OUTPUT_DIR` move to Fase 3.
- 6.2: stages `runtime`/`test`, volume `data`, `make test-slow`, `make fixtures`.
- 7.1: `MediaFile` with raw `probe_json`, no `SourceFolder` and no track tables yet.
- 7.2: Biblioteca without match and filters until Fase 2; tela da pasta.
- 12: Fase 1 checked; roadmap order note "Ordem de execução: 1 → 3 → 2 → 4 → 5 → 6 → 7 → 8 (aprovada em 2026-10-15)", with the Fase 3 entry moved before Fase 2 and its "pronto" split: ISO validated in VLC now; physical player test pending until the burner is bought.
- 14: state of the session (PR number, next step: Fase 3 brainstorm).
- 15: the items of the spec section "Para o Log de decisões", plus the plan decisions of this file (scan count on screen, `--factory`, roadmap order, own CSS).

- [ ] **Step 4: Gate and commit**

Run: `make lint && make test`
Expected: green.

```bash
git add README.md README.pt-BR.md .env.example CLAUDE.md
git commit -m "docs: document the phase 1 library"
```

- [ ] **Step 5: Final review and PR (after Vini's ok)**

Final whole-branch review (fresh reviewer), then `superpowers:finishing-a-development-branch`. Push and PR only with Vini's confirmation; PR body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
