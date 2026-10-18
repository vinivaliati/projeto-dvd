"""From the disc choices to the plan a job runs: tracks per title, menu pages, bitrate."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image

from projeto_dvd.library.probe import AudioTrack
from projeto_dvd.menus.pages import build_pages
from projeto_dvd.menus.theme import resolve_accent
from projeto_dvd.planner.bd_source import HeaderReport, bd_copy_reason
from projeto_dvd.planner.calculator import (
    Estimate,
    Quality,
    TitleLoad,
    estimate_disc,
    suggest_profile,
)
from projeto_dvd.planner.disc import (
    MAX_GOP_FIELDS,
    DiscTitle,
    bd_eligible,
    best_audio,
    best_subtitle,
    choice_errors,
    copy_reason,
    disc_name,
    is_rip,
    menu_name,
    strip_prefix,
    video_size,
)
from projeto_dvd.planner.disc_plan import Aspect, DiscChoices, DiscPlan, MenuPlan, TitlePlan
from projeto_dvd.planner.dvd_plan import (
    BD_COPY_AC3_KBPS,
    BD_PCM_BITS,
    MAX_CHAPTERS,
    AudioChoice,
    AudioOutput,
    SubtitleChoice,
    SubtitleOption,
    audio_output,
    bd_audio_output,
    bd_volume_label,
    iso_name,
    plan_chapters,
    volume_name,
)
from projeto_dvd.planner.languages import dvd_language, language_name
from projeto_dvd.planner.profiles import PROFILES, DiscProfile, Medium, medium_of
from projeto_dvd.planner.source import VideoMode, bd_frame, geometry

BD_MAX_CHAPTERS = 999
MAX_SHIFT = 0.032  # one AC-3 frame: a copied track later than this is converted on a Blu-ray


@dataclass(frozen=True)
class TitleSource:
    """A title ready to encode: the frame scan of DVD rips already ran."""

    title: DiscTitle
    mode: VideoMode
    top_field_first: bool
    gop_fields: int | None = None  # the longest GOP of a DVD rip's frame sample, in fields
    headers: HeaderReport | None = None  # Phase 6a: the SPS and slice sample of a Blu-ray copy
    gop_frames: int | None = None  # the longest GOP of that sample, in frames


def title_plan(source: TitleSource, choices: DiscChoices, name: str) -> TitlePlan:
    summary = source.title.summary
    video, duration = summary.video, summary.duration
    if video is None or duration is None:
        raise ValueError("source without video or duration")
    medium = medium_of(choices.profile)
    found = [best_audio(source.title, language, medium) for language in choices.audio]
    tracks = list({t.index: t for t in found if t is not None}.values()) or [summary.audio[0]]
    positions = {track.index: n for n, track in enumerate(tracks)}
    # A language the title lacks plays its first disc track (position 0).
    audio_map = tuple(positions[t.index] if t else 0 for t in found)
    options = [best_subtitle(source.title, language, medium) for language in choices.subtitles]
    chosen = list({o.key: o for o in options if o is not None}.values())
    keys = {option.key: n for n, option in enumerate(chosen)}
    directory = PurePosixPath(source.title.path).parent
    aspect: Aspect
    if medium == "bluray":
        copy = bd_copy_reason(source.title, choices, source.headers, source.gop_frames) is None
        frame = bd_frame(video) or (1920, 1080, False)
        aspect, width, height, scale = "16:9", frame[0], frame[1], frame[2] and not copy
        max_chapters = BD_MAX_CHAPTERS
    else:
        copy = (
            is_rip(source.title)
            and copy_reason(source.title, choices) is None
            and (source.gop_fields or 0) <= MAX_GOP_FIELDS
        )
        shape = geometry(video)
        aspect, width, height, scale = shape.aspect, shape.width, shape.height, shape.scale
        max_chapters = MAX_CHAPTERS
    if copy and medium == "dvd":  # the cells of the original disc: a chapter mid-GOP shows blocks
        file = summary.chapters
        starts = plan_chapters(file, duration, "file", 1).starts if len(file) >= 2 else (0.0,)
    else:
        starts = plan_chapters(summary.chapters, duration, choices.chapters, choices.minutes,
                               max_chapters).starts  # fmt: skip
    return TitlePlan(
        path=source.title.path, video_index=video.index, size=source.title.video.size,
        mtime_ns=source.title.video.mtime_ns, duration=duration, mode=source.mode,
        top_field_first=source.top_field_first, aspect=aspect, width=width, height=height,
        scale=scale, hd_color=video.height > 576,
        audio=tuple(_audio(t, t.start_time - video.start_time, medium) for t in tracks),
        subtitles=tuple(_subtitle(option, directory) for option in chosen),
        chapters=starts,
        audio_map=audio_map,
        subtitle_map=tuple(keys[o.key] if o else None for o in options),
        menu_name=name, copy_video=copy, video_bytes=video_size(source.title) if copy else None,
    )  # fmt: skip


def _audio(track: AudioTrack, offset: float, medium: Medium) -> AudioChoice:
    """A Blu-ray cannot shift a copied AC-3 or DTS by less than a frame: a late track is
    converted (with the delay applied); LPCM keeps its copy, padded with silence."""
    if medium == "dvd":
        out = audio_output(track)
    else:
        out = bd_audio_output(track)
        if out.action == "copy" and track.codec not in BD_PCM_BITS and abs(offset) > MAX_SHIFT:
            out = AudioOutput("ac3", min(out.channels, 6), BD_COPY_AC3_KBPS,
                              6 if out.channels > 6 else None)  # fmt: skip
    return AudioChoice(
        index=track.index, language=dvd_language(track.language), action=out.action,
        channels=out.channels, kbps=out.kbps, downmix=out.downmix, offset=round(offset, 6),
        codec=track.codec,
    )  # fmt: skip


def menu_plan(
    choices: DiscChoices,
    titles: Sequence[DiscTitle],
    folder: str,
    backdrop: Path | None,
    accent_image: Image.Image | None,
) -> MenuPlan:
    by_path = {t.path: t for t in titles}
    ordered = [by_path[path] for path in choices.order if path in by_path]
    name, secondary = disc_name(ordered, folder)
    aspects = {geometry(t.summary.video).aspect for t in ordered if t.summary.video}
    original = next((dvd_language(t.info.original_language) for t in ordered if t.info), None)
    audio_labels = [
        language_name(lang) + (" (original)" if lang == original else "") for lang in choices.audio
    ]
    pages = build_pages(
        choices.kind, [strip_prefix(menu_name(t), name) for t in ordered], name, secondary,
        audio_labels, [language_name(lang) for lang in choices.subtitles],
    )  # fmt: skip
    return MenuPlan(
        aspect="4:3" if aspects == {"4:3"} else "16:9",
        backdrop=str(backdrop) if backdrop else None,
        accent=resolve_accent(choices.theme.accent, accent_image),
        side=choices.theme.side,
        pages=pages,
    )


def disc_estimate(profile: DiscProfile, plans: Sequence[TitlePlan], menu_pages: int) -> Estimate:
    loads = [
        TitleLoad(p.duration, tuple(a.kbps for a in p.audio), len(p.subtitles),
                  p.video_bytes if p.copy_video else None)
        for p in plans
    ]  # fmt: skip
    return estimate_disc(profile, loads, menu_pages)


def build_disc_plan(
    folder: str,
    sources: Sequence[TitleSource],
    choices: DiscChoices,
    menu: MenuPlan | None,  # None on a Blu-ray (no menu in Phase 6a)
    confirm_low: bool,
    replace_iso: bool,
) -> DiscPlan:
    by_path = {s.title.path: s for s in sources}
    plans = tuple(
        title_plan(by_path[path], choices, menu_name(by_path[path].title))
        for path in choices.order
        if path in by_path
    )
    profile = PROFILES[choices.profile]
    result = disc_estimate(profile, plans, len(menu.pages) if menu else 0)
    on = choices.subtitle_on
    blu_ray = profile.medium == "bluray"
    return DiscPlan(
        folder=folder, profile=profile.key, video_kbps=result.video_kbps,
        maxrate_kbps=result.maxrate_kbps, estimated_bytes=result.size_bytes,
        confirmed_low=confirm_low, replace_existing=replace_iso,
        volume=bd_volume_label(folder) if blu_ray else volume_name(folder),
        iso_name=iso_name(folder, profile.medium),
        subtitle_on=choices.subtitles.index(on) + 1 if on in choices.subtitles else 0,
        titles=plans, menu=menu,
    )  # fmt: skip


def disc_errors(
    choices: DiscChoices, titles: Sequence[DiscTitle], estimate: Estimate, confirm_low: bool
) -> list[str]:
    errors = choice_errors(choices, titles)
    if errors:
        return errors
    if estimate.quality == Quality.DOES_NOT_FIT:
        return [f"O disco não cabe no {estimate.profile.name}."]
    if estimate.quality == Quality.LOW and not confirm_low:
        return ["Confirme que quer gerar com qualidade baixa."]
    return []


def _subtitle(option: SubtitleOption, directory: PurePosixPath) -> SubtitleChoice:
    return SubtitleChoice(
        key=option.key,
        stream_index=int(option.key[1:]) if option.key.startswith("s") else None,
        file=str(directory / option.key[2:]) if option.key.startswith("f:") else None,
        language=option.language,
        codec="pgs" if option.kind == "image" else "text",  # the only image a disc takes
    )


def disc_estimates(
    choices: DiscChoices, titles: Sequence[DiscTitle], folder: str
) -> list[Estimate]:
    """Every profile for the whole disc, menus included; the frame scan does not matter here.

    The Blu-ray profiles appear only when the folder can become one.
    """
    by_path = {t.path: t for t in titles}
    estimates: list[Estimate] = []
    for medium in ("dvd", "bluray"):
        if medium == "bluray" and bd_eligible(titles) is not None:
            continue
        profiles = [p for p in PROFILES.values() if p.medium == medium]
        draft = choices.model_copy(update={"profile": profiles[0].key})
        plans = [
            title_plan(TitleSource(by_path[path], VideoMode.FILM, True), draft, "")
            for path in choices.order
            if path in by_path
        ]
        pages = len(menu_plan(draft, titles, folder, None, None).pages) if medium == "dvd" else 0
        estimates += [disc_estimate(profile, plans, pages) for profile in profiles]
    return estimates


def profile_for(titles: Sequence[DiscTitle], folder: str) -> Callable[[DiscChoices], str]:
    """The suggested profile of a draft: the first one with great quality (a Blu-ray one for
    an HD video that can become a Blu-ray)."""
    hd = hd_disc(titles)
    return lambda draft: suggest_profile(disc_estimates(draft, titles, folder), hd).key


def hd_disc(titles: Sequence[DiscTitle]) -> bool:
    """An HD video that can become a Blu-ray: the suggestion looks at the Blu-ray profiles."""
    return bd_eligible(titles) is None and any(
        t.summary.video is not None and t.summary.video.height > 576 for t in titles
    )
