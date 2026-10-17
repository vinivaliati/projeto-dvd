"""Capacity calculator: video bitrate, estimated size and quality of a profile."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from projeto_dvd.planner.profiles import DiscProfile

PACK_OVERHEAD_KBPS = 300  # pack, PES and nav headers inside the 10.08 Mbps mux
SUBTITLE_PEAK_KBPS = 40
SUBTITLE_AVERAGE_KBPS = 10
# A target equal to maxrate turns the 2-pass VBR into CBR (no room for the hard scenes).
VBR_HEADROOM = 0.95
# A still menu page: about a second of MPEG-2 plus the buttons (measured 90 KB to 1.2 MB).
MENU_PAGE_BYTES = 2 * 1024 * 1024
# Up to 20 pages cost the same, so changing the menu never changes the video bitrate (and the
# encode cache keeps working); about 0.5% of a DVD-9.
MENU_RESERVE_PAGES = 20


class Quality(StrEnum):
    GREAT = "Ótima"
    ACCEPTABLE = "Aceitável"
    LOW = "Baixa"
    DOES_NOT_FIT = "Não cabe"


@dataclass(frozen=True)
class TitleLoad:
    duration: float
    audio_kbps: tuple[int, ...]
    subtitles: int
    video_bytes: int | None = None  # the video of a DVD rip, copied as it is


@dataclass(frozen=True)
class Estimate:
    profile: DiscProfile
    video_kbps: int
    maxrate_kbps: int
    size_bytes: int
    quality: Quality


def maxrate_kbps(profile: DiscProfile, audio_kbps: Sequence[int], subtitles: int) -> int:
    room = (
        profile.mux_rate_kbps
        - sum(audio_kbps)
        - SUBTITLE_PEAK_KBPS * subtitles
        - PACK_OVERHEAD_KBPS
    )
    return min(profile.max_video_kbps, room)


def estimate(
    profile: DiscProfile, duration: float, audio_kbps: Sequence[int], subtitles: int
) -> Estimate:
    return estimate_disc(profile, [TitleLoad(duration, tuple(audio_kbps), subtitles)], 0)


def estimate_disc(profile: DiscProfile, titles: Sequence[TitleLoad], menu_pages: int) -> Estimate:
    """One video bitrate for every encoded title: the same quality from the first to the last.

    A copied video takes its own size; the encoded titles share what is left.
    """
    if sum(title.duration for title in titles) <= 0:
        raise ValueError("disc without duration")
    menus = menu_bytes(menu_pages)
    encoded = [title for title in titles if title.video_bytes is None]
    copied_kilobits = sum(
        (title.video_bytes or 0) * 8 / 1000 + title.duration * _other_kbps(title)
        for title in titles
        if title.video_bytes is not None
    )
    room_kilobits = (profile.usable_bytes - menus) * 8 / (1 + profile.mux_overhead) / 1000
    duration = sum(title.duration for title in encoded)
    if encoded:
        maxrate = min(maxrate_kbps(profile, t.audio_kbps, t.subtitles) for t in encoded)
        other_kilobits = sum(title.duration * _other_kbps(title) for title in encoded)
        free = room_kilobits - copied_kilobits - other_kilobits
        video = int(min(free / duration, VBR_HEADROOM * maxrate)) if duration else 0
    else:
        maxrate = video = 0
    kilobits = copied_kilobits + sum(t.duration * (video + _other_kbps(t)) for t in encoded)
    size = int(kilobits * 1000 * (1 + profile.mux_overhead) / 8) + profile.reserve_bytes + menus
    if encoded:
        quality = _quality(profile, video)
    else:  # only copies: the original quality, if it fits
        fits = size <= profile.usable_bytes + profile.reserve_bytes
        quality = Quality.GREAT if fits else Quality.DOES_NOT_FIT
    return Estimate(profile=profile, video_kbps=video, maxrate_kbps=maxrate, size_bytes=size,
                    quality=quality)  # fmt: skip


def menu_bytes(pages: int) -> int:
    """The space kept for the menus: a fixed reserve, or the pages when there are more."""
    return max(pages, MENU_RESERVE_PAGES) * MENU_PAGE_BYTES if pages else 0


def suggest_profile(estimates: Sequence[Estimate]) -> DiscProfile:
    """The first profile with great quality; the last one (the largest) otherwise."""
    for item in estimates:
        if item.quality == Quality.GREAT:
            return item.profile
    return estimates[-1].profile


def _other_kbps(title: TitleLoad) -> float:
    return sum(title.audio_kbps) + SUBTITLE_AVERAGE_KBPS * title.subtitles


def _quality(profile: DiscProfile, video_kbps: int) -> Quality:
    if video_kbps >= profile.good_kbps:
        return Quality.GREAT
    if video_kbps >= profile.acceptable_kbps:
        return Quality.ACCEPTABLE
    if video_kbps >= profile.min_kbps:
        return Quality.LOW
    return Quality.DOES_NOT_FIT
