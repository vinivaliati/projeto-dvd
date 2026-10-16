"""The disc of a folder: titles, names, order, tracks by language, suggestion, reconciliation.

Pure: the screens and the job read the folder and TMDB elsewhere and pass them in.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import ValidationError

from projeto_dvd.library.files import VideoFile, natural_key
from projeto_dvd.library.probe import AudioTrack, Summary
from projeto_dvd.library.scan import FolderView
from projeto_dvd.metadata.details import TitleInfo, generic_episode_name
from projeto_dvd.metadata.filename import Guess, guess
from projeto_dvd.planner.disc_plan import UND, DiscChoices, Kind
from projeto_dvd.planner.dvd_plan import SubtitleOption, subtitle_options
from projeto_dvd.planner.languages import dvd_language, language_name
from projeto_dvd.planner.profiles import PROFILES

MAX_TITLES = 60  # each title costs 2 of the 128 commands of the VMGM dispatcher
MAX_LANGUAGES = 4  # each language page fits in large type
_COMMENTARY = re.compile(r"coment|comment", re.IGNORECASE)


@dataclass(frozen=True)
class DiscTitle:
    path: str  # relative to MEDIA_DIR
    video: VideoFile
    summary: Summary
    options: tuple[SubtitleOption, ...]
    info: TitleInfo | None  # the confirmed TMDB match
    guess: Guess


def disc_titles(
    view: FolderView, infos: Mapping[str, TitleInfo], max_year: int
) -> tuple[DiscTitle, ...]:
    """The scanned videos of the folder; the ones that cannot go on a disc block it elsewhere."""
    return tuple(
        DiscTitle(
            path=file.video.path,
            video=file.video,
            summary=file.summary,
            options=tuple(subtitle_options(file.summary, file.video.subtitles)),
            info=infos.get(file.video.path),
            guess=guess(file.video.path.split("/", 1)[1], view.name, max_year),
        )
        for file in view.files
        if file.summary is not None
    )


def menu_name(title: DiscTitle) -> str:
    info, found = title.info, title.guess
    if info is not None and info.kind == "episode":
        return info.title if generic_episode_name(info.title) else f"{info.episode}. {info.title}"
    if info is not None:
        return info.title
    if found.kind == "episode" and found.episode is not None:
        return f"Episódio {found.episode}"
    return found.title or PurePosixPath(title.path).stem


def disc_name(titles: Sequence[DiscTitle], folder: str) -> tuple[str, str | None]:
    infos = [t.info for t in titles]
    if infos and all(i is not None for i in infos):
        confirmed = [i for i in infos if i is not None]
        shows = {i.show for i in confirmed if i.kind == "episode"}
        if len(shows) == 1 and all(i.kind == "episode" for i in confirmed):
            seasons = {i.season for i in confirmed}
            secondary = f"Temporada {seasons.pop()}" if len(seasons) == 1 else None
            return str(shows.pop()), secondary
        if len(confirmed) == 1 and confirmed[0].kind == "movie":
            return confirmed[0].title, None
        collections = {i.collection for i in confirmed}
        if all(i.kind == "movie" for i in confirmed) and len(collections) == 1:
            collection = collections.pop()
            if collection:
                return collection, None
    return folder, None


def strip_prefix(name: str, disc: str) -> str:
    """'O Senhor dos Anéis: A Sociedade do Anel' as 'A Sociedade do Anel' on that disc."""
    for separator in (": ", " - ", " "):
        prefix = disc + separator
        if name.startswith(prefix) and name[len(prefix) :].strip():
            return name[len(prefix) :].strip()
    return name


def suggest_kind(titles: Sequence[DiscTitle]) -> Kind:
    return "series" if titles and all(_episode_key(t) for t in titles) else "movies"


def suggest_order(titles: Sequence[DiscTitle]) -> tuple[str, ...]:
    if suggest_kind(titles) == "series":
        ordered = sorted(titles, key=lambda t: (_episode_key(t), natural_key(t.path)))
    else:
        ordered = sorted(titles, key=lambda t: (_year(t), natural_key(t.path)))
    return tuple(t.path for t in ordered)


def track_language(tag: str | None) -> str:
    return dvd_language(tag) or UND


def audio_languages(titles: Sequence[DiscTitle]) -> tuple[str, ...]:
    found = (track_language(track.language) for t in titles for track in t.summary.audio)
    return tuple(dict.fromkeys(found))


def subtitle_languages(titles: Sequence[DiscTitle]) -> tuple[str, ...]:
    found = (o.language or UND for t in titles for o in t.options if o.supported)
    return tuple(dict.fromkeys(found))


def best_audio(title: DiscTitle, language: str) -> AudioTrack | None:
    tracks = [t for t in title.summary.audio if track_language(t.language) == language]
    if not tracks:
        return None
    return min(
        tracks,
        key=lambda t: (bool(_COMMENTARY.search(t.title or "")), -(t.channel_count or 0), t.index),
    )


def best_subtitle(title: DiscTitle, language: str) -> SubtitleOption | None:
    """The full subtitle; a forced-only language counts as missing (it subtitles little)."""
    options = [o for o in title.options if o.supported and (o.language or UND) == language]
    return next((o for o in options if not o.forced), None)


def fallback_audio(title: DiscTitle, choices: DiscChoices) -> str:
    """The language a title plays when it lacks the chosen one: its first disc language."""
    return next(
        (lang for lang in choices.audio if best_audio(title, lang) is not None),
        track_language(title.summary.audio[0].language) if title.summary.audio else UND,
    )


def track_warnings(titles: Sequence[DiscTitle], choices: DiscChoices) -> tuple[str, ...]:
    by_path = {t.path: t for t in titles}
    warnings: list[str] = []
    for path in choices.order:
        title = by_path.get(path)
        if title is None:
            continue
        name = menu_name(title)
        fallback = language_name(fallback_audio(title, choices))
        for language in choices.audio:
            if best_audio(title, language) is None:
                warnings.append(
                    f"{name} não tem áudio em {language_name(language)}: toca em {fallback}."
                )
        for language in choices.subtitles:
            if best_subtitle(title, language) is not None:
                continue
            forced = any(
                o.supported and o.forced and (o.language or UND) == language for o in title.options
            )
            if forced:
                warnings.append(
                    f"{name} só tem a legenda forçada em {language_name(language)}: fica sem "
                    "legenda."
                )
            else:
                warnings.append(f"{name} não tem legenda em {language_name(language)}.")
    return tuple(warnings)


def suggest_choices(
    titles: Sequence[DiscTitle], folder: str, profile_for: Callable[[DiscChoices], str]
) -> DiscChoices:
    order = suggest_order(titles)
    by_path = {t.path: t for t in titles}
    first = by_path[order[0]]
    available = audio_languages(titles)
    original = track_language(first.summary.audio[0].language) if first.summary.audio else UND
    tmdb = next((t.info.original_language for t in titles if t.info), None)
    if tmdb and dvd_language(tmdb) in available:
        original = str(dvd_language(tmdb))
    audio = tuple(dict.fromkeys(lang for lang in ("pt", original) if lang in available))
    subtitles = ("pt",) if "pt" in subtitle_languages(titles) else ()
    subtitle_on = "pt" if subtitles and audio[:1] != ("pt",) else None
    every = all(len(t.summary.chapters) >= 2 for t in titles)
    draft = DiscChoices(
        kind=suggest_kind(titles), order=order, profile="dvd5",
        audio=(audio or available[:1])[:MAX_LANGUAGES], subtitles=subtitles,
        subtitle_on=subtitle_on, chapters="file" if every else "every", minutes=5,
    )  # fmt: skip
    return draft.model_copy(update={"profile": profile_for(draft)})


def reconcile(
    saved: str | None,
    titles: Sequence[DiscTitle],
    suggestion: DiscChoices,
    backdrops: Sequence[str],
) -> DiscChoices:
    """The saved choices fitted to the folder as it is now. Never raises."""
    if saved is None:
        return suggestion
    try:
        choices = DiscChoices.model_validate_json(saved)
    except ValidationError:
        return suggestion
    paths = {t.path for t in titles}
    kept = [p for p in choices.order if p in paths]
    order = (*kept, *(p for p in suggestion.order if p not in kept))
    audio = tuple(lang for lang in choices.audio if lang in audio_languages(titles))
    subtitles = tuple(lang for lang in choices.subtitles if lang in subtitle_languages(titles))
    theme = choices.theme
    if theme.backdrop not in backdrops:
        theme = theme.model_copy(update={"backdrop": None})
    return choices.model_copy(
        update={
            "order": order,
            "profile": choices.profile if choices.profile in PROFILES else suggestion.profile,
            "audio": audio or suggestion.audio,
            "subtitles": subtitles,
            "subtitle_on": choices.subtitle_on if choices.subtitle_on in subtitles else None,
            "theme": theme,
        }
    )


def choice_errors(choices: DiscChoices, titles: Sequence[DiscTitle]) -> list[str]:
    errors = []
    if len(titles) > MAX_TITLES:
        errors.append(
            f"O disco aceita até {MAX_TITLES} títulos nesta versão; esta pasta tem {len(titles)}."
        )
    if not choices.audio:
        errors.append("Escolha ao menos um idioma de áudio.")
    elif len(choices.audio) > MAX_LANGUAGES:
        errors.append(f"Escolha até {MAX_LANGUAGES} idiomas de áudio.")
    if len(choices.subtitles) > MAX_LANGUAGES:
        errors.append(f"Escolha até {MAX_LANGUAGES} idiomas de legenda.")
    return errors


def _episode_key(title: DiscTitle) -> tuple[int, int] | None:
    info, found = title.info, title.guess
    if info is not None and info.season is not None and info.episode is not None:
        return info.season, info.episode
    if info is None and found.season is not None and found.episode is not None:
        return found.season, found.episode
    return None


def _year(title: DiscTitle) -> int:
    return title.info.year if title.info and title.info.year else 9999
