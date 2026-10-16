"""Create disc_project and convert the phase 3 job plans to disc plans.

The conversion works on plain dicts, never on the app models, so later model changes cannot
break it. Jobs still queued or running were made for the old pipeline and are failed. The
downgrade drops the table and does not convert the plans back.
"""

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

OLD_JOB = "Job criado numa versão anterior; gere de novo."
TITLE_KEYS = (
    "path", "video_index", "size", "mtime_ns", "duration", "mode", "top_field_first", "aspect",
    "width", "height", "scale", "hd_color", "audio", "subtitles", "chapters",
)  # fmt: skip
DISC_KEYS = (
    "folder", "profile", "video_kbps", "maxrate_kbps", "estimated_bytes", "confirmed_low",
    "replace_existing", "volume", "iso_name",
)  # fmt: skip


def upgrade() -> None:
    op.create_table(
        "disc_project",
        sa.Column("folder", sa.String(), primary_key=True),
        sa.Column("choices_json", sa.String(), nullable=False),
    )
    connection = op.get_bind()
    jobs = connection.execute(sa.text("SELECT id, plan_json FROM job")).all()
    for job_id, plan_json in jobs:
        plan = json.dumps(convert(json.loads(plan_json)))
        update = sa.text("UPDATE job SET plan_json = :plan WHERE id = :id")
        connection.execute(update, {"plan": plan, "id": job_id})
    connection.execute(
        sa.text(
            "UPDATE job SET status = 'failed', error = :error, finished_at = CURRENT_TIMESTAMP"
            " WHERE status IN ('queued', 'running')"
        ),
        {"error": OLD_JOB},
    )


def downgrade() -> None:
    op.drop_table("disc_project")


def convert(old: dict[str, Any]) -> dict[str, Any]:
    if "titles" in old:
        return old
    title = {key: old[key] for key in TITLE_KEYS}
    title["audio_map"] = list(range(len(old["audio"])))
    title["subtitle_map"] = list(range(len(old["subtitles"])))
    title["menu_name"] = old["folder"]
    disc = {key: old[key] for key in DISC_KEYS}
    return {**disc, "subtitle_on": 1 if old["subtitle_on"] else 0, "titles": [title], "menu": None}
