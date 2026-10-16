"""The job folders in WORK_DIR/jobs/<id>: size, cleanup and the log."""

import os
import shutil
from collections import deque
from pathlib import Path

LOG = "job.log"


def job_dir(work_dir: Path, job_id: int) -> Path:
    if job_id < 0:
        raise ValueError("invalid job id")
    return work_dir / "jobs" / str(job_id)


def temporary_bytes(work_dir: Path, job_id: int) -> int:
    root = job_dir(work_dir, job_id)
    if not root.is_dir():
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if path != root / LOG and not path.is_symlink():
                total += path.stat().st_size
    return total


def clean_job_dir(work_dir: Path, job_id: int) -> int:
    """Delete everything but the log; links are removed, never followed."""
    root = job_dir(work_dir, job_id)
    if not root.is_dir():
        return 0
    if not root.resolve().is_relative_to((work_dir / "jobs").resolve()):
        raise ValueError("job folder outside the work folder")
    freed = temporary_bytes(work_dir, job_id)
    for entry in os.scandir(root):
        if entry.name == LOG:
            continue
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path)
        else:
            os.unlink(entry.path)
    return freed


def log_tail(work_dir: Path, job_id: int, lines: int = 200) -> str:
    path = job_dir(work_dir, job_id) / LOG
    if not path.is_file():
        return ""
    with path.open(errors="replace") as log:
        return "\n".join(line.rstrip("\n") for line in deque(log, maxlen=lines))
