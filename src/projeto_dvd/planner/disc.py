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
from projeto_dvd.planner.dvd_plan import (
    SubtitleOption,
    audio_output,
    bd_audio_output,
    subtitle_options,
)
from projeto_dvd.planner.languages import dvd_language, language_name
from projeto_dvd.planner.profiles import PROFILES, Medium
from projeto_dvd.planner.source import check_video, geometry

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


BD_ONE_TITLE = "Blu-ray: um título por disco nesta fase."


def bd_eligible(titles: Sequence[DiscTitle]) -> str | None:
    """Why the folder cannot become a Blu-ray yet; None when it can (one HD film video)."""
    if len(titles) != 1:
        return BD_ONE_TITLE
    reasons = check_video(titles[0].summary, "bluray").reasons
    return f"Blu-ray: {reasons[0]}" if reasons else None


def track_language(tag: str | None) -> str:
    return dvd_language(tag) or UND


def audio_languages(titles: Sequence[DiscTitle]) -> tuple[str, ...]:
    found = (track_language(track.language) for t in titles for track in t.summary.audio)
    return tuple(dict.fromkeys(found))


def subtitle_languages(titles: Sequence[DiscTitle], medium: Medium = "dvd") -> tuple[str, ...]:
    found = (o.language or UND for t in titles for o in t.options if _usable(o, medium))
    return tuple(dict.fromkeys(found))


def best_audio(title: DiscTitle, language: str, medium: Medium = "dvd") -> AudioTrack | None:
    """The main track of a language; a Blu-ray first takes one it can copy (the AC-3 core
    MakeMKV keeps next to a TrueHD track, a DTS-HD MA)."""
    tracks = [t for t in title.summary.audio if track_language(t.language) == language]
    if not tracks:
        return None
    return min(
        tracks,
        key=lambda t: (bool(_COMMENTARY.search(t.title or "")),
                       medium == "bluray" and bd_audio_output(t).action != "copy",
                       -(t.channel_count or 0), t.index),
    )  # fmt: skip


def best_subtitle(title: DiscTitle, language: str, medium: Medium = "dvd") -> SubtitleOption | None:
    """The full subtitle; a forced-only language counts as missing (it subtitles little)."""
    options = [o for o in title.options if _usable(o, medium) and (o.language or UND) == language]
    return next((o for o in options if not o.forced), None)


def _medium(choices: DiscChoices) -> Medium:
    return PROFILES[choices.profile].medium if choices.profile in PROFILES else "dvd"


def _usable(option: SubtitleOption, medium: Medium) -> bool:
    return option.bd_supported if medium == "bluray" else option.supported


def fallback_audio(title: DiscTitle, choices: DiscChoices) -> str:
    """The language a title plays when it lacks the chosen one: its first disc language."""
    return next(
        (lang for lang in choices.audio if best_audio(title, lang) is not None),
        track_language(title.summary.audio[0].language) if title.summary.audio else UND,
    )


def missing_languages(title: DiscTitle, choices: DiscChoices) -> list[str]:
    """Short badges for the title list: "sem áudio Inglês", "sem legenda Inglês"."""
    audio = [f"sem áudio {language_name(lang)}" for lang in choices.audio
             if best_audio(title, lang) is None]  # fmt: skip
    medium = _medium(choices)
    subtitles = [f"sem legenda {language_name(lang)}" for lang in choices.subtitles
                 if best_subtitle(title, lang, medium) is None]  # fmt: skip
    return audio + subtitles


DVD_PEAK = 9_800_000  # bit/s, the DVD video ceiling written in the sequence header
DVD_BUFFER = 1_835_008  # bits, the MP@ML VBV buffer
SUBTITLE_PEAK_KBPS = 40
MAX_GOP_FIELDS = 36  # the NTSC limit, counted in displayed fields (pulldown repeats fields)
NOT_ENOUGH_ROOM = "as faixas escolhidas pedem mais espaço que o disco original"
UNKNOWN_SIZE = "tamanho do vídeo desconhecido"
REENCODE_CHECKED = "Recodificar os rips está marcado"


def is_rip(title: DiscTitle) -> bool:
    """MPEG-2 720x480 as a DVD carries it, with the sequence header of a DVD."""
    video = title.summary.video
    if video is None or video.codec != "mpeg2video" or (video.width, video.height) != (720, 480):
        return False
    if geometry(video).scale or video.dvd_header is None:
        return False
    peak, buffer = video.dvd_header
    return peak <= DVD_PEAK and buffer <= DVD_BUFFER


def video_size(title: DiscTitle) -> int | None:
    """The bytes of the video stream: the MakeMKV tag, or the file minus its audio."""
    video = title.summary.video
    if video is None:
        return None
    if video.stream_bytes and video.stream_bytes < title.video.size:
        return video.stream_bytes
    duration = title.summary.duration or 0.0
    if any(track.bit_rate is None for track in title.summary.audio):
        return None
    estimate = (
        title.video.size - sum(track.bit_rate or 0 for track in title.summary.audio) * duration / 8
    )
    return int(estimate) if estimate > 0 else None


def copy_reason(title: DiscTitle, choices: DiscChoices) -> str | None:
    """Why a DVD rip is encoded again; None when its video is copied as it is.

    The original disc already fitted the video in the 10.08 Mbps mux with its own audio and
    subtitles; the copy keeps to that budget.
    """
    if choices.reencode_rips:
        return REENCODE_CHECKED
    found = [best_audio(title, language) for language in choices.audio]
    tracks = {t.index: t for t in found if t is not None} or (
        {title.summary.audio[0].index: title.summary.audio[0]} if title.summary.audio else {}
    )
    subtitles = {o.key for o in (best_subtitle(title, lang) for lang in choices.subtitles) if o}
    needed = sum(audio_output(t).kbps for t in tracks.values()) + SUBTITLE_PEAK_KBPS * len(
        subtitles
    )
    original = sum(
        (t.bit_rate or 0) // 1000 for t in title.summary.audio
    ) + SUBTITLE_PEAK_KBPS * sum(1 for s in title.summary.subtitles if s.codec == "dvd_subtitle")
    if needed > original:
        return NOT_ENOUGH_ROOM
    if video_size(title) is None:
        return UNKNOWN_SIZE
    return None


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
            if best_subtitle(title, language, _medium(choices)) is not None:
                continue
            forced = any(
                _usable(o, _medium(choices)) and o.forced and (o.language or UND) == language
                for o in title.options
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
    profile = choices.profile if choices.profile in PROFILES else suggestion.profile
    if PROFILES[profile].medium == "bluray" and bd_eligible(titles) is not None:
        profile = suggestion.profile
    medium = PROFILES[profile].medium
    audio = tuple(lang for lang in choices.audio if lang in audio_languages(titles))
    found = subtitle_languages(titles, medium)
    subtitles = tuple(lang for lang in choices.subtitles if lang in found)
    theme = choices.theme
    if theme.backdrop not in backdrops:
        theme = theme.model_copy(update={"backdrop": None})
    return choices.model_copy(
        update={
            "order": order,
            "profile": profile,
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
