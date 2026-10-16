import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from sqlmodel import Session, select

from projeto_dvd.db.models import MediaFile, Title
from projeto_dvd.metadata.art import LOW_RES
from projeto_dvd.metadata.curation import (
    ART_FAILED,
    MOVIE_DURATION,
    Choice,
    confirm,
    confirm_all,
    confirmed_counts,
    download_again,
    original_language,
    run_suggestions,
)
from projeto_dvd.metadata.details import title_info
from projeto_dvd.metadata.tmdb import TOKEN_REFUSED, TmdbClient, TmdbError
from projeto_dvd.metadata.tmdb_models import DETAILS
from tests.tmdb_fakes import MOVIE, SHOW, router, search_page, season

RING = {"id": 101, "title": "Anel Mágico", "original_title": "The Magic Ring",
        "release_date": "2001-12-19", "poster_path": "/posterpt.jpg"}  # fmt: skip
IMAGES = {f"/t/p/original{p}": b"img" for p in
          ("/posterpt.jpg", "/backnull2.jpg", "/logoen.png", "/showposter.jpg", "/still3.jpg",
           "/still1.jpg")}  # fmt: skip


def tmdb(routes: Mapping[str, object], requests: list[httpx2.Request] | None = None) -> TmdbClient:
    return TmdbClient("t", "pt-BR", transport=httpx2.MockTransport(router(routes, requests)))


def add_file(session: Session, path: str, seconds: float = 10680.0) -> MediaFile:
    probe = {"streams": [], "format": {"duration": str(seconds)}}
    row = MediaFile(folder=path.split("/")[0], path=path, size=1, mtime_ns=1,
                    probe_json=json.dumps(probe), scanned_at=datetime.now(UTC))  # fmt: skip
    session.add(row)
    session.commit()
    return row


def test_run_suggestions_skips_confirmed(session: Session) -> None:
    first = add_file(session, "Anel/Anel Mágico (2001).mkv")
    done = add_file(session, "Anel/Outro.mkv")
    done.title = Title(status="confirmed", kind="movie", label="Outro", tmdb_id=5)
    session.commit()

    count = run_suggestions(session, "Anel", tmdb({"/3/search/movie": search_page(RING)}), 2026)

    assert count == 1
    assert first.title is not None
    assert (first.title.status, first.title.tmdb_id, first.title.label) == (
        "suggested", 101, "Anel Mágico (2001)",
    )  # fmt: skip
    assert done.title is not None and done.title.label == "Outro"


def test_run_suggestions_writes_nothing_when_tmdb_fails(session: Session) -> None:
    add_file(session, "Anel/Anel Mágico (2001).mkv")

    with pytest.raises(TmdbError):
        run_suggestions(session, "Anel", tmdb({"/3/search/movie": 401}), 2026)

    assert session.exec(select(Title)).all() == []


def test_confirm_movie_downloads_art_and_metadata(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)  # fmt: skip

    folder = tmp_path / "covers" / "Anel" / "Anel Mágico (2001)"
    assert sorted(p.name for p in folder.iterdir()) == [
        "backdrop.jpg", "logo.png", "metadata.json", "poster.jpg",
    ]  # fmt: skip
    assert json.loads((folder / "metadata.json").read_text())["title"] == "Anel Mágico"
    assert (title.status, title.label, title.message) == ("confirmed", "Anel Mágico (2001)", None)
    assert title.tmdb_json is not None
    assert title_info(DETAILS.validate_json(title.tmdb_json)).collection_id == 900


def test_confirm_movie_with_colon_in_title(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Disco: 1/a.mkv")
    assert row.id is not None
    routes: dict[str, object] = {"/3/movie/101": {**MOVIE, "title": "Anel: Parte 1"}, **IMAGES}

    confirm(session, row.id, Choice("movie", 101), tmdb(routes), tmp_path)

    folder = tmp_path / "covers" / "Disco - 1" / "Anel - Parte 1 (2001)"
    assert (folder / "poster.jpg").exists()


def test_confirm_warns_about_the_movie_duration(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv", seconds=228 * 60)
    assert row.id is not None

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)  # fmt: skip

    assert title.message == MOVIE_DURATION


def test_confirm_episode_fills_english_and_saves_the_still(
    session: Session, tmp_path: Path
) -> None:
    row = add_file(session, "Amigos/S01E02.mkv", seconds=22 * 60)
    assert row.id is not None
    routes: dict[str, object] = {"/3/tv/202": SHOW, "/3/tv/202/season/1": season(),
              "/3/tv/202/season/1?language=en-US": season("en"), **IMAGES,
              "/t/p/original/still2.jpg": b"img"}  # fmt: skip

    title = confirm(session, row.id, Choice("episode", 202, 1, 2), tmdb(routes), tmp_path)

    info = title_info(DETAILS.validate_json(title.tmdb_json or ""))
    assert (info.title, info.overview) == ("The Middle", "Resumo 2")
    assert title.label == "Amigos de Sempre · S01E02 · The Middle"
    folder = tmp_path / "covers" / "Amigos" / "Amigos de Sempre"
    assert (folder / "S01E02.jpg").exists()
    assert json.loads((folder / "S01E02.json").read_text())["episode"] == 2


def test_confirm_missing_episode_changes_nothing(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Amigos/S01E09.mkv")
    assert row.id is not None
    routes: dict[str, object] = {"/3/tv/202": SHOW, "/3/tv/202/season/1": season()}

    with pytest.raises(TmdbError):
        confirm(session, row.id, Choice("episode", 202, 1, 9), tmdb(routes), tmp_path)

    assert session.exec(select(Title)).all() == []


def test_art_failure_keeps_the_confirmation(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    routes: dict[str, object] = {"/3/movie/101": MOVIE, "/t/p/original/posterpt.jpg": b"img"}

    title = confirm(session, row.id, Choice("movie", 101), tmdb(routes), tmp_path)

    assert title.status == "confirmed"
    assert title.message is not None and title.message.startswith(ART_FAILED)


def test_unwritable_output_keeps_the_confirmation(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    blocked = tmp_path / "out"
    blocked.write_text("a file, not a folder")

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), blocked)  # fmt: skip

    assert title.status == "confirmed"
    assert title.message is not None and "chown" in title.message


def test_download_again_overwrites(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    client = tmdb({"/3/movie/101": MOVIE, **IMAGES})
    confirm(session, row.id, Choice("movie", 101), client, tmp_path)
    poster = tmp_path / "covers" / "Anel" / "Anel Mágico (2001)" / "poster.jpg"
    poster.write_bytes(b"old")

    download_again(session, row.id, client, tmp_path)

    assert poster.read_bytes() == b"img"


def test_confirm_all_skips_doubtful(session: Session, tmp_path: Path) -> None:
    sure = add_file(session, "Anel/a.mkv")
    doubtful = add_file(session, "Anel/b.mkv")
    sure.title = Title(status="suggested", kind="movie", label="Anel", tmdb_id=101)
    doubtful.title = Title(status="doubtful", kind="movie", label="Anel", tmdb_id=101)
    session.commit()

    count = confirm_all(session, "Anel", tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)

    assert count == 1
    assert (sure.title.status, doubtful.title.status) == ("confirmed", "doubtful")


def test_counts_and_original_language(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    add_file(session, "Anel/b.mkv")
    assert row.id is not None
    confirm(session, row.id, Choice("movie", 101), tmdb({"/3/movie/101": MOVIE, **IMAGES}),
            tmp_path)  # fmt: skip

    assert confirmed_counts(session) == {"Anel": 1}
    assert original_language(session, "Anel/a.mkv") == "en"
    assert original_language(session, "Anel/b.mkv") is None


def test_episode_choice_needs_season_and_episode(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Amigos/a.mkv")
    assert row.id is not None

    with pytest.raises(TmdbError):
        confirm(session, row.id, Choice("episode", 202), tmdb({}), tmp_path)


def test_two_episodes_in_one_file(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Amigos/S01E01E02.mkv", seconds=44 * 60)
    assert row.id is not None
    routes: dict[str, object] = {"/3/tv/202": SHOW, "/3/tv/202/season/1": season(),
              "/3/tv/202/season/1?language=en-US": season("en"), **IMAGES}  # fmt: skip

    title = confirm(session, row.id, Choice("episode", 202, 1, 1, 2), tmdb(routes), tmp_path)

    assert (title.episode, title.episode_end) == (1, 2)
    assert title_info(DETAILS.validate_json(title.tmdb_json or "")).episode_end == 2


def test_missing_season_and_other_errors(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Amigos/a.mkv")
    assert row.id is not None

    with pytest.raises(TmdbError) as missing:
        confirm(session, row.id, Choice("episode", 202, 7, 1), tmdb({"/3/tv/202": SHOW}), tmp_path)
    with pytest.raises(TmdbError) as refused:
        confirm(session, row.id, Choice("episode", 202, 1, 1),
                tmdb({"/3/tv/202": SHOW, "/3/tv/202/season/1": 401}), tmp_path)  # fmt: skip

    assert missing.value.message == "O episódio S07E01 não existe no TMDB. Use Corrigir."
    assert refused.value.message == TOKEN_REFUSED


def test_episode_with_portuguese_text_needs_no_english(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Amigos/a.mkv")
    assert row.id is not None
    requests: list[httpx2.Request] = []
    routes: dict[str, object] = {"/3/tv/202": SHOW, "/3/tv/202/season/1": season(), **IMAGES}

    title = confirm(session, row.id, Choice("episode", 202, 1, 3), tmdb(routes, requests), tmp_path)

    assert title.label == "Amigos de Sempre · S01E03 · O Polegar"
    assert not any(r.url.params.get("language") == "en-US" for r in requests)


def test_english_season_without_the_episode_keeps_portuguese(
    session: Session, tmp_path: Path
) -> None:
    row = add_file(session, "Amigos/a.mkv")
    assert row.id is not None
    routes: dict[str, object] = {"/3/tv/202": SHOW, "/3/tv/202/season/1": season(),
              "/3/tv/202/season/1?language=en-US": {"season_number": 1, "episodes": []},
              **IMAGES}  # fmt: skip

    title = confirm(session, row.id, Choice("episode", 202, 1, 2), tmdb(routes), tmp_path)

    assert title.label == "Amigos de Sempre · S01E02 · Episódio 2"


def test_pick_warning_and_existing_files(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    low = {**MOVIE, "images": {**MOVIE["images"], "posters": [
        {"file_path": "/posterpt.jpg", "iso_639_1": "pt", "width": 600}]}}  # fmt: skip
    folder = tmp_path / "covers" / "Anel" / "Anel Mágico (2001)"
    folder.mkdir(parents=True)
    (folder / "poster.jpg").write_bytes(b"kept")

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": low, **IMAGES}), tmp_path)  # fmt: skip

    assert title.message == LOW_RES
    assert (folder / "poster.jpg").read_bytes() == b"kept"


def test_disk_error_while_saving_art(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    folder = tmp_path / "covers" / "Anel" / "Anel Mágico (2001)"
    (folder / "poster.jpg.part").mkdir(parents=True)  # writing the poster fails

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)  # fmt: skip

    assert title.status == "confirmed"
    assert title.message is not None and "chown" in title.message
    assert not (folder / "backdrop.jpg").exists()  # stops at the first disk error


def test_download_again_needs_a_confirmed_title(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None

    with pytest.raises(TmdbError):
        download_again(session, row.id, tmdb({}), tmp_path)


def test_unknown_file(session: Session, tmp_path: Path) -> None:
    with pytest.raises(LookupError):
        confirm(session, 999, Choice("movie", 101), tmdb({}), tmp_path)


def test_original_language_only_when_confirmed(session: Session, tmp_path: Path) -> None:
    row = add_file(session, "Anel/a.mkv")
    assert row.id is not None
    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)  # fmt: skip
    title.status = "suggested"  # the file changed after the confirmation
    session.commit()

    assert original_language(session, "Anel/a.mkv") is None


def test_file_without_probe_has_no_duration_checks(session: Session, tmp_path: Path) -> None:
    row = MediaFile(folder="Anel", path="Anel/a.mkv", size=1, mtime_ns=1, error="ruim",
                    scanned_at=datetime.now(UTC))  # fmt: skip
    session.add(row)
    session.commit()
    assert row.id is not None

    title = confirm(session, row.id, Choice("movie", 101),
                    tmdb({"/3/movie/101": MOVIE, **IMAGES}), tmp_path)  # fmt: skip

    assert title.message is None


def test_episode_label_and_folder_use_the_english_show_name(
    session: Session, tmp_path: Path
) -> None:
    row = add_file(session, "Amigos/S01E03.mkv", seconds=22 * 60)
    assert row.id is not None
    translations = {"translations": [
        {"iso_639_1": "en", "iso_3166_1": "US", "data": {"name": "Forever Friends"}}]}  # fmt: skip
    show = {**SHOW, "name": "영원한 친구", "original_language": "ko", "translations": translations}
    routes: dict[str, object] = {"/3/tv/202": show, "/3/tv/202/season/1": season(), **IMAGES}

    title = confirm(session, row.id, Choice("episode", 202, 1, 3), tmdb(routes), tmp_path)

    assert title.label == "Forever Friends · S01E03 · O Polegar"
    assert (tmp_path / "covers" / "Amigos" / "Forever Friends" / "S01E03.jpg").exists()
