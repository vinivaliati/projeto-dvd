import os
from pathlib import Path

import pytest

from projeto_dvd.jobs.files import clean_job_dir, job_dir, log_tail, temporary_bytes
from tests.tree import make_file


def test_clean_keeps_only_the_log(tmp_path: Path) -> None:
    root = job_dir(tmp_path, 3)
    make_file(root / "job.log", b"log")
    make_file(root / "disc.iso", b"x" * 1000)
    make_file(root / "dvd" / "VIDEO_TS" / "VTS_01_1.VOB", b"y" * 500)
    outside = make_file(tmp_path / "outside.txt", b"keep")
    os.symlink(outside, root / "link")

    assert temporary_bytes(tmp_path, 3) == 1500
    assert clean_job_dir(tmp_path, 3) == 1500

    assert sorted(p.name for p in root.iterdir()) == ["job.log"]
    assert outside.read_bytes() == b"keep"


def test_missing_folder_has_nothing_to_clean(tmp_path: Path) -> None:
    assert temporary_bytes(tmp_path, 9) == 0
    assert clean_job_dir(tmp_path, 9) == 0
    assert log_tail(tmp_path, 9) == ""


def test_log_tail(tmp_path: Path) -> None:
    make_file(job_dir(tmp_path, 1) / "job.log", "\n".join(f"l{i}" for i in range(500)).encode())

    tail = log_tail(tmp_path, 1, lines=3)

    assert tail == "l497\nl498\nl499"


def test_job_dir_must_stay_inside_work(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        job_dir(tmp_path, -1)


def test_job_folder_that_is_a_link_outside_work_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    make_file(outside / "precious.mkv")
    (tmp_path / "work" / "jobs").mkdir(parents=True)
    os.symlink(outside, tmp_path / "work" / "jobs" / "5")

    with pytest.raises(ValueError):
        clean_job_dir(tmp_path / "work", 5)

    assert (outside / "precious.mkv").exists()
