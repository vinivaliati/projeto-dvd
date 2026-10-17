"""The logical pages of a disc menu: what each page lists and where each button leads. Pure.

Page order: the main page, the list pages (movies or episodes), one audio page per option and
one subtitle page per option. The language pages are variants that differ only in the check
mark, so the viewer sees which option is on.
"""

from collections.abc import Sequence
from typing import Literal

from projeto_dvd.planner.disc_plan import Action, Kind, MenuItem, MenuPage

PAGE_SIZE = 6  # items of a normal list
LARGE_MAIN = 4  # a main page with up to 4 items uses the large type
LARGE_MAX = 5  # a language page with up to 5 lines uses the large type
BACK = MenuItem(label="Voltar", action="back")


def build_pages(
    kind: Kind,
    names: Sequence[str],
    disc_name: str,
    secondary: str | None,
    audio_labels: Sequence[str],
    subtitle_labels: Sequence[str],
) -> tuple[MenuPage, ...]:
    languages = []
    if len(audio_labels) > 1:
        languages.append(MenuItem(label="Áudio", action="audio_menu"))
    if subtitle_labels:
        languages.append(MenuItem(label="Legendas", action="subtitle_menu"))
    plays = [MenuItem(label=name, action="play", target=n) for n, name in enumerate(names, 1)]
    lists: list[MenuPage] = []
    if len(names) == 1:
        items = [MenuItem(label="Assistir", action="play", target=1), *languages]
    elif kind == "movies" and len(plays) + len(languages) <= PAGE_SIZE:
        items = [*plays, *languages]
    else:
        first = (
            MenuItem(label="Tocar todos", action="play_all")
            if kind == "series"
            else MenuItem(label="Filmes", action="page", target=1)
        )
        items = [first, *languages]
        if kind == "series":
            items.insert(1, MenuItem(label="Episódios", action="page", target=1))
        lists = _list_pages(kind, plays, disc_name)
    main = MenuPage(
        kind="main", heading=disc_name, secondary=secondary, items=tuple(items),
        large=len(items) <= LARGE_MAIN,
    )  # fmt: skip
    audio = [
        _variant("audio", "Áudio", list(audio_labels), option)
        for option in range(len(audio_labels))
    ]
    if len(audio_labels) <= 1:
        audio = []
    subtitle_options = ["Sem legenda", *subtitle_labels]
    subtitles = [
        _variant("subtitles", "Legendas", subtitle_options, option)
        for option in range(len(subtitle_options))
    ]
    if not subtitle_labels:
        subtitles = []
    return (main, *lists, *audio, *subtitles)


def page_of_title(pages: Sequence[MenuPage], title: int) -> tuple[int, int]:
    """The page index and the 1-based button that plays a title."""
    for index, page in enumerate(pages):
        for number, item in enumerate(page.items, 1):
            if item.action == "play" and item.target == title:
                return index, number
    raise LookupError(title)


def audio_variant(pages: Sequence[MenuPage], option: int) -> int:
    return _variant_index(pages, "audio", option)


def subtitle_variant(pages: Sequence[MenuPage], option: int) -> int:
    return _variant_index(pages, "subtitles", option)


def _list_pages(kind: Kind, plays: list[MenuItem], heading: str) -> list[MenuPage]:
    word = "Episódios" if kind == "series" else "Filmes"
    chunks = [plays[i : i + PAGE_SIZE] for i in range(0, len(plays), PAGE_SIZE)]
    pages = []
    for number, chunk in enumerate(chunks, 1):
        start = (number - 1) * PAGE_SIZE + 1
        previous = MenuItem(label="◀ Anterior", action="page", target=number - 1)
        following = MenuItem(label="Próxima ▶", action="page", target=number + 1)
        pages.append(
            MenuPage(
                kind="list",
                heading=heading,
                secondary=f"{word} {start} a {start + len(chunk) - 1} de {len(plays)}",
                items=tuple(chunk),
                footer=(
                    previous if number > 1 else None,
                    BACK,
                    following if number < len(chunks) else None,
                ),
            )
        )
    return pages


def _variant(
    kind: Literal["audio", "subtitles"], heading: str, labels: list[str], option: int
) -> MenuPage:
    action: Action = "audio" if kind == "audio" else "subtitle"
    items = [MenuItem(label=label, action=action, target=n) for n, label in enumerate(labels)]
    return MenuPage(
        kind=kind, heading=heading,
        items=(*items, BACK), checked=option, focus=option + 1,
        large=len(items) + 1 <= LARGE_MAX,
    )  # fmt: skip


def _variant_index(pages: Sequence[MenuPage], kind: str, option: int) -> int:
    return next(i for i, p in enumerate(pages) if p.kind == kind and p.checked == option)
