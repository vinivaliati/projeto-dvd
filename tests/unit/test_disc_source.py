import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image
from sqlmodel import Session

from projeto_dvd.db.models import MediaFile
from projeto_dvd.library.files import VideoFile
from projeto_dvd.library.probe import summarize
from projeto_dvd.library.scan import FileView, FolderView, Status
from projeto_dvd.menus.theme import PALETTE
from projeto_dvd.metadata.filename import guess
from projeto_dvd.planner import disc_source, source
from projeto_dvd.planner.disc import DiscTitle
from projeto_dvd.planner.disc_build import TitleSource
from projeto_dvd.planner.disc_plan import DiscPlan, Theme
from projeto_dvd.planner.disc_source import (
    disc_menu,
    folder_reasons,
    load_disc,
    prepare_title,
    suggested_disc_plan,
    suggestion,
    theme_image,
)
from projeto_dvd.planner.source import VideoMode
from tests.tree import make_file

VIDEO = VideoFile(path="F/f.mkv", absolute=Path("/media/F/f.mkv"), size=10, mtime_ns=20)
H264 = {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
        "r_frame_rate": "24000/1001", "avg_frame_rate": "24000/1001",
        "display_aspect_ratio": "16:9"}  # fmt: skip
MPEG2 = {**H264, "codec_name": "mpeg2video", "width": 720, "height": 480,
         "r_frame_rate": "30000/1001", "avg_frame_rate": "30000/1001"}  # fmt: skip
AUDIO = {"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 2,
         "sample_rate": "48000", "bit_rate": "192000", "tags": {"language": "por"}}  # fmt: skip


def summary(*streams: dict[str, Any]) -> Any:
    return summarize({"streams": list(streams), "format": {"duration": "600"}})


def view(status: Status, files: tuple[FileView, ...]) -> FolderView:
    return FolderView(name="F", status=status, files=files, size=10, duration=600.0)


def title(*streams: dict[str, Any]) -> DiscTitle:
    return DiscTitle(path=VIDEO.path, video=VIDEO, summary=summary(*streams), options=(),
                     info=None, guess=guess("f.mkv", "F", 2030))  # fmt: skip


def test_folder_reasons() -> None:
    good = FileView(video=VIDEO, summary=summary(H264, AUDIO), error=None)

    assert folder_reasons(view(Status.EMPTY, ())) == ()
    assert folder_reasons(view(Status.NOT_SCANNED, (good,))) == (disc_source.SCAN_FIRST,)
    assert folder_reasons(view(Status.CHANGED, (good,))) == (disc_source.CHANGED,)
    assert folder_reasons(view(Status.OK, (good, good))) == ()
    broken = FileView(video=VIDEO, summary=None, error="x")
    assert folder_reasons(view(Status.WARNINGS, (good, broken))) == (
        f"f.mkv: {disc_source.READ_ERROR}",
    )  # fmt: skip


def test_a_video_the_dvd_cannot_take_blocks_the_folder_with_its_name() -> None:
    silent = FileView(video=VIDEO, summary=summary(H264), error=None)
    assert folder_reasons(view(Status.OK, (silent,))) == (f"f.mkv: {source.NO_AUDIO}",)


def test_scanned_folder_without_summary_asks_for_a_scan() -> None:
    pending = FileView(video=VIDEO, summary=None, error=None)

    assert folder_reasons(view(Status.OK, (pending,))) == (disc_source.SCAN_FIRST,)


def test_prepare_h264_film_without_frame_scan() -> None:
    def capture(command: list[str]) -> str:
        raise AssertionError("no frame scan for H.264")

    result = prepare_title(title(H264, AUDIO), capture)

    assert isinstance(result, TitleSource) and result.mode == VideoMode.FILM


def test_prepare_mpeg2_uses_the_frames() -> None:
    frames = [{"repeat_pict": r, "interlaced_frame": 0, "top_field_first": t}
              for r, t in [(1, 1), (0, 0), (1, 0), (0, 1)] * 20]  # fmt: skip
    calls: list[list[str]] = []

    def capture(command: list[str]) -> str:
        calls.append(command)
        return json.dumps({"frames": frames})

    result = prepare_title(title(MPEG2, AUDIO), capture)

    assert isinstance(result, TitleSource) and result.mode == VideoMode.FILM
    assert calls[0][0] == "ffprobe"


def test_prepare_returns_refusals() -> None:
    assert prepare_title(title(AUDIO), lambda command: "") == (source.NO_VIDEO,)


def test_prepare_turns_a_failed_frame_scan_into_a_refusal() -> None:
    def capture(command: list[str]) -> str:
        raise OSError("boom")

    assert prepare_title(title(MPEG2, AUDIO), capture) == (source.FRAMES_UNREADABLE,)


def test_prepare_refuses_progressive_2997_mpeg2() -> None:
    frames = [{"repeat_pict": 0, "interlaced_frame": 0, "top_field_first": 1}] * 50

    result = prepare_title(title(MPEG2, AUDIO), lambda c: json.dumps({"frames": frames}))

    assert result == (source.PROGRESSIVE_2997,)


def test_run_capture_returns_stdout() -> None:
    assert disc_source.run_capture([sys.executable, "-c", "print('ok')"]).strip() == "ok"


def test_suggestion_picks_the_profile_with_the_calculator() -> None:
    choices = suggestion((title(H264, AUDIO),), "F")
    assert (choices.profile, choices.audio, choices.order) == ("dvd5", ("pt",), ("F/f.mkv",))


def backdrop(
    output: Path, name: str = "Up (2009)", color: tuple[int, int, int] = (30, 60, 200)
) -> None:
    path = output / "covers" / "F" / name / "backdrop.jpg"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 36), color).save(path)


def test_theme_image_reads_an_available_backdrop(tmp_path: Path) -> None:
    backdrop(tmp_path)
    choices = suggestion((title(H264, AUDIO),), "F")
    chosen = choices.model_copy(update={"theme": Theme(backdrop="Up (2009)")})

    path, image = theme_image(chosen, "F", tmp_path)

    assert path == tmp_path / "covers" / "F" / "Up (2009)" / "backdrop.jpg" and image is not None
    assert theme_image(choices, "F", tmp_path) == (None, None)
    gone = chosen.model_copy(update={"theme": Theme(backdrop="Outro (2001)")})
    assert theme_image(gone, "F", tmp_path) == (None, None)
    menu = disc_menu(chosen, (title(H264, AUDIO),), "F", tmp_path)
    assert (menu.backdrop, menu.accent) == (str(path), PALETTE["azul"][1])


def test_an_unreadable_backdrop_counts_as_none(tmp_path: Path) -> None:
    make_file(tmp_path / "covers" / "F" / "Up (2009)" / "backdrop.jpg", b"not a jpeg")
    choices = suggestion((title(H264, AUDIO),), "F")
    chosen = choices.model_copy(update={"theme": Theme(backdrop="Up (2009)")})

    assert theme_image(chosen, "F", tmp_path) == (None, None)


def scanned(
    session: Session, media: Path, *names: str, probe: dict[str, Any] | None = None
) -> None:
    data = json.dumps(probe or {"streams": [H264, AUDIO], "format": {"duration": "600"}})
    for name in names:
        file = make_file(media / "F" / name)
        stat = file.stat()
        session.add(MediaFile(folder="F", path=f"F/{name}", size=stat.st_size,
                              mtime_ns=stat.st_mtime_ns, probe_json=data,
                              scanned_at=datetime.now(UTC)))  # fmt: skip
    session.commit()


def test_load_disc(session: Session, tmp_path: Path) -> None:
    scanned(session, tmp_path, "b.mkv", "a.mkv")

    folder_view, titles = load_disc(session, tmp_path, "F", tmp_path / "F")

    assert folder_view.status == Status.OK
    assert [t.path for t in titles] == ["F/a.mkv", "F/b.mkv"]


def test_suggested_disc_plan(session: Session, tmp_path: Path) -> None:
    media, output = tmp_path / "media", tmp_path / "out"
    scanned(session, media, "Ep.S01E02.mkv", "Ep.S01E01.mkv")
    backdrop(output)

    plan = suggested_disc_plan(session, media, output, "F", media / "F", lambda c: "")

    assert isinstance(plan, DiscPlan)
    assert [t.path for t in plan.titles] == ["F/Ep.S01E01.mkv", "F/Ep.S01E02.mkv"]
    assert plan.menu is not None and plan.menu.backdrop is not None
    assert plan.menu.pages[0].items[0].action == "play_all"
    assert plan.confirmed_low and plan.replace_existing


def test_suggested_disc_plan_refusals(session: Session, tmp_path: Path) -> None:
    assert suggested_disc_plan(session, tmp_path, tmp_path, "F", tmp_path / "F",
                               lambda c: "") == ("Nada para gerar.",)  # fmt: skip
    scanned(session, tmp_path, "a.mkv", probe={"streams": [MPEG2, AUDIO],
                                               "format": {"duration": "600"}})  # fmt: skip

    def broken(command: list[str]) -> str:
        raise OSError("boom")

    result = suggested_disc_plan(session, tmp_path, tmp_path, "F", tmp_path / "F", broken)

    assert result == (source.FRAMES_UNREADABLE,)


def test_suggested_disc_plan_that_does_not_fit(session: Session, tmp_path: Path) -> None:
    long = {"streams": [H264, AUDIO], "format": {"duration": str(60 * 60 * 40)}}
    scanned(session, tmp_path, "a.mkv", probe=long)

    result = suggested_disc_plan(session, tmp_path, tmp_path, "F", tmp_path / "F", lambda c: "")

    assert result == ("O disco não cabe no DVD-9.",)
