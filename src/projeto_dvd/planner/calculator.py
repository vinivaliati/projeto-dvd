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


class Quality(StrEnum):
    GREAT = "Ótima"
    ACCEPTABLE = "Aceitável"
    LOW = "Baixa"
    DOES_NOT_FIT = "Não cabe"


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
    other_kbps = sum(audio_kbps) + SUBTITLE_AVERAGE_KBPS * subtitles
    total_kbps = profile.usable_bytes * 8 / (1 + profile.mux_overhead) / duration / 1000
    maxrate = maxrate_kbps(profile, audio_kbps, subtitles)
    video = int(min(total_kbps - other_kbps, VBR_HEADROOM * maxrate))
    size = (video + other_kbps) * 1000 * duration * (1 + profile.mux_overhead) / 8
    return Estimate(
        profile=profile,
        video_kbps=video,
        maxrate_kbps=maxrate,
        size_bytes=int(size) + profile.reserve_bytes,
        quality=_quality(profile, video),
    )


def suggest_profile(estimates: Sequence[Estimate]) -> DiscProfile:
    """The first profile with great quality; the last one (the largest) otherwise."""
    for item in estimates:
        if item.quality == Quality.GREAT:
            return item.profile
    return estimates[-1].profile


def _quality(profile: DiscProfile, video_kbps: int) -> Quality:
    if video_kbps >= profile.good_kbps:
        return Quality.GREAT
    if video_kbps >= profile.acceptable_kbps:
        return Quality.ACCEPTABLE
    if video_kbps >= profile.min_kbps:
        return Quality.LOW
    return Quality.DOES_NOT_FIT
