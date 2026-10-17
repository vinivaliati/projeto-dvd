from typing import Any

import pytest

from projeto_dvd.covers.content import CoverLine, cover_content
from projeto_dvd.covers.sizes import DPI, CaseSize, LabelSheet, px
from projeto_dvd.metadata.details import TitleInfo
from projeto_dvd.planner.disc import DiscTitle
from projeto_dvd.planner.disc_plan import CoverChoices
from tests.unit.test_disc import VIDEO, choices, episode, title

SD_43 = {**VIDEO, "width": 720, "height": 480, "display_aspect_ratio": "4:3"}


def film(name: str, year: int, overview: str = "", cast: tuple[str, ...] = ()) -> TitleInfo:
    return TitleInfo(kind="movie", tmdb_id=1, title=name, year=year, overview=overview,
                     cast=list(cast), runtime=999)  # fmt: skip


def content(titles: list[DiscTitle], tmdb_art: bool = False, **overrides: Any) -> Any:
    fields: dict[str, Any] = {"order": tuple(t.path for t in titles)}
    fields.update(overrides)
    return cover_content(choices(**fields), titles, "Pasta", tmdb_art)


def test_px_converts_millimeters_at_a_dpi() -> None:
    assert px(25.4, DPI) == 300
    assert px(183.0, 50) == 360
    assert 2 * CaseSize().panel_width + CaseSize().spine == 273.0
    assert LabelSheet().centers == ((105.0, 78.5), (105.0, 218.5))


def test_one_movie_has_the_year_the_synopsis_and_five_names_of_the_cast() -> None:
    cast = ("A", "B", "C", "D", "E", "F")
    info = film("Matrix", 1999, "Um hacker descobre.", cast)
    result = content([title("P/a.mkv", info=info, duration=8160.0)])

    assert (result.disc_name, result.secondary) == ("Matrix", None)
    assert result.front_text == "1999"
    assert (result.spine_text, result.spine_extra) == ("Matrix", "1999")
    assert result.synopsis == "Um hacker descobre."
    assert result.cast == ("A", "B", "C", "D", "E")
    assert result.lines == ()
    assert result.tech[0] == ("Duração", "2h16")  # the file, not the TMDB runtime
    assert result.tmdb


def test_several_movies_list_each_one_with_a_short_synopsis() -> None:
    titles = [
        title("P/a.mkv", info=film("Um", 2001, "Primeiro."), duration=10680.0),
        title("P/b.mkv", info=film("Dois", 2002, "Segundo."), duration=600.0),
        title("P/Filme Três.mkv", duration=3600.0),
    ]
    result = content(titles)

    assert result.front_text == "3 filmes"
    assert result.spine_extra is None
    assert result.synopsis is None and result.cast == ()
    assert result.lines == (
        CoverLine("Um", "2001 · 2h58", "Primeiro."),
        CoverLine("Dois", "2002 · 10 min", "Segundo."),
        CoverLine("Filme Três", "1h00", None),
    )
    assert result.tech[0] == ("Duração", "4h08 no total")


def test_a_season_lists_its_episodes_under_the_series_synopsis() -> None:
    def ep(number: int, name: str, end: int | None = None) -> TitleInfo:
        info = episode("Friends", 1, number, name)
        return info.model_copy(update={"episode_end": end, "show_overview": "Seis amigos."})

    titles = [
        title("P/1.mkv", info=ep(1, "Piloto", end=2), duration=2640.0),
        title("P/3.mkv", info=ep(3, "Episódio 3"), duration=1320.0),
    ]
    result = content(titles, kind="series")

    assert (result.disc_name, result.secondary) == ("Friends", "Temporada 1")
    assert result.front_text == "Temporada 1 · 3 episódios"
    assert (result.spine_text, result.spine_extra) == ("Friends", "T1")
    assert result.synopsis == "Seis amigos."
    assert result.cast == ()
    assert result.lines == (CoverLine("1-2. Piloto", "44 min", None),
                            CoverLine("3.", "22 min", None))  # fmt: skip


@pytest.mark.parametrize(
    ("seasons", "front", "extra"),
    [((0, 0), "Especiais", None), ((1, 2), "Temporadas 1 e 2", None),
     ((1, 2, 3), "Temporadas 1, 2 e 3", None), ((4,), "Temporada 4 · 1 episódio", "T4")],
)  # fmt: skip
def test_the_front_names_the_seasons(
    seasons: tuple[int, ...], front: str, extra: str | None
) -> None:
    titles = [
        title(f"P/{n}.mkv", info=episode("Friends", season, n + 1, f"Nome {n}"))
        for n, season in enumerate(seasons)
    ]
    result = content(titles, kind="series")

    assert (result.front_text, result.spine_extra) == (front, extra)


def test_without_a_match_the_lines_use_the_menu_names() -> None:
    titles = [title("P/Show S01E01.mkv"), title("P/Show S01E02.mkv")]
    result = content(titles, kind="series")

    assert result.disc_name == "Pasta"
    assert result.front_text == "2 episódios"
    assert [line.title for line in result.lines] == ["Episódio 1", "Episódio 2"]
    assert result.synopsis is None
    assert not result.tmdb


def test_one_unmatched_movie_is_a_line_and_tmdb_art_still_needs_the_attribution() -> None:
    result = content([title("P/Filme Caseiro.mkv", duration=5400.0)], tmdb_art=True)

    assert result.front_text == ""
    assert result.lines == (CoverLine("Filme Caseiro", "1h30", None),)
    assert result.tmdb


def test_a_mixed_disc_counts_titles() -> None:
    titles = [title("P/a.mkv", info=film("Um", 2001)),
              title("P/b.mkv", info=episode("Friends", 1, 1, "Piloto"))]  # fmt: skip
    result = content(titles)

    assert result.front_text == "2 títulos"
    assert [line.title for line in result.lines] == ["Um", "1. Piloto"]


def test_edited_texts_win() -> None:
    cover = CoverChoices(front_text="Edição especial", spine_text="Matrix 1")
    result = content([title("P/a.mkv", info=film("Matrix", 1999))], cover=cover)

    assert result.front_text == "Edição especial"
    assert (result.spine_text, result.spine_extra) == ("Matrix 1", None)


def test_the_technical_box() -> None:
    titles = [title("P/a.mkv", video_stream=SD_43, duration=1800.0)]
    result = content(titles, audio=("pt", "en"), subtitles=("pt",), profile="dvd5")

    assert result.tech == (
        ("Duração", "30 min"),
        ("Áudio", "Português, Inglês"),
        ("Legendas", "Português"),
        ("Vídeo", "DVD-Video · NTSC · 4:3"),
        ("Disco", "DVD-5"),
    )
    assert result.profile == "DVD-5"
    no_subtitles = content([title("P/a.mkv")])
    assert ("Legendas", "Nenhuma") in no_subtitles.tech
    assert ("Vídeo", "DVD-Video · NTSC · 16:9") in no_subtitles.tech


def test_titles_out_of_the_disc_order_are_left_out() -> None:
    titles = [title("P/a.mkv", info=film("Um", 2001)), title("P/b.mkv", info=film("Dois", 2002))]
    result = cover_content(choices(order=("P/b.mkv",)), titles, "Pasta", False)

    assert result.disc_name == "Dois"
