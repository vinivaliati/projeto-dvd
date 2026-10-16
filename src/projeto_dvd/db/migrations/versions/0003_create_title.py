"""Create the title table (TMDB matches)."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "title",
        sa.Column("media_file_id", sa.Integer(), sa.ForeignKey("media_file.id"), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("episode_end", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("poster_path", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("tmdb_json", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("title")
