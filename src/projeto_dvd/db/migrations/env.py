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
