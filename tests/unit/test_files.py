import os
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library.files import (
    ExternalSubtitle,
    find_videos,
    list_disc_folders,
    match_subtitles,
    natural_key,
)
from tests.tree import make_file

NOT_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")


def test_natural_order() -> None:
    names = ["S01E10.mkv", "S01E02.mkv", "s01e01.mkv", "Extra.mkv"]

    assert sorted(names, key=natural_key) == ["Extra.mkv", "s01e01.mkv", "S01E02.mkv", "S01E10.mkv"]


def test_natural_order_with_superscript_digits() -> None:
    # "²" is a digit for str.isdigit() but not a decimal: int("²") would raise.
    assert sorted(["Rocky 2²", "Rocky 10", "Rocky 2"], key=natural_key) == [
        "Rocky 2",
        "Rocky 2²",
        "Rocky 10",
    ]


# Disc folders


def test_lists_immediate_subfolders_in_natural_order(tmp_path: Path) -> None:
    for name in ["Disco 10", "Disco 2", "Senhor dos Aneis"]:
        (tmp_path / name).mkdir()
    make_file(tmp_path / "solto.mkv")  # files at the root are ignored

    folders = list_disc_folders(tmp_path)

    assert list(folders) == ["Disco 2", "Disco 10", "Senhor dos Aneis"]
    assert folders["Disco 2"] == tmp_path / "Disco 2"


def test_missing_media_dir_has_no_folders(tmp_path: Path) -> None:
    assert list_disc_folders(tmp_path / "nao-montado") == {}


def test_symlinked_folder_is_ignored(tmp_path: Path) -> None:
    outside = tmp_path / "fora"
    outside.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    (media / "link").symlink_to(outside, target_is_directory=True)

    assert list_disc_folders(media) == {}


@NOT_ROOT
def test_unreadable_folder_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "ok").mkdir()
    locked = tmp_path / "System Volume Information"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        assert list(list_disc_folders(tmp_path)) == ["ok"]
    finally:
        locked.chmod(0o755)


def test_folder_names_are_nfc(tmp_path: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "Ação")
    (tmp_path / decomposed).mkdir()

    folders = list_disc_folders(tmp_path)

    assert list(folders) == ["Ação"]
    assert folders["Ação"] == tmp_path / decomposed  # the real path is kept for reading


# Videos


def test_finds_videos_recursively_with_stat(tmp_path: Path) -> None:
    disc = tmp_path / "Friends T1"
    make_file(disc / "Temporada 1" / "S01E10.mkv", b"12345")
    make_file(disc / "Temporada 1" / "S01E02.MP4")
    make_file(disc / "capa.jpg")
    make_file(disc / "Thumbs.db")
    make_file(disc / "info.nfo")

    videos = find_videos(tmp_path, disc)

    assert [v.path for v in videos] == [
        "Friends T1/Temporada 1/S01E02.MP4",
        "Friends T1/Temporada 1/S01E10.mkv",
    ]
    stat = (disc / "Temporada 1" / "S01E10.mkv").stat()
    assert (videos[1].size, videos[1].mtime_ns) == (5, stat.st_mtime_ns)
    assert videos[1].absolute == disc / "Temporada 1" / "S01E10.mkv"


@pytest.mark.parametrize("extension", [".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts"])
def test_video_extensions(tmp_path: Path, extension: str) -> None:
    make_file(tmp_path / "d" / f"a{extension.upper()}")

    assert len(find_videos(tmp_path, tmp_path / "d")) == 1


def test_symlinks_inside_a_disc_folder_are_ignored(tmp_path: Path) -> None:
    outside = make_file(tmp_path / "fora" / "segredo.mkv").parent
    disc = tmp_path / "media" / "d"
    make_file(disc / "real.mkv")
    (disc / "arquivo.mkv").symlink_to(outside / "segredo.mkv")
    (disc / "pasta").symlink_to(outside, target_is_directory=True)
    (disc / "laco").symlink_to(disc, target_is_directory=True)

    videos = find_videos(tmp_path / "media", disc)

    assert [v.path for v in videos] == ["d/real.mkv"]


def test_file_removed_before_stat_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_file(tmp_path / "d" / "a.mkv")
    make_file(tmp_path / "d" / "b.mkv")
    real_stat = Path.stat

    def stat(self: Path, **kwargs: Any) -> os.stat_result:
        if self.name == "a.mkv":
            raise FileNotFoundError(self)
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)

    assert [v.path for v in find_videos(tmp_path, tmp_path / "d")] == ["d/b.mkv"]


def test_video_paths_are_nfc(tmp_path: Path) -> None:
    make_file(tmp_path / "d" / unicodedata.normalize("NFD", "Coração.mkv"))

    assert find_videos(tmp_path, tmp_path / "d")[0].path == "d/Coração.mkv"


def test_external_subtitles_are_attached(tmp_path: Path) -> None:
    make_file(tmp_path / "d" / "Filme.mkv")
    make_file(tmp_path / "d" / "Filme.pt-BR.srt")

    video = find_videos(tmp_path, tmp_path / "d")[0]

    assert video.subtitles == (
        ExternalSubtitle(name="Filme.pt-BR.srt", language="pt-BR", image=False),
    )


# External subtitles (pure)


def test_subtitle_without_language() -> None:
    assert match_subtitles(["Filme.mkv", "Filme.srt"]) == {
        "Filme.mkv": (ExternalSubtitle(name="Filme.srt", language=None, image=False),)
    }


def test_subtitle_languages_and_kinds() -> None:
    result = match_subtitles(
        ["Filme.mkv", "Filme.en.forced.ass", "Filme.pt.sup", "Filme.pt-BR.ssa"]
    )

    assert result["Filme.mkv"] == (
        ExternalSubtitle(name="Filme.en.forced.ass", language="en.forced", image=False),
        ExternalSubtitle(name="Filme.pt-BR.ssa", language="pt-BR", image=False),
        ExternalSubtitle(name="Filme.pt.sup", language="pt", image=True),
    )


def test_subtitle_matching_normalizes_accents() -> None:
    video = unicodedata.normalize("NFD", "Coração.mkv")  # keys keep the real name, for reading

    result = match_subtitles([video, "Coração.pt.srt"])

    assert result == {video: (ExternalSubtitle(name="Coração.pt.srt", language="pt", image=False),)}


def test_idx_needs_its_sub() -> None:
    assert match_subtitles(["Filme.mkv", "Filme.idx"]) == {"Filme.mkv": ()}
    assert match_subtitles(["Filme.mkv", "Filme.IDX", "Filme.sub"]) == {
        "Filme.mkv": (ExternalSubtitle(name="Filme.IDX", language=None, image=True),)
    }


def test_longest_video_name_wins() -> None:
    result = match_subtitles(["Filme.mkv", "Filme.2.mkv", "Filme.2.pt-BR.srt", "Filme.pt.srt"])

    assert result == {
        "Filme.mkv": (ExternalSubtitle(name="Filme.pt.srt", language="pt", image=False),),
        "Filme.2.mkv": (ExternalSubtitle(name="Filme.2.pt-BR.srt", language="pt-BR", image=False),),
    }


def test_matching_ignores_case() -> None:
    result = match_subtitles(["Filme.mkv", "FILME.PT-BR.SRT"])

    assert result["Filme.mkv"] == (
        ExternalSubtitle(name="FILME.PT-BR.SRT", language="PT-BR", image=False),
    )


def test_same_name_videos_share_the_subtitle() -> None:
    result = match_subtitles(["Filme.mkv", "Filme.mp4", "Filme.srt"])

    assert result["Filme.mkv"] == result["Filme.mp4"] != ()


def test_unrelated_files_are_not_subtitles() -> None:
    assert match_subtitles(["Filme.mkv", "Outro.srt", "Filmes.srt", "Filme.nfo", "Filme.sub"]) == {
        "Filme.mkv": ()
    }


def test_subtitles_only_match_videos_in_the_same_folder(tmp_path: Path) -> None:
    make_file(tmp_path / "d" / "Filme.mkv")
    make_file(tmp_path / "d" / "legendas" / "Filme.srt")

    assert find_videos(tmp_path, tmp_path / "d")[0].subtitles == ()
