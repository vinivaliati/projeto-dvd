from projeto_dvd.menus.pages import (
    audio_variant,
    build_pages,
    page_of_title,
    subtitle_variant,
)
from projeto_dvd.planner.disc_plan import MenuItem, MenuPage

AUDIO = ("Português", "Inglês (original)")
SUBS = ("Português",)


def labels(page: MenuPage) -> list[str]:
    return [item.label for item in page.items]


def footer(page: MenuPage) -> list[str | None]:
    return [item.label if item else None for item in page.footer]


def test_one_title_has_watch_and_the_languages() -> None:
    pages = build_pages("movies", ["Up"], "Up", None, AUDIO, SUBS)

    main = pages[0]
    assert (main.kind, main.heading, main.large) == ("main", "Up", True)
    assert main.items == (
        MenuItem(label="Assistir", action="play", target=1),
        MenuItem(label="Áudio", action="audio_menu"),
        MenuItem(label="Legendas", action="subtitle_menu"),
    )


def test_languages_are_hidden_when_there_is_nothing_to_choose() -> None:
    pages = build_pages("movies", ["Up"], "Up", None, ("Português",), ())

    assert labels(pages[0]) == ["Assistir"]
    assert [p.kind for p in pages] == ["main"]


def test_few_movies_fit_the_large_main_page() -> None:
    pages = build_pages("movies", ["A", "B"], "Disco", None, AUDIO, SUBS)

    assert pages[0].large
    assert labels(pages[0]) == ["A", "B", "Áudio", "Legendas"]
    assert page_of_title(pages, 2) == (0, 2)


def test_up_to_six_items_use_the_normal_main_page() -> None:
    pages = build_pages("movies", ["A", "B", "C", "D"], "Disco", None, AUDIO, SUBS)

    assert not pages[0].large
    assert labels(pages[0]) == ["A", "B", "C", "D", "Áudio", "Legendas"]


def test_many_movies_get_their_own_pages() -> None:
    names = [f"Filme {i}" for i in range(1, 8)]

    pages = build_pages("movies", names, "Disco", None, AUDIO, SUBS)

    assert labels(pages[0]) == ["Filmes", "Áudio", "Legendas"]
    assert pages[0].items[0] == MenuItem(label="Filmes", action="page", target=1)
    first, second = pages[1], pages[2]
    assert labels(first) == names[:6] and labels(second) == names[6:]
    assert (first.secondary, second.secondary) == ("Filmes 1 a 6 de 7", "Filmes 7 a 7 de 7")
    assert footer(first) == [None, "Voltar", "Próxima ▶"]
    assert footer(second) == ["◀ Anterior", "Voltar", None]
    assert second.footer[0] == MenuItem(label="◀ Anterior", action="page", target=1)
    assert page_of_title(pages, 7) == (2, 1)


def test_a_series_has_play_all_and_episode_pages() -> None:
    names = [f"{i}. Episódio" for i in range(1, 14)]

    pages = build_pages("series", names, "Friends", "Temporada 1", AUDIO, SUBS)

    main = pages[0]
    assert (main.heading, main.secondary, main.large) == ("Friends", "Temporada 1", True)
    assert main.items[:2] == (
        MenuItem(label="Tocar todos", action="play_all"),
        MenuItem(label="Episódios", action="page", target=1),
    )
    lists = [p for p in pages if p.kind == "list"]
    assert [len(p.items) for p in lists] == [6, 6, 1]
    assert lists[2].secondary == "Episódios 13 a 13 de 13"
    assert page_of_title(pages, 13) == (3, 1)


def test_audio_variants_check_each_option() -> None:
    pages = build_pages("movies", ["Up"], "Up", None, AUDIO, SUBS)

    variant = pages[audio_variant(pages, 1)]
    assert (variant.kind, variant.heading, variant.checked, variant.focus) == (
        "audio", "Áudio", 1, 2,
    )  # fmt: skip
    assert variant.items == (
        MenuItem(label="Português", action="audio", target=0),
        MenuItem(label="Inglês (original)", action="audio", target=1),
        MenuItem(label="Voltar", action="back"),
    )
    assert variant.large


def test_subtitle_variants_start_with_no_subtitle() -> None:
    pages = build_pages("movies", ["Up"], "Up", None, AUDIO, ("Português", "Inglês"))

    off = pages[subtitle_variant(pages, 0)]
    assert labels(off) == ["Sem legenda", "Português", "Inglês", "Voltar"]
    assert off.items[1] == MenuItem(label="Português", action="subtitle", target=1)
    assert (off.checked, off.focus) == (0, 1)
    assert pages[subtitle_variant(pages, 2)].checked == 2


def test_six_subtitle_lines_use_the_normal_size() -> None:
    subs = ("Português", "Inglês", "Espanhol", "Francês")
    pages = build_pages("movies", ["Up"], "Up", None, AUDIO, subs)

    assert not pages[subtitle_variant(pages, 0)].large
    assert pages[audio_variant(pages, 0)].large


def test_page_of_an_unknown_title_is_an_error() -> None:
    pages = build_pages("movies", ["Up"], "Up", None, AUDIO, SUBS)
    try:
        page_of_title(pages, 5)
    except LookupError:
        return
    raise AssertionError("expected LookupError")
