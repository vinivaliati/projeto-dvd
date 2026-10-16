"""Disc profiles as configuration. Adding a profile is adding an entry here."""

from dataclasses import dataclass

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

    @property
    def capacity_bytes(self) -> int:
        return self.sectors * SECTOR

    @property
    def usable_bytes(self) -> int:
        return int(self.margin * self.capacity_bytes) - self.reserve_bytes


DVD5 = DiscProfile(key="dvd5", name="DVD-5", description="camada única, 4,7 GB", sectors=2_295_104)
DVD9 = DiscProfile(key="dvd9", name="DVD-9", description="dupla camada, 8,5 GB", sectors=4_171_712)
PROFILES = {profile.key: profile for profile in (DVD5, DVD9)}
