import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, select

from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.library.probe import NO_VIDEO, READ_ERROR, FfprobeMissingError, ProbeResult
from projeto_dvd.library.scan import (
    CHANGED_FILE,
    Status,
    folder_view,
    purge_missing_folders,
    scan_folder,
)
from tests.tree import make_file, snapshot

NOT_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")

VIDEO_JSON = json.dumps(
    {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"codec_type": "audio", "codec_name": "ac3", "channels": 6},
        ],
        "format": {"duration": "3600.0"},
    }
)
AUDIO_ONLY_JSON = json.dumps({"streams": [], "format": {"duration": "60.0"}})


class FakeProbe:
    """Records which files were probed; answers with a fixed result per file name."""

    def __init__(self, results: dict[str, ProbeResult] | None = None) -> None:
        self.results = results or {}
        self.calls: list[str] = []

    def __call__(self, path: Path) -> ProbeResult:
        self.calls.append(path.name)
        return self.results.get(path.name, ProbeResult(json=VIDEO_JSON, error=None))


@pytest.fixture
def media(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    make_file(root / "Disco" / "a.mkv", b"aaa")
    make_file(root / "Disco" / "b.mkv", b"bbb")
    return root


def scan(session: Session, media: Path, probe: FakeProbe, name: str = "Disco") -> int:
    return scan_folder(session, media, name, media / name, probe)


def rows(session: Session) -> dict[str, MediaFile]:
    return {row.path: row for row in session.exec(select(MediaFile)).all()}


# Incremental scan


def test_first_scan_probes_every_video(session: Session, media: Path) -> None:
    probe = FakeProbe()

    assert scan(session, media, probe) == 2
    assert sorted(probe.calls) == ["a.mkv", "b.mkv"]
    saved = rows(session)["Disco/a.mkv"]
    assert (saved.folder, saved.size, saved.probe_json, saved.error) == (
        "Disco",
        3,
        VIDEO_JSON,
        None,
    )
    assert saved.mtime_ns == (media / "Disco" / "a.mkv").stat().st_mtime_ns


def test_second_scan_without_changes_does_not_probe(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    probe = FakeProbe()

    assert scan(session, media, probe) == 0
    assert probe.calls == []


def test_new_and_changed_files_are_probed(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    make_file(media / "Disco" / "c.mkv")
    (media / "Disco" / "a.mkv").write_bytes(b"changed")
    probe = FakeProbe()

    scan(session, media, probe)

    assert sorted(probe.calls) == ["a.mkv", "c.mkv"]
    assert rows(session)["Disco/a.mkv"].size == 7


def test_older_mtime_counts_as_a_change(session: Session, media: Path) -> None:
    # Windows Explorer keeps the original mtime when copying a file over another one.
    scan(session, media, FakeProbe())
    os.utime(media / "Disco" / "a.mkv", ns=(1, 1))
    probe = FakeProbe()

    scan(session, media, probe)

    assert probe.calls == ["a.mkv"]


def test_removed_files_leave_the_database(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    (media / "Disco" / "b.mkv").unlink()

    scan(session, media, FakeProbe())

    assert list(rows(session)) == ["Disco/a.mkv"]


def test_files_with_a_previous_error_are_probed_again(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe({"a.mkv": ProbeResult(json=None, error="boom")}))
    assert rows(session)["Disco/a.mkv"].error == "boom"
    probe = FakeProbe()

    scan(session, media, probe)

    assert probe.calls == ["a.mkv"]
    assert rows(session)["Disco/a.mkv"].error is None


def test_a_bad_file_does_not_stop_the_scan(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe({"a.mkv": ProbeResult(json=None, error="Invalid data")}))

    saved = rows(session)
    assert (saved["Disco/a.mkv"].probe_json, saved["Disco/a.mkv"].error) == (None, "Invalid data")
    assert saved["Disco/b.mkv"].probe_json == VIDEO_JSON


def test_file_growing_during_scan_is_probed_again_next_time(session: Session, media: Path) -> None:
    # The stat stored is the one taken before ffprobe: a copy still in progress looks changed.
    def growing(path: Path) -> ProbeResult:
        with path.open("ab") as file:
            file.write(b"more")
        return ProbeResult(json=VIDEO_JSON, error=None)

    scan_folder(session, media, "Disco", media / "Disco", growing)
    probe = FakeProbe()

    scan(session, media, probe)

    assert sorted(probe.calls) == ["a.mkv", "b.mkv"]


def test_file_removed_before_probing_is_skipped(session: Session, media: Path) -> None:
    def vanish(path: Path) -> ProbeResult:
        path.unlink()
        return ProbeResult(json=None, error="No such file or directory")

    scan_folder(session, media, "Disco", media / "Disco", vanish)

    assert rows(session) == {}


def test_row_of_a_file_removed_while_probing_is_dropped(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    (media / "Disco" / "a.mkv").write_bytes(b"changed")

    def vanish(path: Path) -> ProbeResult:
        path.unlink()
        return ProbeResult(json=None, error="No such file or directory")

    scan_folder(session, media, "Disco", media / "Disco", vanish)

    assert list(rows(session)) == ["Disco/b.mkv"]


def test_missing_ffprobe_stops_the_scan_without_marking_files(
    session: Session, media: Path
) -> None:
    def missing(path: Path) -> ProbeResult:
        raise FfprobeMissingError

    with pytest.raises(FfprobeMissingError):
        scan_folder(session, media, "Disco", media / "Disco", missing)

    assert rows(session) == {}


def test_scan_only_touches_its_own_folder(session: Session, media: Path) -> None:
    make_file(media / "Outro" / "x.mkv")
    scan(session, media, FakeProbe(), name="Outro")

    scan(session, media, FakeProbe())

    assert sorted(rows(session)) == ["Disco/a.mkv", "Disco/b.mkv", "Outro/x.mkv"]


def test_rescan_updates_the_same_row(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    first_id = rows(session)["Disco/a.mkv"].id
    (media / "Disco" / "a.mkv").write_bytes(b"changed")

    scan(session, media, FakeProbe())

    assert rows(session)["Disco/a.mkv"].id == first_id
    assert len(rows(session)) == 2


def test_purge_removes_rows_of_folders_that_are_gone(session: Session, media: Path) -> None:
    make_file(media / "Outro" / "x.mkv")
    scan(session, media, FakeProbe())
    scan(session, media, FakeProbe(), name="Outro")

    purge_missing_folders(session, ["Disco"])

    assert sorted(rows(session)) == ["Disco/a.mkv", "Disco/b.mkv"]


# Read-only


def test_scan_never_writes_to_the_media_folder(session: Session, media: Path) -> None:
    make_file(media / "Disco" / "a.pt-BR.srt")
    before = snapshot(media)

    scan(session, media, FakeProbe())
    folder_view(session, media, "Disco", media / "Disco")

    assert snapshot(media) == before


@NOT_ROOT
def test_scan_works_on_a_read_only_folder(session: Session, media: Path) -> None:
    disc = media / "Disco"
    for file in disc.iterdir():
        file.chmod(0o444)
    disc.chmod(0o555)
    media.chmod(0o555)
    try:
        assert scan(session, media, FakeProbe()) == 2
    finally:
        media.chmod(0o755)
        disc.chmod(0o755)


# Status and view


def test_status_empty(session: Session, tmp_path: Path) -> None:
    make_file(tmp_path / "Vazia" / "Filme.srt")  # subtitles alone are not videos

    result = folder_view(session, tmp_path, "Vazia", tmp_path / "Vazia")

    assert result.status == Status.EMPTY
    assert result.files == ()


def test_status_not_scanned(session: Session, media: Path) -> None:
    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.NOT_SCANNED
    assert result.size == 6
    assert result.duration is None
    assert [f.summary for f in result.files] == [None, None]


def test_status_ok_with_total_duration(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())

    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.OK
    assert result.duration == 7200.0
    assert result.warning_count == 0


def test_status_with_warnings(session: Session, media: Path) -> None:
    scan(
        session,
        media,
        FakeProbe(
            {
                "a.mkv": ProbeResult(json=None, error="Invalid data"),
                "b.mkv": ProbeResult(json=AUDIO_ONLY_JSON, error=None),
            }
        ),
    )

    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.WARNINGS
    assert result.warning_count == 2
    assert [f.warnings for f in result.files] == [(READ_ERROR,), (NO_VIDEO,)]
    assert result.files[0].error == "Invalid data"


@pytest.mark.parametrize("change", ["added", "removed", "modified"])
def test_status_changed(session: Session, media: Path, change: str) -> None:
    scan(session, media, FakeProbe())
    if change == "added":
        make_file(media / "Disco" / "c.mkv")
    elif change == "removed":
        (media / "Disco" / "b.mkv").unlink()
    else:
        (media / "Disco" / "a.mkv").write_bytes(b"changed")

    result = folder_view(session, media, "Disco", media / "Disco")

    assert result.status == Status.CHANGED


def test_same_size_with_another_mtime_has_changed(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    os.utime(media / "Disco" / "a.mkv", ns=(1, 1))

    assert folder_view(session, media, "Disco", media / "Disco").status == Status.CHANGED


def test_changed_wins_over_warnings(session: Session, media: Path) -> None:
    # "mudou" asks for a new scan, so it is shown even when there are warnings.
    scan(session, media, FakeProbe({"a.mkv": ProbeResult(json=None, error="Invalid data")}))
    make_file(media / "Disco" / "c.mkv")

    assert folder_view(session, media, "Disco", media / "Disco").status == Status.CHANGED


def test_empty_folder_with_old_rows_has_changed(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    for file in (media / "Disco").iterdir():
        file.unlink()

    assert folder_view(session, media, "Disco", media / "Disco").status == Status.CHANGED


def test_duration_ignores_files_without_one(session: Session, media: Path) -> None:
    no_duration = json.dumps({"streams": [], "format": {}})
    scan(session, media, FakeProbe({"a.mkv": ProbeResult(json=no_duration, error=None)}))

    assert folder_view(session, media, "Disco", media / "Disco").duration == 3600.0


def test_rows_from_other_folders_do_not_leak(session: Session, media: Path) -> None:
    session.add(
        MediaFile(
            folder="Disco 2",
            path="Disco 2/a.mkv",
            size=1,
            mtime_ns=1,
            scanned_at=datetime.now(UTC),
        )
    )
    session.commit()

    assert folder_view(session, media, "Disco", media / "Disco").status == Status.NOT_SCANNED


def test_changed_file_unconfirms_title(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    row = rows(session)["Disco/a.mkv"]
    row.title = Title(status="confirmed", kind="movie", label="Anel (2001)", tmdb_id=101)
    session.commit()

    (media / "Disco" / "a.mkv").write_bytes(b"another disc")
    scan(session, media, FakeProbe())

    session.refresh(row)
    assert row.title is not None
    assert (row.title.status, row.title.message, row.title.tmdb_id) == (
        "suggested",
        CHANGED_FILE,
        101,
    )


def test_unchanged_file_keeps_its_confirmation(session: Session, media: Path) -> None:
    scan(session, media, FakeProbe())
    row = rows(session)["Disco/a.mkv"]
    row.title = Title(status="confirmed", kind="movie", label="Anel (2001)", tmdb_id=101)
    row.error = "old error"  # probed again, but the file is the same
    session.commit()

    scan(session, media, FakeProbe())

    session.refresh(row)
    assert row.title is not None and row.title.status == "confirmed"
