"""Encoded video kept between jobs, to resume a job or rebuild a disc without encoding again.

Each entry is the MPEG-2 video of one title after both passes and the pulldown, hard linked
from the job folder (the cache and the jobs share WORK_DIR, so a link is atomic and costs no
copy), next to a JSON with its size and the progress of the second pass (the QA reads it).
The key is the second-pass command itself, so any change in the encode makes a new key. Only
the worker evicts: it knows which entries the running job needs.
"""

import contextlib
import hashlib
import json
import os
import re
from collections.abc import Collection
from pathlib import Path

from projeto_dvd.encode import mpeg2
from projeto_dvd.encode.video import video_pass_command
from projeto_dvd.jobs.runner import RunResult
from projeto_dvd.planner.disc_plan import DiscPlan

NAME = re.compile(r"^[0-9a-f]{64}\.(m2v|json)$")
KEPT_PROGRESS = ("frame", "dup_frames", "drop_frames", "out_time_us")


def cache_dir(work_dir: Path) -> Path:
    return work_dir / "cache"


def cache_key(disc: DiscPlan, number: int, ffmpeg_version: str | None) -> str:
    title = disc.titles[number - 1]
    fields = {
        "source": [title.path, title.size, title.mtime_ns],
        # Fixed paths: the same encode in another job folder is the same video.
        "command": video_pass_command(disc, number, Path("/media") / title.path, Path("/job"), 2),
        "pulldown": mpeg2.PULLDOWN_VERSION,
        "ffmpeg": ffmpeg_version,
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def plan_keys(disc: DiscPlan, ffmpeg_version: str | None) -> list[str]:
    return [cache_key(disc, n, ffmpeg_version) for n in range(1, len(disc.titles) + 1)]


def lookup(work_dir: Path, key: str, target: Path) -> RunResult | None:
    """Link the cached video to `target`; None when there is no usable entry."""
    video, meta = _paths(work_dir, key)
    try:
        info = json.loads(meta.read_text())
        if video.stat().st_size != info["size"]:
            return None
        target.unlink(missing_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(video, target)
        os.utime(video)  # the last use, for the eviction
        return RunResult({k: str(v) for k, v in info["progress"].items()}, "")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def store(work_dir: Path, key: str, m2v: Path, pass2: RunResult) -> None:
    """Keep the job's video; OSError goes to the caller (the job goes on without cache)."""
    video, meta = _paths(work_dir, key)
    video.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileExistsError):
        os.link(m2v, video)
    progress = {k: pass2.progress[k] for k in KEPT_PROGRESS if k in pass2.progress}
    meta.write_text(json.dumps({"size": video.stat().st_size, "progress": progress}))


def cache_bytes(work_dir: Path) -> int:
    return sum(path.stat().st_size for path in _entries(work_dir, ".m2v"))


def evict(work_dir: Path, limit_bytes: int, keep: Collection[str]) -> int:
    """Delete the least recently used videos until the cache fits; returns the bytes freed."""
    videos = sorted(_entries(work_dir, ".m2v"), key=lambda path: path.stat().st_mtime)
    total = sum(path.stat().st_size for path in videos)
    freed = 0
    for video in videos:
        if total - freed <= limit_bytes:
            break
        if video.stem in keep:
            continue
        freed += video.stat().st_size
        _remove(work_dir, video.stem)
    return freed


def purge(work_dir: Path, keys: Collection[str]) -> None:
    """Forget the videos of a disc that failed the QA, so a retry encodes them again."""
    for key in keys:
        _remove(work_dir, key)


def clean(work_dir: Path) -> int:
    """Delete every cache file, and nothing else: only regular files with a cache name."""
    removed = 0
    folder = cache_dir(work_dir)
    if not folder.is_dir():
        return 0
    with os.scandir(folder) as entries:
        for item in entries:
            if NAME.match(item.name) and item.is_file(follow_symlinks=False):
                os.unlink(item.path)
                removed += 1
    return removed


def _paths(work_dir: Path, key: str) -> tuple[Path, Path]:
    folder = cache_dir(work_dir)
    return folder / f"{key}.m2v", folder / f"{key}.json"


def _entries(work_dir: Path, suffix: str) -> list[Path]:
    folder = cache_dir(work_dir)
    if not folder.is_dir():
        return []
    return [
        path
        for path in folder.iterdir()
        if NAME.match(path.name) and path.suffix == suffix and not path.is_symlink()
    ]


def _remove(work_dir: Path, key: str) -> None:
    for path in _paths(work_dir, key):
        path.unlink(missing_ok=True)
