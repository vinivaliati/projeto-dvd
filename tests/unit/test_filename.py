import pytest

from projeto_dvd.metadata.filename import Guess, guess

Y = 2026


@pytest.mark.parametrize(
    ("path", "folder", "kind", "title", "year", "season", "episode"),
    [
        ("The.Lord.of.the.Rings.2001.1080p.BluRay.x264-GRUPO.mkv", "LOTR", "movie",
         "The Lord of the Rings", 2001, None, None),
        ("O Senhor dos Anéis (2001).mkv", "Senhor", "movie", "O Senhor dos Anéis", 2001,
         None, None),
        ("Cidade de Deus 2002 DUBLADO 720p.mkv", "x", "movie", "Cidade de Deus", 2002, None, None),
        ("Movie.2019.2160p.UHD.BDRemux.HDR.DV.TrueHD.Atmos.7.1-RARBG.mkv", "x", "movie",
         "Movie", 2019, None, None),
        ("Filme (Dublado) (2010).mkv", "x", "movie", "Filme", 2010, None, None),
        ("Amelie.2001.DDP5.1.NF.WEB-DL.mkv", "x", "movie", "Amelie", 2001, None, None),
        ("1917.mkv", "x", "movie", "1917", None, None, None),
        ("1917 (2019).mkv", "x", "movie", "1917", 2019, None, None),
        ("2012 2009 1080p.mkv", "x", "movie", "2012", 2009, None, None),
        ("2001 A Space Odyssey 1968.mkv", "x", "movie", "2001 A Space Odyssey", 1968, None, None),
        ("E.T.the.Extra-Terrestrial.1982.mkv", "x", "movie", "E.T. the Extra-Terrestrial",
         1982, None, None),
        ("Spider-Man.2002.mkv", "x", "movie", "Spider-Man", 2002, None, None),
        ("Friends.S01E03.720p.mkv", "x", "episode", "Friends", None, 1, 3),
        ("friends s1e3.mkv", "x", "episode", "friends", None, 1, 3),
        ("Friends 1x03.mkv", "x", "episode", "Friends", None, 1, 3),
        ("Friends T01E03.mkv", "x", "episode", "Friends", None, 1, 3),
        ("Friends Temporada 1 Episódio 3.mkv", "x", "episode", "Friends", None, 1, 3),
        ("Doctor.Who.2005.S01E01.mkv", "x", "episode", "Doctor Who", 2005, 1, 1),
        ("Show.S00E02.mkv", "x", "episode", "Show", None, 0, 2),
        ("S01E03.mkv", "Friends", "episode", "Friends", None, 1, 3),
        ("Temporada 2/03.mkv", "Friends", "episode", "Friends", None, 2, 3),
        ("Ep 03.mkv", "Friends Temporada 1", "episode", "Friends", None, 1, 3),
        ("EP03.mkv", "Friends T1", "episode", "Friends", None, 1, 3),
        ("Episódio 3.mkv", "Friends Season 1", "episode", "Friends", None, 1, 3),
        ("E03.mkv", "1ª Temporada", "episode", "1ª Temporada", None, 1, 3),
    ],
)  # fmt: skip
def test_guess(
    path: str,
    folder: str,
    kind: str,
    title: str,
    year: int | None,
    season: int | None,
    episode: int | None,
) -> None:
    result = guess(path, folder, Y)

    assert (result.kind, result.title, result.year, result.season, result.episode) == (
        kind, title, year, season, episode,
    )  # fmt: skip


def test_resolution_is_not_an_episode() -> None:
    result = guess("Movie 1920x1080 720x480.mkv", "x", Y)

    assert result.kind == "movie"
    assert result.title == "Movie 1920x1080 720x480"


def test_two_episodes_in_one_file() -> None:
    for name in ("Friends.S01E01E02.mkv", "Friends.S01E01-E02.mkv"):
        result = guess(name, "x", Y)
        assert (result.episode, result.episode_end) == (1, 2)
        assert result.warnings == ("Este arquivo tem dois episódios (E01 e E02).",)


@pytest.mark.parametrize("name", ["title_t00.mkv", "TITLE_01.mkv", "Disc 1.mkv", "Faixa 2.mkv",
                                  "12.mkv", "x.mkv", "[GRUPO].mkv"])  # fmt: skip
def test_generic_names_use_the_folder(name: str) -> None:
    result = guess(name, "Senhor dos Aneis (2001)", Y)

    assert result == Guess(kind="movie", title="Senhor dos Aneis", year=2001, from_folder=True)


def test_makemkv_volume_names() -> None:
    lotr = guess("LORD_OF_THE_RINGS_D1_t00.mkv", "Senhor", Y)
    friends = guess("Friends_S1_D1_t03.mkv", "Seriados", Y)

    assert (lotr.kind, lotr.title, lotr.from_folder) == ("movie", "LORD OF THE RINGS", False)
    assert lotr.fallback == "Senhor"
    assert (friends.kind, friends.title, friends.season, friends.episode) == (
        "episode", "Friends", 1, None,
    )  # fmt: skip


def test_makemkv_number_in_a_season_folder_is_not_an_episode() -> None:
    result = guess("Temporada 1/title_t03.mkv", "Friends", Y)

    assert (result.kind, result.episode, result.from_folder) == ("movie", None, True)
    assert result.title == "Friends"


def test_t2_in_a_movie_folder_is_not_a_season() -> None:
    result = guess("title_t00.mkv", "Exterminador do Futuro T2", Y)

    assert (result.kind, result.title, result.season) == (
        "movie", "Exterminador do Futuro T2", None,
    )  # fmt: skip


def test_future_year_is_not_a_year() -> None:
    assert guess("Blade Runner 2049.mkv", "x", 2026).year is None
    assert guess("Blade Runner 2049.mkv", "x", 2026).title == "Blade Runner 2049"


def test_fallback_is_the_folder_title_when_the_name_is_used() -> None:
    result = guess("Matrix.1999.mkv", "Trilogia Matrix", Y)

    assert result.fallback == "Trilogia Matrix"
