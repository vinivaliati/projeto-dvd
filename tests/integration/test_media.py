"""Real ffmpeg/ffprobe: run inside the Docker image (make test-slow)."""

import json
import subprocess
from pathlib import Path

import pytest
from sqlmodel import Session

from projeto_dvd.library.probe import READ_ERROR, run_ffprobe, summarize
from projeto_dvd.library.scan import Status, folder_view, scan_folder
from tests.tree import make_file

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).parent.parent / "fixtures"
GENERATED = ["movie", "cover", "cover_only", "hdr10", "hlg", "dvd"]


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("probe")
    subprocess.run(["sh", str(FIXTURES / "make_fixtures.sh"), str(out)], check=True)
    return out


@pytest.mark.parametrize("name", GENERATED)
def test_committed_fixtures_match_the_image_ffprobe(regenerated: Path, name: str) -> None:
    committed = json.loads((FIXTURES / "probe" / f"{name}.json").read_text())
    fresh = json.loads((regenerated / f"{name}.json").read_text())

    assert summarize(fresh) == summarize(committed)


def test_scan_end_to_end(session: Session, tmp_path: Path) -> None:
    media = tmp_path / "media"
    disc = media / "Disco Teste"
    disc.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=s=1280x720:r=25:d=2",
            "-f", "lavfi", "-i", "sine=d=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "ac3",
            str(disc / "Filme.mkv"),
        ],
        check=True,
    )  # fmt: skip
    make_file(disc / "quebrado.mkv", b"not a video")

    probed = scan_folder(session, media, "Disco Teste", disc, run_ffprobe)
    view = folder_view(session, media, "Disco Teste", disc)

    assert probed == 2
    assert view.status == Status.WARNINGS
    good, broken = view.files
    assert good.summary is not None and good.summary.video is not None
    assert good.summary.video.width == 1280
    assert good.summary.duration == pytest.approx(2, abs=0.1)
    assert broken.warnings == (READ_ERROR,)
    assert broken.error is not None and "Invalid data" in broken.error
