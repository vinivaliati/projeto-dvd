from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from projeto_dvd.library.files import ExternalSubtitle
from projeto_dvd.menus.theme import PALETTE
from projeto_dvd.planner.bd_source import HeaderReport
from projeto_dvd.planner.calculator import Quality, menu_bytes
from projeto_dvd.planner.disc import BD_ONE_TITLE, bd_eligible, reconcile
from projeto_dvd.planner.disc_build import (
    TitleSource,
    build_disc_plan,
    disc_errors,
    disc_estimate,
    disc_estimates,
    menu_plan,
    profile_for,
    title_plan,
)
from projeto_dvd.planner.disc_plan import Theme
from projeto_dvd.planner.dvd_plan import bd_volume_label, iso_name
from projeto_dvd.planner.profiles import DVD5, DVD9
from projeto_dvd.planner.source import BD_SD, VideoMode
from tests.unit.test_disc import VIDEO, audio, choices, episode, movie, sub, title


def source(path: str, *args: Any, **kwargs: Any) -> TitleSource:
    return TitleSource(title(path, *args, **kwargs), VideoMode.FILM, True)


def test_tracks_follow_the_disc_languages() -> None:
    s = source("P/a.mkv", [audio(1, "eng", 2), audio(2, "por", 6)], [sub(3, "por")], chapters=3)
    c = choices(audio=("pt", "en"), subtitles=("pt",), chapters="file")

    plan = title_plan(s, c, "A")

    assert [(a.index, a.language) for a in plan.audio] == [(2, "pt"), (1, "en")]
    assert (plan.audio_map, plan.subtitle_map) == ((0, 1), (0,))
    assert [(x.key, x.stream_index, x.language) for x in plan.subtitles] == [("s3", 3, "pt")]
    assert plan.chapters == (0.0, 60.0, 120.0) and plan.menu_name == "A"
    assert (plan.aspect, plan.mode, plan.path) == ("16:9", VideoMode.FILM, "P/a.mkv")


def test_a_missing_language_maps_to_the_first_track_of_the_title() -> None:
    plan = title_plan(source("P/a.mkv", [audio(1, "por")]), choices(audio=("en", "pt")), "A")
    assert [a.index for a in plan.audio] == [1]
    assert plan.audio_map == (0, 0)


def test_a_title_without_any_chosen_language_keeps_its_first_track() -> None:
    plan = title_plan(source("P/a.mkv", [audio(4, "jpn")]), choices(audio=("pt",)), "A")
    assert [a.index for a in plan.audio] == [4] and plan.audio_map == (0,)


def test_und_tracks_have_no_language() -> None:
    plan = title_plan(source("P/a.mp4", [audio(1, None)]), choices(audio=("und",)), "A")
    assert plan.audio[0].language is None and plan.audio_map == (0,)


def test_two_languages_on_the_same_track_are_not_duplicated() -> None:
    s = source("P/a.mkv", [audio(1, "por")], [sub(2, "eng")])
    plan = title_plan(s, choices(audio=("pt",), subtitles=("pt", "en")), "A")
    assert plan.subtitle_map == (None, 0) and len(plan.subtitles) == 1


def test_an_external_srt_keeps_its_path() -> None:
    external = (ExternalSubtitle(name="a.pt.srt", language="pt", image=False),)
    plan = title_plan(source("P/sub/a.mkv", external=external), choices(subtitles=("pt",)), "A")
    assert [(x.key, x.file) for x in plan.subtitles] == [("f:a.pt.srt", "P/sub/a.pt.srt")]


def test_menu_plan_for_a_series(tmp_path: Path) -> None:
    titles = [title("F/a.mkv", [audio(1, "por"), audio(2, "eng")], [sub(3, "por")],
                    info=episode("Friends", 1, n, f"Ep {n}")) for n in (1, 2)]  # fmt: skip
    c = choices(kind="series", order=("F/a.mkv",), audio=("pt", "en"), subtitles=("pt",),
                theme=Theme(accent="verde", side="right"))  # fmt: skip
    backdrop = tmp_path / "b.jpg"

    plan = menu_plan(c, titles[:1], "F", backdrop, None)

    assert (plan.aspect, plan.accent, plan.side) == ("16:9", PALETTE["verde"][1], "right")
    assert plan.backdrop == str(backdrop)
    main = plan.pages[0]
    assert (main.heading, main.secondary) == ("Friends", "Temporada 1")
    audio_page = next(p for p in plan.pages if p.kind == "audio")
    assert [i.label for i in audio_page.items] == ["Português", "Inglês (original)", "Voltar"]


def test_menu_plan_strips_the_disc_name_and_picks_the_auto_accent() -> None:
    saga = "O Senhor dos Anéis"
    titles = [title(f"P/{n}.mkv", info=movie(f"{saga}: {n}", collection=saga))
              for n in ("A Sociedade do Anel", "As Duas Torres")]  # fmt: skip
    c = choices(order=tuple(t.path for t in titles))
    blue = Image.new("RGB", (64, 36), (30, 60, 200))

    plan = menu_plan(c, titles, "P", None, blue)

    assert [i.label for i in plan.pages[0].items] == ["A Sociedade do Anel", "As Duas Torres"]
    assert (plan.accent, plan.backdrop) == (PALETTE["azul"][1], None)


def test_menus_are_4_3_only_when_every_title_is() -> None:
    narrow = {**VIDEO, "width": 720, "height": 480, "display_aspect_ratio": "4:3"}
    old = [title("P/a.mkv", video_stream=narrow), title("P/b.mkv", video_stream=narrow)]
    mixed = [old[0], title("P/c.mkv")]
    assert menu_plan(choices(order=("P/a.mkv", "P/b.mkv")), old, "P", None, None).aspect == "4:3"
    assert menu_plan(choices(order=("P/a.mkv", "P/c.mkv")), mixed, "P", None, None).aspect == "16:9"


def test_build_disc_plan_shares_one_bitrate_and_counts_the_menus() -> None:
    sources = [source("P/b.mkv", duration=3000.0), source("P/a.mkv", duration=2000.0)]
    c = choices(order=("P/a.mkv", "P/b.mkv"), subtitles=(), profile="dvd9")
    menu = menu_plan(c, [s.title for s in sources], "P", None, None)

    plan = build_disc_plan("P", sources, c, menu, confirm_low=True, replace_iso=False)

    assert [t.path for t in plan.titles] == ["P/a.mkv", "P/b.mkv"]
    expected = disc_estimate(DVD9, plan.titles, len(menu.pages))
    assert (plan.video_kbps, plan.estimated_bytes) == (expected.video_kbps, expected.size_bytes)
    without = disc_estimate(DVD9, plan.titles, 0)
    assert plan.estimated_bytes - without.size_bytes < menu_bytes(len(menu.pages)) + 1
    assert (plan.volume, plan.iso_name, plan.confirmed_low) == ("P", "P.iso", True)
    assert plan.subtitle_on == 0


def test_subtitle_on_is_the_language_position_plus_one() -> None:
    sources = [source("P/a.mkv", subtitles=[sub(2, "eng"), sub(3, "por")])]
    c = choices(subtitles=("en", "pt"), subtitle_on="pt")
    menu = menu_plan(c, [sources[0].title], "P", None, None)
    assert build_disc_plan("P", sources, c, menu, False, False).subtitle_on == 2


def test_disc_errors() -> None:
    titles = [title("P/a.mkv", duration=40000.0)]
    c = choices()
    plan = title_plan(TitleSource(titles[0], VideoMode.FILM, True), c, "A")
    too_long = disc_estimate(DVD5, [plan], 3)
    assert too_long.quality == Quality.DOES_NOT_FIT
    assert disc_errors(c, titles, too_long, confirm_low=False) == ["O disco não cabe no DVD-5."]
    long_movie = TitleSource(title("P/a.mkv", duration=9000.0), VideoMode.FILM, True)
    low = disc_estimate(DVD5, [title_plan(long_movie, c, "A")], 3)
    assert low.quality == Quality.LOW
    assert disc_errors(c, titles, low, confirm_low=False) == [
        "Confirme que quer gerar com qualidade baixa.",
    ]  # fmt: skip
    assert disc_errors(c, titles, low, confirm_low=True) == []
    assert disc_errors(c.model_copy(update={"audio": ()}), titles, low, True) == [
        "Escolha ao menos um idioma de áudio.",
    ]  # fmt: skip


def test_a_single_title_keeps_its_own_name_not_the_button_label() -> None:
    sources = [source("P/a.mkv", info=movie("Up"))]
    c = choices()
    menu = menu_plan(c, [sources[0].title], "P", None, None)
    assert menu.pages[0].items[0].label == "Assistir"
    assert build_disc_plan("P", sources, c, menu, False, False).titles[0].menu_name == "Up"


def test_a_source_without_duration_is_refused() -> None:
    good = title("P/a.mkv")
    bad = replace(good, summary=replace(good.summary, duration=None))
    with pytest.raises(ValueError, match="without video or duration"):
        title_plan(TitleSource(bad, VideoMode.FILM, True), choices(), "A")


# DVD rips


def rip_source(gop_fields: int | None = 30, **title_kwargs: Any) -> TitleSource:
    from tests.unit.test_disc import rip

    return TitleSource(rip(**title_kwargs), VideoMode.FILM, True, gop_fields)


def test_a_rip_is_planned_as_copied_video() -> None:
    plan = title_plan(rip_source(), choices(audio=("pt", "en")), "Rip")

    assert (plan.copy_video, plan.video_bytes) == (True, 3_000_000_000)
    assert plan.chapters == (0.0,)  # no chapters in the file: just the start


def test_a_copied_rip_keeps_the_chapters_of_the_file() -> None:
    from tests.unit.test_disc import RIP_VIDEO, rip

    made = rip()
    with_chapters = replace(made, summary=replace(made.summary, chapters=(0.0, 600.0, 1200.0)))
    source = TitleSource(with_chapters, VideoMode.FILM, True, 30)

    plan = title_plan(source, choices(chapters="every", minutes=5), "Rip")

    assert plan.chapters == (0.0, 600.0, 1200.0)
    assert RIP_VIDEO["codec_name"] == "mpeg2video"


def test_a_long_gop_in_the_sample_recodes_the_rip() -> None:
    plan = title_plan(rip_source(gop_fields=38), choices(), "Rip")
    assert (plan.copy_video, plan.video_bytes) == (False, None)


def test_the_estimate_counts_the_copied_size() -> None:
    copied = title_plan(rip_source(), choices(), "Rip")
    recoded = title_plan(rip_source(), choices(reencode_rips=True), "Rip")

    assert disc_estimate(DVD9, [copied], 1).video_kbps == 0
    assert disc_estimate(DVD9, [recoded], 1).video_kbps > 0


# Blu-ray (Phase 6a)

BD_REMUX = {**VIDEO, "profile": "High", "level": 41, "pix_fmt": "yuv420p",
            "sample_aspect_ratio": "1:1", "tags": {"NUMBER_OF_BYTES": "20000000000"}}  # fmt: skip
GOOD = HeaderReport(hrd=True, slices=4, max_dec_frame_buffering=4)


def bd_source(video: dict[str, Any] = BD_REMUX, tracks: list[dict[str, Any]] | None = None,
              headers: HeaderReport | None = GOOD, **kwargs: Any) -> TitleSource:  # fmt: skip
    found = title("P/a.mkv", tracks or [audio(1, "por", bit_rate="640000")],
                  video_stream=video, **kwargs)  # fmt: skip
    found = replace(found, video=replace(found.video, size=25_000_000_000))
    return TitleSource(found, VideoMode.FILM, True, headers=headers, gop_frames=24)


def test_a_blu_ray_remux_is_planned_as_copied() -> None:
    plan = title_plan(bd_source(), choices(profile="bd50"), "A")

    assert plan.copy_video and plan.video_bytes == 20_000_000_000
    assert (plan.width, plan.height, plan.scale) == (1920, 1080, False)
    assert [(a.action, a.kbps, a.codec) for a in plan.audio] == [("copy", 640, "ac3")]


def test_a_web_file_is_encoded_with_the_frame_padded() -> None:
    web = {**VIDEO, "height": 800}
    plan = title_plan(bd_source(web, headers=replace(GOOD, hrd=False)), choices(profile="bd25"),
                      "A")  # fmt: skip

    assert not plan.copy_video
    assert (plan.width, plan.height, plan.scale) == (1920, 1080, False)


def test_an_anamorphic_1440_is_scaled_only_when_encoded() -> None:
    anamorphic = {**BD_REMUX, "width": 1440, "sample_aspect_ratio": "4:3"}

    copied = title_plan(bd_source(anamorphic), choices(profile="bd25"), "A")
    encoded = title_plan(bd_source(anamorphic), choices(profile="bd25", reencode_rips=True), "A")

    assert copied.copy_video and not copied.scale
    assert not encoded.copy_video and (encoded.width, encoded.scale) == (1920, True)


def test_720p_stays_720p() -> None:
    plan = title_plan(bd_source({**VIDEO, "width": 1280, "height": 720}), choices(profile="bd25"),
                      "A")  # fmt: skip

    assert (plan.width, plan.height, plan.copy_video) == (1280, 720, False)


def test_delayed_audio_that_cannot_be_padded_becomes_ac3() -> None:
    late = [audio(1, "por", 6, codec_name="dts", profile="DTS", start_time="0.5"),
            audio(2, "eng", 2, codec_name="pcm_s24le", start_time="0.5")]  # fmt: skip
    plan = title_plan(bd_source(tracks=late), choices(profile="bd25", audio=("pt", "en")), "A")

    assert [(a.action, a.kbps, a.offset) for a in plan.audio] == [("ac3", 640, 0.5),
                                                                   ("copy", 2304, 0.5)]  # fmt: skip


def test_pgs_and_text_subtitles_on_blu_ray() -> None:
    subs = [sub(3, "por", codec="hdmv_pgs_subtitle"), sub(4, "eng")]
    plan = title_plan(bd_source(subtitles=subs), choices(profile="bd25", subtitles=("pt", "en")),
                      "A")  # fmt: skip

    assert [(s.key, s.codec) for s in plan.subtitles] == [("s3", "pgs"), ("s4", "text")]


def test_blu_ray_chapters_go_past_99() -> None:
    plan = title_plan(bd_source(chapters=150, duration=9000.0),
                      choices(profile="bd25", chapters="file"), "A")  # fmt: skip

    assert len(plan.chapters) == 150


def test_build_a_blu_ray_plan() -> None:
    s = bd_source()
    plan = build_disc_plan("O Senhor dos Anéis", [s], choices(profile="bd50"), None, False, False)

    assert plan.menu is None and plan.maxrate_kbps == 0  # copied: nothing to encode
    assert (plan.volume, plan.iso_name) == ("O Senhor dos Aneis", "O Senhor dos Anéis (BD).iso")
    encoded = build_disc_plan("F", [s], choices(profile="bd50", reencode_rips=True), None,
                              False, False)  # fmt: skip
    assert encoded.maxrate_kbps == 35_000 and encoded.video_kbps > 15_000


@pytest.mark.parametrize(
    ("folder", "label"),
    [("O Senhor dos Anéis: A Sociedade do Anel", "O Senhor dos Aneis A Sociedade"),
     ("ÉÇ!", "EC"), ("!!", "DISC")],
)  # fmt: skip
def test_bd_volume_label(folder: str, label: str) -> None:
    assert bd_volume_label(folder) == label


def test_iso_name() -> None:
    assert (iso_name("Filme", "dvd"), iso_name("Filme", "bluray")) == ("Filme.iso",
                                                                      "Filme (BD).iso")  # fmt: skip


def test_blu_ray_estimates_only_for_one_eligible_video() -> None:
    one = [bd_source().title]
    two = [bd_source().title, replace(bd_source().title, path="P/b.mkv")]
    sd = [title("P/a.mkv", video_stream={**VIDEO, "width": 720, "height": 480})]

    keys = [e.profile.key for e in disc_estimates(choices(), one, "P")]
    assert keys == ["dvd5", "dvd9", "bd25", "bd50"]
    assert bd_eligible(one) is None
    assert bd_eligible(two) == BD_ONE_TITLE
    assert bd_eligible(sd) == f"Blu-ray: {BD_SD}"
    two_choices = choices(order=("P/a.mkv", "P/b.mkv"))
    assert [e.profile.key for e in disc_estimates(two_choices, two, "P")] == ["dvd5", "dvd9"]


def test_an_hd_video_suggests_blu_ray() -> None:
    assert profile_for([bd_source().title], "P")(choices()) == "bd25"
    big = {**BD_REMUX, "tags": {"NUMBER_OF_BYTES": "30000000000"}}
    found = bd_source(big).title
    found = replace(found, video=replace(found.video, size=40_000_000_000))
    assert profile_for([found], "P")(choices()) == "bd50"


def test_reconcile_leaves_blu_ray_when_the_folder_gets_a_second_video() -> None:
    two = [bd_source().title, replace(bd_source().title, path="P/b.mkv")]
    suggestion = choices(order=("P/a.mkv", "P/b.mkv"), profile="dvd9")
    saved = choices(profile="bd25").model_dump_json()

    assert reconcile(saved, two, suggestion, ()).profile == "dvd9"
