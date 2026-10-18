"""libbluray and libudfread through ctypes, on an ISO tsMuxeR makes here (make test-slow)."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from projeto_dvd.authoring.bluray.libs import bd_info, es_sha256, udf_copy, udf_tree
from projeto_dvd.authoring.bluray.meta import BdInputs, bd_meta, tsmuxer_command, tsmuxer_problem
from projeto_dvd.authoring.bluray.qa import REQUIRED, es_command, info_checks, tree_checks
from projeto_dvd.encode.x264 import X264_PARAMS
from projeto_dvd.planner.dvd_plan import AudioChoice
from tests.plans import make_disc_plan, make_title_plan

pytestmark = pytest.mark.slow
SECONDS = 12


def run(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


@pytest.fixture(scope="module")
def disc(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, object]:
    folder = tmp_path_factory.mktemp("bd")
    video, audio = folder / "video.h264", folder / "a1.ac3"
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
         f"testsrc2=s=1920x1080:r=24000/1001:d={SECONDS}", "-c:v", "libx264", "-preset",
         "ultrafast", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
         "-b:v", "8000k", "-maxrate", "35000k", "-bufsize", "30000k", "-x264-params",
         X264_PARAMS, "-f", "h264", str(video)])  # fmt: skip
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={SECONDS}",
         "-ac", "2", "-c:a", "ac3", "-b:a", "256k", "-f", "ac3", str(audio)])  # fmt: skip
    title = make_title_plan(duration=SECONDS * 1.0, chapters=(0.0, 6.0), width=1920, height=1080,
                            subtitles=(), audio=(AudioChoice(index=1, language="pt",
                            action="copy", channels=2, kbps=256, downmix=None, offset=0.0,
                            codec="ac3"),))  # fmt: skip
    plan = make_disc_plan(profile="bd25", volume="Teste", titles=(title,), menu=None,
                          subtitle_on=0)  # fmt: skip
    meta = folder / "disc.meta"
    meta.write_text(bd_meta(plan, BdInputs(video, (audio,), ())))
    iso = folder / "disc.iso"
    output = subprocess.run(tsmuxer_command(meta, iso), capture_output=True, text=True)
    assert output.returncode == 0 and tsmuxer_problem(output.stdout + output.stderr) is None
    return iso, video, plan


def test_the_tree_of_the_iso(disc: tuple[Path, Path, object]) -> None:
    iso, _, _ = disc
    paths = udf_tree(iso)

    assert set(REQUIRED) <= set(paths)
    assert all(check.ok for check in tree_checks(paths))


def test_the_playlist_through_libbluray(disc: tuple[Path, Path, object]) -> None:
    iso, _, plan = disc
    info = bd_info(iso)

    assert info.detected and info.first_play
    assert [round(c, 1) for c in info.chapters] == [0.0, 6.0]
    assert [(s.coding_type, s.language) for s in info.audio] == [(0x81, "por")]
    checks = info_checks(info, plan)  # type: ignore[arg-type]
    assert [c.name for c in checks if not c.ok] in ([], ["duration"])  # lavfi rounding


def test_the_video_comes_out_as_delivered(disc: tuple[Path, Path, object], tmp_path: Path) -> None:
    iso, video, _ = disc
    m2ts = tmp_path / "00000.m2ts"
    udf_copy(iso, "/BDMV/STREAM/00000.m2ts", m2ts)

    assert m2ts.stat().st_size > video.stat().st_size
    assert es_sha256(es_command(m2ts)) == hashlib.sha256(video.read_bytes()).hexdigest()


def test_opening_something_else_fails(tmp_path: Path) -> None:
    junk = tmp_path / "junk.iso"
    junk.write_bytes(b"\0" * 4096)

    with pytest.raises(OSError):
        udf_tree(junk)
