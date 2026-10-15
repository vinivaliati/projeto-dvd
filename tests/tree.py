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
