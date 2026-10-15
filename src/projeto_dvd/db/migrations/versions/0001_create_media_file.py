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
