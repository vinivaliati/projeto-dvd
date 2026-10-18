from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.library.files import ExternalSubtitle, VideoFile
from projeto_dvd.library.probe import summarize
from projeto_dvd.library.scan import FileView, FolderView, Status
from projeto_dvd.metadata.details import TitleInfo
from projeto_dvd.metadata.filename import guess
from projeto_dvd.planner.disc import (
    DiscTitle,
    audio_languages,
    best_audio,
    best_subtitle,
    choice_errors,
    copy_reason,
    disc_name,
    disc_titles,
    is_rip,
    menu_name,
    reconcile,
    strip_prefix,
    subtitle_languages,
    suggest_choices,
    suggest_kind,
    suggest_order,
    track_warnings,
    video_size,
)
from projeto_dvd.planner.disc_plan import DiscChoices, Theme
from projeto_dvd.planner.dvd_plan import subtitle_options
from projeto_dvd.planner.languages import language_name

VIDEO = {
    "index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
    "r_frame_rate": "24000/1001", "avg_frame_rate": "24000/1001",
    "display_aspect_ratio": "16:9", "start_time": "0.000",
}  # fmt: skip


def audio(index: int, lang: str | None, channels: int = 6, **extra: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {"index": index, "codec_type": "audio", "codec_name": "ac3",
                              "channels": channels, "sample_rate": "48000"}  # fmt: skip
    if lang:
        stream["tags"] = {"language": lang}
    stream.update(extra)
    return stream


def sub(index: int, lang: str, forced: bool = False, codec: str = "subrip") -> dict[str, Any]:
    return {"index": index, "codec_type": "subtitle", "codec_name": codec,
            "tags": {"language": lang}, "disposition": {"forced": int(forced)}}  # fmt: skip


def title(
    path: str,
    audio_tracks: list[dict[str, Any]] | None = None,
    subtitles: list[dict[str, Any]] | None = None,
    chapters: int = 0,
    info: TitleInfo | None = None,
    external: tuple[ExternalSubtitle, ...] = (),
    duration: float = 2700.0,
    video_stream: dict[str, Any] = VIDEO,
) -> DiscTitle:
    streams = [video_stream, *(audio_tracks if audio_tracks is not None else [audio(1, "por")]),
               *(subtitles or [])]  # fmt: skip
    data = {
        "streams": streams,
        "format": {"duration": str(duration)},
        "chapters": [{"start_time": str(i * 60.0)} for i in range(chapters)],
    }
    summary = summarize(data)
    folder, relative = path.split("/", 1)
    video = VideoFile(path=path, absolute=Path("/media") / path, size=1, mtime_ns=1,
                      subtitles=external)  # fmt: skip
    return DiscTitle(
        path=path, video=video, summary=summary,
        options=tuple(subtitle_options(summary, external)), info=info,
        guess=guess(relative, folder, 2030),
    )  # fmt: skip


def movie(name: str, year: int | None = None, collection: str | None = None,
          language: str = "en") -> TitleInfo:  # fmt: skip
    return TitleInfo(kind="movie", tmdb_id=1, title=name, year=year, collection=collection,
                     original_language=language)  # fmt: skip


def episode(show: str, season: int, number: int, name: str) -> TitleInfo:
    return TitleInfo(kind="episode", tmdb_id=2, title=name, show=show, season=season,
                     episode=number, original_language="en")  # fmt: skip


def choices(**overrides: Any) -> DiscChoices:
    fields: dict[str, Any] = {
        "kind": "movies",
        "order": ("P/a.mkv",),
        "profile": "dvd9",
        "audio": ("pt",),
        "subtitles": (),
        "subtitle_on": None,
        "chapters": "every",
        "minutes": 5,
    }
    fields.update(overrides)
    return DiscChoices(**fields)


def dvd9(_: DiscChoices) -> str:
    return "dvd9"


# Names


def test_a_confirmed_movie_uses_the_tmdb_title() -> None:
    assert menu_name(title("P/x.mkv", info=movie("A Sociedade do Anel"))) == ("A Sociedade do Anel")


def test_a_confirmed_episode_is_numbered() -> None:
    t = title("P/x.mkv", info=episode("Friends", 1, 3, "O do Polegar"))
    assert menu_name(t) == "3. O do Polegar"


def test_a_generic_episode_name_is_not_numbered_twice() -> None:
    t = title("P/x.mkv", info=episode("Friends", 1, 3, "Episódio 3"))
    assert menu_name(t) == "Episódio 3"


def test_an_unconfirmed_episode_uses_its_number() -> None:
    assert menu_name(title("Friends/Friends.S01E03.mkv")) == "Episódio 3"


def test_an_unconfirmed_movie_uses_the_parsed_title() -> None:
    assert menu_name(title("P/O.Hobbit.2012.1080p.mkv")) == "O Hobbit"


def test_a_name_that_says_nothing_uses_the_file_stem() -> None:
    t = title("P/title_t00.mkv")
    assert menu_name(t) == "P"  # the parser falls back to the folder title


def test_disc_name_of_a_season() -> None:
    titles = [title("F/a.mkv", info=episode("Friends", 1, n, f"E{n}")) for n in (1, 2)]
    assert disc_name(titles, "F") == ("Friends", "Temporada 1")


def test_disc_name_of_two_seasons_has_no_secondary_line() -> None:
    titles = [title("F/a.mkv", info=episode("Friends", s, 1, "x")) for s in (1, 2)]
    assert disc_name(titles, "F") == ("Friends", None)


def test_disc_name_of_one_movie() -> None:
    assert disc_name([title("P/a.mkv", info=movie("Up"))], "P") == ("Up", None)


def test_disc_name_of_a_collection() -> None:
    titles = [title("P/a.mkv", info=movie(n, collection="O Senhor dos Anéis")) for n in "ab"]
    assert disc_name(titles, "P") == ("O Senhor dos Anéis", None)


def test_disc_name_falls_back_to_the_folder() -> None:
    titles = [title("P/a.mkv", info=movie("a")), title("P/b.mkv")]
    assert disc_name(titles, "Pasta") == ("Pasta", None)


def test_strip_prefix() -> None:
    disc = "O Senhor dos Anéis"
    assert strip_prefix("O Senhor dos Anéis: A Sociedade do Anel", disc) == "A Sociedade do Anel"
    assert strip_prefix("O Senhor dos Anéis - As Duas Torres", disc) == "As Duas Torres"
    assert strip_prefix("O Senhor dos Anéis", disc) == "O Senhor dos Anéis"
    assert strip_prefix("O Senhor dos Anéisx", disc) == "O Senhor dos Anéisx"


# Order and kind


def test_series_order_by_season_and_episode() -> None:
    titles = [title("F/F.S02E01.mkv"), title("F/F.S01E10.mkv"), title("F/F.S01E02.mkv")]
    assert suggest_kind(titles) == "series"
    assert suggest_order(titles) == ("F/F.S01E02.mkv", "F/F.S01E10.mkv", "F/F.S02E01.mkv")


def test_movies_order_by_year_then_natural_name() -> None:
    titles = [title("P/b10.mkv"), title("P/b2.mkv"), title("P/z.mkv", info=movie("z", 1990))]
    assert suggest_kind(titles) == "movies"
    assert suggest_order(titles) == ("P/z.mkv", "P/b2.mkv", "P/b10.mkv")


def test_a_season_without_episode_number_is_not_a_series() -> None:
    assert suggest_kind([title("F/F.S01E01.mkv"), title("F/Extra.mkv")]) == "movies"


# Tracks


def test_und_tracks_become_a_choosable_language() -> None:
    titles = [title("P/a.mp4", audio_tracks=[audio(1, None)])]
    assert audio_languages(titles) == ("und",)
    assert suggest_choices(titles, "P", dvd9).audio == ("und",)


def test_languages_are_the_union_in_order_of_appearance() -> None:
    titles = [title("P/a.mkv", [audio(1, "eng")], [sub(2, "eng")]),
              title("P/b.mkv", [audio(1, "por"), audio(2, "eng")], [sub(3, "por")])]  # fmt: skip
    assert audio_languages(titles) == ("en", "pt")
    assert subtitle_languages(titles) == ("en", "pt")


def test_unsupported_subtitles_are_not_languages() -> None:
    titles = [title("P/a.mkv", subtitles=[sub(2, "eng", codec="hdmv_pgs_subtitle")])]
    assert subtitle_languages(titles) == ()


def test_best_audio_prefers_more_channels_and_skips_commentary() -> None:
    t = title("P/a.mkv", [
        audio(1, "eng", 2), audio(2, "eng", 6, tags={"language": "eng", "title": "Commentary"}),
        audio(3, "eng", 6), audio(4, "eng", 6),
    ])  # fmt: skip
    best = best_audio(t, "en")
    assert best is not None and best.index == 3
    assert best_audio(t, "pt") is None


def test_best_audio_takes_a_commentary_when_it_is_the_only_one() -> None:
    t = title("P/a.mkv", [audio(1, "eng", 2, tags={"language": "eng", "title": "Comentário"})])
    best = best_audio(t, "en")
    assert best is not None and best.index == 1


def test_a_forced_only_subtitle_counts_as_missing() -> None:
    t = title("P/a.mkv", subtitles=[sub(3, "por", forced=True)])
    assert best_subtitle(t, "pt") is None


def test_best_subtitle_prefers_the_full_one() -> None:
    t = title("P/a.mkv", subtitles=[sub(3, "por", forced=True), sub(4, "por")])
    best = best_subtitle(t, "pt")
    assert best is not None and best.key == "s4"


def test_warnings_for_missing_languages() -> None:
    titles = [
        title("P/a.mkv", [audio(1, "por"), audio(2, "eng")], [sub(3, "por")], info=movie("A")),
        title("P/b.mkv", [audio(1, "por")], [sub(2, "por", forced=True)], info=movie("B")),
    ]
    c = choices(order=("P/a.mkv", "P/b.mkv"), audio=("pt", "en"), subtitles=("pt",))
    assert track_warnings(titles, c) == (
        "B não tem áudio em Inglês: toca em Português.",
        "B só tem a legenda forçada em Português: fica sem legenda.",
    )


def test_warning_for_a_missing_subtitle() -> None:
    titles = [title("P/a.mkv", subtitles=[sub(3, "eng")]), title("P/Bravo.mkv")]
    c = choices(order=("P/a.mkv", "P/Bravo.mkv", "P/gone.mkv"), subtitles=("en",))
    assert track_warnings(titles, c) == ("Bravo não tem legenda em Inglês.",)


# Suggestion


def test_suggestion_for_an_english_movie_with_portuguese_subtitles() -> None:
    titles = [title("P/a.mkv", [audio(1, "eng"), audio(2, "por", 2)], [sub(3, "por")],
                    chapters=3, info=movie("A", language="en"))]  # fmt: skip
    c = suggest_choices(titles, "P", dvd9)
    assert c == DiscChoices(kind="movies", order=("P/a.mkv",), profile="dvd9",
                            audio=("pt", "en"), subtitles=("pt",), subtitle_on=None,
                            chapters="file", minutes=5, theme=Theme())  # fmt: skip


def test_suggestion_turns_portuguese_subtitles_on_without_portuguese_audio() -> None:
    titles = [title("P/a.mkv", [audio(1, "jpn")], [sub(3, "por")])]
    c = suggest_choices(titles, "P", dvd9)
    assert (c.audio, c.subtitle_on, c.chapters) == (("ja",), "pt", "every")


def test_suggestion_uses_the_tmdb_original_language_when_a_track_has_it() -> None:
    titles = [title("P/a.mkv", [audio(1, "eng"), audio(2, "fre")], info=movie("A", language="fr"))]
    assert suggest_choices(titles, "P", dvd9).audio == ("fr",)


def test_suggestion_keeps_at_most_four_languages() -> None:
    assert len(suggest_choices([title("P/a.mkv")], "P", dvd9).audio) <= 4


def test_suggestion_asks_the_calculator_for_the_profile() -> None:
    seen: list[DiscChoices] = []

    def profile_for(draft: DiscChoices) -> str:
        seen.append(draft)
        return "dvd5"

    assert suggest_choices([title("P/a.mkv")], "P", profile_for).profile == "dvd5"
    assert seen[0].order == ("P/a.mkv",)


# Reconcile


def test_reconcile_without_a_saved_project_is_the_suggestion() -> None:
    titles = [title("P/a.mkv")]
    suggestion = suggest_choices(titles, "P", dvd9)
    assert reconcile(None, titles, suggestion, ()) == suggestion


def test_reconcile_survives_a_schema_change() -> None:
    titles = [title("P/a.mkv")]
    suggestion = suggest_choices(titles, "P", dvd9)
    assert reconcile('{"kind": "x"}', titles, suggestion, ()) == suggestion
    assert reconcile("not json", titles, suggestion, ()) == suggestion


def test_reconcile_drops_removed_videos_and_appends_new_ones() -> None:
    titles = [title("P/a.mkv"), title("P/b.mkv"), title("P/c.mkv")]
    suggestion = suggest_choices(titles, "P", dvd9)
    saved = choices(order=("P/c.mkv", "P/gone.mkv", "P/a.mkv")).model_dump_json()
    assert reconcile(saved, titles, suggestion, ()).order == ("P/c.mkv", "P/a.mkv", "P/b.mkv")


def test_reconcile_drops_what_no_longer_exists() -> None:
    titles = [title("P/a.mkv", [audio(1, "por")], [sub(2, "por")])]
    suggestion = suggest_choices(titles, "P", dvd9)
    saved = choices(profile="hddvd", audio=("en", "pt"), subtitles=("en", "pt"), subtitle_on="en",
                    theme=Theme(backdrop="Gone (2001)", accent="azul"))  # fmt: skip
    result = reconcile(saved.model_dump_json(), titles, suggestion, ("A (2001)",))
    assert (result.profile, result.audio, result.subtitles) == ("dvd9", ("pt",), ("pt",))
    assert result.subtitle_on is None
    assert result.theme == Theme(backdrop=None, accent="azul")


def test_reconcile_falls_back_to_the_suggested_audio_when_none_is_left() -> None:
    titles = [title("P/a.mkv", [audio(1, "por")])]
    suggestion = suggest_choices(titles, "P", dvd9)
    saved = choices(audio=("en",)).model_dump_json()
    assert reconcile(saved, titles, suggestion, ()).audio == ("pt",)


def test_reconcile_keeps_an_available_backdrop() -> None:
    titles = [title("P/a.mkv")]
    suggestion = suggest_choices(titles, "P", dvd9)
    saved = choices(theme=Theme(backdrop="A (2001)")).model_dump_json()
    assert reconcile(saved, titles, suggestion, ("A (2001)",)).theme.backdrop == "A (2001)"


# Errors


def test_choice_errors() -> None:
    titles = [title(f"P/{i}.mkv") for i in range(61)]
    c = choices(order=tuple(t.path for t in titles), audio=(), subtitles=tuple("abcde"))
    assert choice_errors(c, titles) == [
        "O disco aceita até 60 títulos nesta versão; esta pasta tem 61.",
        "Escolha ao menos um idioma de áudio.",
        "Escolha até 4 idiomas de legenda.",
    ]


def test_too_many_audio_languages() -> None:
    c = choices(audio=("pt", "en", "es", "fr", "de"))
    assert choice_errors(c, [title("P/a.mkv")]) == ["Escolha até 4 idiomas de áudio."]


def test_a_title_without_any_chosen_language_plays_its_own_first_track() -> None:
    titles = [title("P/Alfa.mkv", [audio(1, "jpn")])]
    c = choices(order=("P/Alfa.mkv",), audio=("pt",))
    assert track_warnings(titles, c) == ("Alfa não tem áudio em Português: toca em Japonês.",)


def test_a_title_without_audio_falls_back_to_no_language() -> None:
    titles = [title("P/Alfa.mkv", [])]
    c = choices(order=("P/Alfa.mkv",), audio=("pt",))
    warning = "Alfa não tem áudio em Português: toca em Idioma não informado."
    assert track_warnings(titles, c) == (warning,)


def test_language_names() -> None:
    assert [language_name(c) for c in ("pt", "und", "xx")] == [
        "Português", "Idioma não informado", "XX",
    ]  # fmt: skip


def test_disc_titles_skip_unscanned_files() -> None:
    scanned = title("P/a.mkv")
    files = (FileView(scanned.video, scanned.summary, None),
             FileView(title("P/b.mkv").video, None, "erro"))  # fmt: skip
    view = FolderView(name="P", status=Status.OK, files=files, size=2, duration=None)
    info = movie("A")
    result = disc_titles(view, {"P/a.mkv": info}, 2030)
    assert [(t.path, t.info) for t in result] == [("P/a.mkv", info)]


def test_disc_name_of_movies_without_a_collection_or_mixed() -> None:
    plain = [title("P/a.mkv", info=movie("a")), title("P/b.mkv", info=movie("b"))]
    mixed = [title("P/a.mkv", info=movie("a", collection="C")),
             title("P/b.mkv", info=episode("S", 1, 1, "x"))]  # fmt: skip
    assert disc_name(plain, "Pasta") == ("Pasta", None)
    assert disc_name(mixed, "Pasta") == ("Pasta", None)


def test_valid_choices_have_no_errors() -> None:
    assert choice_errors(choices(), [title("P/a.mkv")]) == []


def test_confirmed_episodes_order_by_tmdb_numbers() -> None:
    titles = [title("F/x.mkv", info=episode("F", 1, 2, "b")),
              title("F/y.mkv", info=episode("F", 1, 1, "a"))]  # fmt: skip
    assert suggest_order(titles) == ("F/y.mkv", "F/x.mkv")
    assert suggest_kind([title("F/F.S01E01.mkv", info=movie("m"))]) == "movies"


# Copying the video of DVD rips

RIP_VIDEO = {
    "index": 0, "codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 480,
    "r_frame_rate": "30000/1001", "avg_frame_rate": "30000/1001",
    "display_aspect_ratio": "16:9", "start_time": "0.000",
    "tags": {"NUMBER_OF_BYTES-eng": "3000000000"},
    "side_data_list": [{"side_data_type": "CPB properties", "max_bitrate": 9800000,
                        "buffer_size": 1835008}],
}  # fmt: skip


def rip(
    audio_tracks: list[dict[str, Any]] | None = None, video: dict[str, Any] | None = None,
    subtitles: list[dict[str, Any]] | None = None,
) -> DiscTitle:  # fmt: skip
    tracks = audio_tracks or [audio(1, "por", 6, bit_rate="448000"),
                              audio(2, "eng", 6, bit_rate="448000")]  # fmt: skip
    made = title("R/Rip.mkv", tracks, subtitles, video_stream=video or RIP_VIDEO)
    return replace(made, video=replace(made.video, size=4 * 10**9))


def test_a_dvd_rip_is_copied() -> None:
    assert is_rip(rip())
    assert copy_reason(rip(), choices(audio=("pt", "en"))) is None
    assert video_size(rip()) == 3_000_000_000


def test_a_movie_that_is_not_a_dvd_rip_is_never_a_rip() -> None:
    assert not is_rip(title("P/a.mkv"))
    no_header = {**RIP_VIDEO, "side_data_list": []}
    assert not is_rip(rip(video=no_header))
    header = {"side_data_type": "CPB properties", "max_bitrate": 15000000, "buffer_size": 1835008}
    tv = {**RIP_VIDEO, "side_data_list": [header]}
    assert not is_rip(rip(video=tv))
    narrow = {**RIP_VIDEO, "width": 704}
    assert not is_rip(rip(video=narrow))


def test_more_audio_than_the_original_disc_is_recoded() -> None:
    stereo = rip([audio(1, "por", 2, bit_rate="192000"), audio(2, "eng", 6, codec="dts")])
    # the DTS becomes 448k AC-3: more than the 192k the original disc carried with the video
    assert copy_reason(stereo, choices(audio=("pt", "en"))) == (
        "as faixas escolhidas pedem mais espaço que o disco original"
    )
    assert copy_reason(stereo, choices(audio=("pt",))) is None


def test_subtitles_count_in_the_budget() -> None:
    tight = rip([audio(1, "por", 2, bit_rate="192000")], subtitles=[sub(3, "por")])
    assert copy_reason(tight, choices(audio=("pt",), subtitles=("pt",))) is not None


def test_the_reencode_box_recodes_the_rips() -> None:
    assert copy_reason(rip(), choices(reencode_rips=True)) == "Recodificar os rips está marcado"


def test_the_video_size_without_the_tag_is_the_file_minus_the_audio() -> None:
    untagged = rip(video={**RIP_VIDEO, "tags": {}})
    tiny = replace(untagged, video=replace(untagged.video, size=1))
    assert video_size(tiny) is None  # the audio alone is bigger than the file
    assert copy_reason(tiny, choices()) == "tamanho do vídeo desconhecido"


def test_the_video_size_from_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    untagged = rip(video={**RIP_VIDEO, "tags": {}})
    sized = replace(untagged, video=replace(untagged.video, size=10**9))
    assert is_rip(sized)
    # 2700 s of 2 x 448 kbps of audio = 302.4 MB
    assert video_size(sized) == 10**9 - 302_400_000
    silent_rate = rip([audio(1, "por", 6)], video={**RIP_VIDEO, "tags": {}})
    assert video_size(replace(silent_rate, video=replace(silent_rate.video, size=10**9))) is None


def test_a_title_without_video_has_no_size_and_is_no_rip() -> None:
    blind = replace(rip(), summary=replace(rip().summary, video=None))
    assert video_size(blind) is None and not is_rip(blind)


def test_blu_ray_prefers_the_track_it_can_copy() -> None:
    found = title("P/a.mkv", [audio(1, "eng", 8, codec_name="truehd"), audio(2, "eng", 6)])
    master = audio(2, "eng", 8, codec_name="dts", profile="DTS-HD MA")
    lossless = title("P/b.mkv", [audio(1, "eng", 6), master])

    assert best_audio(found, "en").index == 1  # type: ignore[union-attr]  # DVD: more channels
    assert best_audio(found, "en", "bluray").index == 2  # type: ignore[union-attr]
    assert best_audio(lossless, "en", "bluray").index == 2  # type: ignore[union-attr]


def test_subtitle_languages_follow_the_medium() -> None:
    titles = [title("P/a.mkv", subtitles=[sub(2, "por", codec="hdmv_pgs_subtitle"), sub(3, "eng")])]

    assert subtitle_languages(titles) == ("en",)
    assert subtitle_languages(titles, "bluray") == ("pt", "en")
    assert best_subtitle(titles[0], "pt", "bluray") is not None
    assert best_subtitle(titles[0], "pt") is None


def test_reconcile_keeps_the_pgs_languages_only_on_blu_ray() -> None:
    titles = [title("P/a.mkv", subtitles=[sub(2, "por", codec="hdmv_pgs_subtitle")])]
    suggestion = suggest_choices(titles, "P", dvd9)
    on_bd = choices(profile="bd25", subtitles=("pt",), subtitle_on="pt").model_dump_json()
    on_dvd = choices(profile="dvd9", subtitles=("pt",), subtitle_on="pt").model_dump_json()

    assert reconcile(on_bd, titles, suggestion, ()).subtitles == ("pt",)
    assert reconcile(on_dvd, titles, suggestion, ()).subtitles == ()
