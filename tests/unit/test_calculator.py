import pytest

from projeto_dvd.planner.calculator import Quality, estimate, maxrate_kbps, suggest_profile
from projeto_dvd.planner.profiles import DVD5, DVD9, PROFILES, DiscProfile

TWO_HOURS = 7200.0


def test_profiles_use_the_smallest_sector_count() -> None:
    assert DVD5.capacity_bytes == 4_700_372_992
    assert DVD9.capacity_bytes == 8_543_666_176
    assert list(PROFILES) == ["dvd5", "dvd9"]


def test_usable_bytes_is_97_percent_minus_4_mib() -> None:
    assert DVD5.usable_bytes == int(0.97 * 4_700_372_992) - 4 * 1024 * 1024


def test_reference_example_two_hour_movie() -> None:
    dvd5 = estimate(DVD5, TWO_HOURS, [448], 0)
    dvd9 = estimate(DVD9, TWO_HOURS, [448], 0)

    assert dvd5.video_kbps / 1000 == pytest.approx(4.47, abs=0.01)
    assert dvd5.quality == Quality.ACCEPTABLE
    assert dvd9.video_kbps / 1000 == pytest.approx(8.49, abs=0.01)
    assert dvd9.quality == Quality.GREAT


def test_maxrate_leaves_room_for_audio_and_subtitles() -> None:
    assert maxrate_kbps(DVD9, [448], 0) == 9000
    assert maxrate_kbps(DVD9, [448] * 3, 2) == 10080 - 1344 - 80 - 300


def test_short_movie_is_capped_at_maxrate() -> None:
    result = estimate(DVD9, 1800.0, [448], 0)

    # 95% of the ceiling: b:v equal to maxrate turns the 2-pass VBR into CBR.
    assert result.video_kbps == 8550
    assert result.maxrate_kbps == 9000
    assert result.quality == Quality.GREAT


@pytest.mark.parametrize(
    ("kbps", "quality"),
    [(5000, Quality.GREAT), (4999, Quality.ACCEPTABLE), (3500, Quality.ACCEPTABLE),
     (3499, Quality.LOW), (1000, Quality.LOW), (999, Quality.DOES_NOT_FIT)],
)  # fmt: skip
def test_quality_bands(kbps: int, quality: Quality) -> None:
    # Find the duration that yields this bitrate on DVD-5 with no audio.
    duration = DVD5.usable_bytes * 8 / 1.03 / (kbps * 1000 + 0.5)

    assert estimate(DVD5, duration, [], 0).quality == quality


def test_estimated_size_fits_the_margin_when_not_capped() -> None:
    result = estimate(DVD5, TWO_HOURS, [448, 192], 2)

    assert result.size_bytes <= int(DVD5.margin * DVD5.capacity_bytes)


def test_suggests_the_first_great_profile() -> None:
    short = [estimate(p, 5400.0, [448], 0) for p in PROFILES.values()]
    long = [estimate(p, TWO_HOURS, [448], 0) for p in PROFILES.values()]
    huge = [estimate(p, 9 * 3600.0, [448], 0) for p in PROFILES.values()]

    assert suggest_profile(short) == DVD5
    assert suggest_profile(long) == DVD9
    assert suggest_profile(huge) == DVD9


def test_profile_is_configuration() -> None:
    tiny = DiscProfile(key="t", name="T", description="teste", sectors=5000)

    assert tiny.capacity_bytes == 5000 * 2048
