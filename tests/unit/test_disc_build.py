from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from projeto_dvd.library.files import ExternalSubtitle
from projeto_dvd.menus.theme import PALETTE
from projeto_dvd.planner.calculator import MENU_PAGE_BYTES, Quality
from projeto_dvd.planner.disc_build import (
    TitleSource,
    build_disc_plan,
    disc_errors,
    disc_estimate,
    menu_plan,
    title_plan,
)
from projeto_dvd.planner.disc_plan import Theme
from projeto_dvd.planner.profiles import DVD5, DVD9
from projeto_dvd.planner.source import VideoMode
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
    assert plan.estimated_bytes - without.size_bytes < len(menu.pages) * MENU_PAGE_BYTES + 1
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
