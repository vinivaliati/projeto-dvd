import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from projeto_dvd.config import Settings
from projeto_dvd.encode import mpeg2
from projeto_dvd.jobs import cache
from projeto_dvd.jobs.runner import RunResult
from tests.plans import make_disc_plan, make_title_plan

PASS2 = RunResult({"frame": "100", "dup_frames": "0", "drop_frames": "0",
                   "out_time_us": "4000000", "speed": "2x"}, "stderr")  # fmt: skip


def key(**changes: object) -> str:
    plan = make_disc_plan(**changes)
    return cache.cache_key(plan, 1, "7.1")


def test_the_key_follows_what_changes_the_video() -> None:
    base = key()
    assert key(video_kbps=5000) != base
    assert key(maxrate_kbps=8000) != base
    other = make_title_plan(aspect="4:3")
    assert key(titles=(other, make_title_plan(path="Série/S01E02.mkv"))) != base
    assert cache.cache_key(make_disc_plan(), 1, "7.2") != base
    moved = make_title_plan(mtime_ns=999)
    assert key(titles=(moved, make_title_plan(path="Série/S01E02.mkv"))) != base


def test_the_key_ignores_the_menu_order_and_chapters(monkeypatch: pytest.MonkeyPatch) -> None:
    base = key()
    assert key(menu=None) == base
    swapped = (make_title_plan(chapters=(0.0,)), make_title_plan(path="Série/X.mkv"))
    assert key(titles=swapped) == base
    monkeypatch.setattr(mpeg2, "PULLDOWN_VERSION", 99)
    assert key() != base


def write_m2v(path: Path, data: bytes = b"\x00\x00\x01\xb3video") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_store_then_lookup_links_the_video(tmp_path: Path) -> None:
    m2v = write_m2v(tmp_path / "job" / "title1.m2v")
    cache.store(tmp_path, "a" * 64, m2v, PASS2)
    target = write_m2v(tmp_path / "job2" / "title1.m2v", b"stale")

    result = cache.lookup(tmp_path, "a" * 64, target)

    assert result is not None
    kept = ("frame", "dup_frames", "drop_frames", "out_time_us")
    assert result.progress == {k: PASS2.progress[k] for k in kept}
    assert target.read_bytes() == m2v.read_bytes()
    assert target.stat().st_nlink == 3  # the job, the cache and the second job


def test_store_twice_is_harmless(tmp_path: Path) -> None:
    m2v = write_m2v(tmp_path / "job" / "title1.m2v")
    cache.store(tmp_path, "a" * 64, m2v, PASS2)
    cache.store(tmp_path, "a" * 64, m2v, PASS2)
    assert cache.cache_bytes(tmp_path) == m2v.stat().st_size


@pytest.mark.parametrize("damage", ["no json", "bad json", "wrong size", "no video"])
def test_a_damaged_entry_is_a_miss(tmp_path: Path, damage: str) -> None:
    m2v = write_m2v(tmp_path / "job" / "title1.m2v")
    cache.store(tmp_path, "b" * 64, m2v, PASS2)
    folder = cache.cache_dir(tmp_path)
    if damage == "no json":
        (folder / f"{'b' * 64}.json").unlink()
    elif damage == "bad json":
        (folder / f"{'b' * 64}.json").write_text("{")
    elif damage == "wrong size":
        (folder / f"{'b' * 64}.json").write_text(json.dumps({"size": 1, "progress": {}}))
    else:
        (folder / f"{'b' * 64}.m2v").unlink()

    assert cache.lookup(tmp_path, "b" * 64, tmp_path / "job2" / "t.m2v") is None


def entry(tmp_path: Path, name: str, size: int, age: int) -> None:
    m2v = write_m2v(tmp_path / "src" / f"{name}.m2v", b"x" * size)
    cache.store(tmp_path, name * 64, m2v, PASS2)
    os.utime(cache.cache_dir(tmp_path) / f"{name * 64}.m2v", (age, age))


def test_evict_removes_the_least_recently_used_first(tmp_path: Path) -> None:
    for name, age in (("1", 100), ("2", 300), ("3", 200)):
        entry(tmp_path, name, 10, age)

    freed = cache.evict(tmp_path, 20, keep=())

    left = sorted(p.name[0] for p in cache.cache_dir(tmp_path).glob("*.m2v"))
    assert (freed, left) == (10, ["2", "3"])
    assert not (cache.cache_dir(tmp_path) / f"{'1' * 64}.json").exists()


def test_evict_keeps_the_running_job(tmp_path: Path) -> None:
    entry(tmp_path, "1", 10, 100)
    entry(tmp_path, "2", 10, 300)

    cache.evict(tmp_path, 0, keep=("1" * 64,))

    assert [p.name[0] for p in cache.cache_dir(tmp_path).glob("*.m2v")] == ["1"]


def test_evict_without_a_cache_folder(tmp_path: Path) -> None:
    assert cache.evict(tmp_path, 0, keep=()) == 0
    assert cache.cache_bytes(tmp_path) == 0
    assert cache.clean(tmp_path) == 0


def test_lookup_refreshes_the_last_use(tmp_path: Path) -> None:
    entry(tmp_path, "1", 10, 100)
    entry(tmp_path, "2", 10, 200)

    cache.lookup(tmp_path, "1" * 64, tmp_path / "job" / "t.m2v")
    cache.evict(tmp_path, 10, keep=())

    assert [p.name[0] for p in cache.cache_dir(tmp_path).glob("*.m2v")] == ["1"]


def test_clean_removes_only_cache_files(tmp_path: Path) -> None:
    entry(tmp_path, "1", 10, 100)
    folder = cache.cache_dir(tmp_path)
    (folder / "notas.txt").write_text("fica")
    outside = write_m2v(tmp_path / "fora.m2v")
    (folder / f"{'c' * 64}.m2v").symlink_to(outside)

    removed = cache.clean(tmp_path)

    assert removed == 2
    assert sorted(p.name for p in folder.iterdir()) == ["c" * 64 + ".m2v", "notas.txt"]
    assert outside.exists()


def test_plan_keys_cover_every_title() -> None:
    plan = make_disc_plan()
    assert cache.plan_keys(plan, "7.1") == [cache.cache_key(plan, n, "7.1") for n in (1, 2)]


def test_purge_removes_the_entries_of_a_plan(tmp_path: Path) -> None:
    entry(tmp_path, "1", 10, 100)
    entry(tmp_path, "2", 10, 100)

    cache.purge(tmp_path, ["1" * 64, "9" * 64])

    assert [p.name[0] for p in cache.cache_dir(tmp_path).glob("*.m2v")] == ["2"]


def test_the_cache_limit_cannot_be_negative(tmp_path: Path) -> None:
    assert Settings(cache_limit_gb=0).cache_limit_gb == 0
    with pytest.raises(ValidationError):
        Settings(cache_limit_gb=-1)


def test_the_key_does_not_depend_on_the_position_of_the_title() -> None:
    a, b = make_title_plan(), make_title_plan(path="Série/S01E02.mkv")

    first = cache.cache_key(make_disc_plan(titles=(a, b)), 1, "7.1")
    moved = cache.cache_key(make_disc_plan(titles=(b, a)), 2, "7.1")

    assert first == moved


def test_a_folder_with_a_cache_name_is_not_an_entry(tmp_path: Path) -> None:
    (cache.cache_dir(tmp_path) / f"{'d' * 64}.m2v").mkdir(parents=True)

    assert cache.cache_bytes(tmp_path) == 0
    assert cache.evict(tmp_path, 0, keep=()) == 0


def test_a_blu_ray_key_follows_the_x264_command() -> None:
    dvd = key()
    blu_ray = key(profile="bd25")

    assert blu_ray != dvd
    assert key(profile="bd50") == blu_ray  # same encode on either disc size
    assert key(profile="bd25", video_kbps=20_000) != blu_ray


def test_h264_entries_are_kept_counted_and_evicted(tmp_path: Path) -> None:
    h264 = write_m2v(tmp_path / "job" / "video.h264", b"\x00\x00\x00\x01h264" * 10)
    m2v = write_m2v(tmp_path / "job" / "title1.m2v")
    cache.store(tmp_path, "b" * 64, h264, PASS2)
    cache.store(tmp_path, "c" * 64, m2v, PASS2)
    target = tmp_path / "job2" / "video.h264"

    assert cache.lookup(tmp_path, "b" * 64, target) is not None
    assert target.read_bytes() == h264.read_bytes()
    assert cache.cache_bytes(tmp_path) == h264.stat().st_size + m2v.stat().st_size
    assert cache.lookup(tmp_path, "c" * 64, tmp_path / "job2" / "video.h264") is None

    os.utime(cache.cache_dir(tmp_path) / f"{'b' * 64}.h264", (1, 1))
    cache.evict(tmp_path, m2v.stat().st_size, keep=())
    assert not (cache.cache_dir(tmp_path) / f"{'b' * 64}.h264").exists()
    cache.purge(tmp_path, ["c" * 64])
    assert list(cache.cache_dir(tmp_path).iterdir()) == []
