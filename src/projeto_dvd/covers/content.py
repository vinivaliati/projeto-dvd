"""The text of a disc cover, from the saved disc choices and the confirmed matches. Pure."""

from collections.abc import Sequence
from dataclasses import dataclass

from projeto_dvd.api.formatting import format_duration
from projeto_dvd.metadata.details import TitleInfo, generic_episode_name
from projeto_dvd.planner.disc import DiscTitle, disc_name, menu_name
from projeto_dvd.planner.disc_plan import DiscChoices
from projeto_dvd.planner.languages import language_name
from projeto_dvd.planner.profiles import PROFILES
from projeto_dvd.planner.source import geometry

CAST = 5


@dataclass(frozen=True)
class CoverLine:
    """A title on the back of the cover."""

    title: str
    detail: str | None  # "2001 · 2h58", or the duration
    synopsis: str | None


@dataclass(frozen=True)
class CoverContent:
    disc_name: str
    secondary: str | None
    front_text: str
    spine_text: str
    spine_extra: str | None  # the year or "T1", in the accent color
    synopsis: str | None  # the movie of a one movie disc, or the series of a season
    cast: tuple[str, ...]
    lines: tuple[CoverLine, ...]  # empty for a one movie disc (the synopsis tells it)
    tech: tuple[tuple[str, str], ...]
    tmdb: bool  # TMDB text or art on the cover: the attribution goes on the back
    profile: str


def cover_content(
    choices: DiscChoices, titles: Sequence[DiscTitle], folder: str, art_from_tmdb: bool
) -> CoverContent:
    by_path = {t.path: t for t in titles}
    ordered = [by_path[path] for path in choices.order if path in by_path]
    name, secondary = disc_name(ordered, folder)
    infos = [t.info for t in ordered if t.info is not None]
    matched = len(infos) == len(ordered) > 0
    episodes = matched and all(i.kind == "episode" for i in infos)
    one_movie = matched and len(infos) == 1 and infos[0].kind == "movie"
    front, extra = _front(ordered, infos, episodes, one_movie)
    synopsis: str | None = None
    if one_movie:
        synopsis = infos[0].overview or None
    elif episodes and len({i.show for i in infos}) == 1:
        synopsis = infos[0].show_overview or None
    cover = choices.cover
    return CoverContent(
        disc_name=name, secondary=secondary,
        front_text=front if cover.front_text is None else cover.front_text,
        spine_text=name if cover.spine_text is None else cover.spine_text,
        spine_extra=extra if cover.spine_text is None else None,
        synopsis=synopsis, cast=tuple(infos[0].cast[:CAST]) if one_movie else (),
        lines=() if one_movie else tuple(_line(t) for t in ordered),
        tech=_tech(choices, ordered), tmdb=art_from_tmdb or bool(infos),
        profile=PROFILES[choices.profile].name,
    )  # fmt: skip


def _front(
    ordered: Sequence[DiscTitle], infos: Sequence[TitleInfo], episodes: bool, one_movie: bool
) -> tuple[str, str | None]:
    """The line at the foot of the front and the complement on the spine."""
    if one_movie:
        year = infos[0].year
        return (str(year), str(year)) if year else ("", None)
    if episodes:
        seasons = sorted({i.season or 0 for i in infos})
        if seasons == [0]:
            return "Especiais", None
        if len(seasons) > 1:
            numbers = [str(s) for s in seasons]
            return f"Temporadas {', '.join(numbers[:-1])} e {numbers[-1]}", None
        count = sum((i.episode_end or i.episode or 0) - (i.episode or 0) + 1 for i in infos)
        noun = "episódio" if count == 1 else "episódios"
        return f"Temporada {seasons[0]} · {count} {noun}", f"T{seasons[0]}"
    if len(ordered) == 1:
        return "", None
    kinds = {t.info.kind if t.info else t.guess.kind for t in ordered}
    noun = (
        {"movie": "filmes", "episode": "episódios"}.get(kinds.pop(), "") if len(kinds) == 1 else ""
    )
    return f"{len(ordered)} {noun or 'títulos'}", None


def _line(title: DiscTitle) -> CoverLine:
    duration = format_duration(title.summary.duration)
    info = title.info
    if info is None:
        return CoverLine(menu_name(title), duration, None)
    if info.kind == "episode":
        number = f"{info.episode}-{info.episode_end}" if info.episode_end else f"{info.episode}"
        name = f"{number}." if generic_episode_name(info.title) else f"{number}. {info.title}"
        return CoverLine(name, duration, None)
    detail = f"{info.year} · {duration}" if info.year else duration
    return CoverLine(info.title, detail, info.overview or None)


def _tech(choices: DiscChoices, ordered: Sequence[DiscTitle]) -> tuple[tuple[str, str], ...]:
    total = format_duration(sum(t.summary.duration or 0.0 for t in ordered))
    aspects = {geometry(t.summary.video).aspect for t in ordered if t.summary.video}
    subtitles = ", ".join(language_name(code) for code in choices.subtitles)
    return (
        ("Duração", f"{total} no total" if len(ordered) > 1 else total),
        ("Áudio", ", ".join(language_name(code) for code in choices.audio)),
        ("Legendas", subtitles or "Nenhuma"),
        ("Vídeo", f"DVD-Video · NTSC · {'4:3' if aspects == {'4:3'} else '16:9'}"),
        ("Disco", PROFILES[choices.profile].name),
    )
