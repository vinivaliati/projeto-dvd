"""Disc profiles as configuration. Adding a profile is adding an entry here."""

from dataclasses import dataclass
from typing import Literal

Medium = Literal["dvd", "bluray"]

MIB = 1024 * 1024
SECTOR = 2048


@dataclass(frozen=True)
class DiscProfile:
    key: str
    name: str
    description: str
    # Smallest sector count between the -R and +R media: the media is not bought yet.
    sectors: int
    margin: float = 0.97
    reserve_bytes: int = 4 * MIB  # IFO, BUP and the ISO file system
    mux_overhead: float = 0.03  # MPEG-PS packs and nav packs (measured 2.7%)
    good_kbps: int = 5000
    acceptable_kbps: int = 3500
    min_kbps: int = 1000
    # 9.0 Mbps, below the 9.8 of the spec: leaves room for VBV peaks inside the 10.08 mux.
    max_video_kbps: int = 9000
    mux_rate_kbps: int = 10080
    medium: Medium = "dvd"
    pack_overhead_kbps: int = 300  # pack, PES and nav headers inside the 10.08 Mbps mux
    subtitle_peak_kbps: int = 40  # a spumux subpicture stream

    @property
    def capacity_bytes(self) -> int:
        return self.sectors * SECTOR

    @property
    def usable_bytes(self) -> int:
        return int(self.margin * self.capacity_bytes) - self.reserve_bytes


DVD5 = DiscProfile(key="dvd5", name="DVD-5", description="camada única, 4,7 GB", sectors=2_295_104)
DVD9 = DiscProfile(key="dvd9", name="DVD-9", description="dupla camada, 8,5 GB", sectors=4_171_712)
BD25 = DiscProfile(
    key="bd25", name="BD-25", description="camada única, 25 GB", sectors=12_219_392,
    medium="bluray", reserve_bytes=64 * MIB, mux_overhead=0.06, good_kbps=15_000,
    acceptable_kbps=8_000, min_kbps=3_000, max_video_kbps=35_000, mux_rate_kbps=48_000,
    pack_overhead_kbps=2_717, subtitle_peak_kbps=500,
)  # fmt: skip
BD50 = DiscProfile(
    key="bd50", name="BD-50", description="dupla camada, 50 GB", sectors=24_438_784,
    medium="bluray", reserve_bytes=64 * MIB, mux_overhead=0.06, good_kbps=15_000,
    acceptable_kbps=8_000, min_kbps=3_000, max_video_kbps=35_000, mux_rate_kbps=48_000,
    pack_overhead_kbps=2_717, subtitle_peak_kbps=500,
)  # fmt: skip
PROFILES = {profile.key: profile for profile in (DVD5, DVD9, BD25, BD50)}


def medium_of(profile_key: str) -> Medium:
    return PROFILES[profile_key].medium
