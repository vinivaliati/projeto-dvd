import pytest

from projeto_dvd.planner.calculator import (
    MENU_PAGE_BYTES,
    MENU_RESERVE_PAGES,
    Quality,
    TitleLoad,
    estimate,
    estimate_disc,
    maxrate_kbps,
    menu_bytes,
    suggest_profile,
)
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


@pytest.mark.parametrize("duration", [1800.0, 7200.0, 20000.0])
def test_one_title_without_menus_is_the_single_title_estimate(duration: float) -> None:
    single = estimate(DVD9, duration, [448, 192], 1)

    disc = estimate_disc(DVD9, [TitleLoad(duration, (448, 192), 1)], menu_pages=0)

    assert disc == single


def test_titles_share_one_video_bitrate_capped_by_the_smallest_maxrate() -> None:
    loads = [TitleLoad(300.0, (448,) * 8, 0), TitleLoad(300.0, (192,), 0)]

    result = estimate_disc(DVD9, loads, menu_pages=0)

    assert result.maxrate_kbps == maxrate_kbps(DVD9, [448] * 8, 0)
    assert result.video_kbps == int(0.95 * result.maxrate_kbps)


def test_menu_pages_take_space_from_the_video() -> None:
    loads = [TitleLoad(5400.0, (448,), 0), TitleLoad(5400.0, (448,), 0)]
    without = estimate_disc(DVD9, loads, menu_pages=0)

    with_menus = estimate_disc(DVD9, loads, menu_pages=10)

    assert with_menus.video_kbps < without.video_kbps
    assert with_menus.size_bytes <= DVD9.usable_bytes + DVD9.reserve_bytes
    assert with_menus.size_bytes - without.size_bytes < 10 * MENU_PAGE_BYTES


def test_menu_bytes_count_in_the_size_when_capped() -> None:
    loads = [TitleLoad(60.0, (192,), 0)]

    assert (
        estimate_disc(DVD5, loads, 3).size_bytes - estimate_disc(DVD5, loads, 0).size_bytes
        == MENU_RESERVE_PAGES * MENU_PAGE_BYTES
    )


def test_menu_space_is_a_fixed_reserve_up_to_twenty_pages() -> None:
    assert menu_bytes(0) == 0
    assert menu_bytes(3) == menu_bytes(20) == 20 * MENU_PAGE_BYTES
    assert menu_bytes(25) == 25 * MENU_PAGE_BYTES


def test_changing_the_menu_pages_keeps_the_video_bitrate() -> None:
    loads = [TitleLoad(5400.0, (448,), 0), TitleLoad(5400.0, (448,), 0)]

    assert estimate_disc(DVD9, loads, 3).video_kbps == estimate_disc(DVD9, loads, 12).video_kbps


def test_a_disc_without_duration_is_an_error() -> None:
    with pytest.raises(ValueError, match="disc without duration"):
        estimate_disc(DVD9, [TitleLoad(0.0, (192,), 0)], menu_pages=1)


def test_copied_video_takes_its_own_size_and_the_rest_shares_what_is_left() -> None:
    encoded = TitleLoad(5400.0, (448,), 0)
    copied = TitleLoad(5400.0, (448,), 0, video_bytes=3 * 10**9)

    alone = estimate_disc(DVD9, [encoded], 1)
    mixed = estimate_disc(DVD9, [encoded, copied], 1)

    assert mixed.video_kbps < alone.video_kbps
    assert mixed.size_bytes <= DVD9.usable_bytes + DVD9.reserve_bytes
    room = (DVD9.usable_bytes - menu_bytes(1)) * 8 / 1.03 / 1000
    copied_kilobits = 3 * 10**9 * 8 / 1000 + 5400 * 448
    assert mixed.video_kbps == int((room - copied_kilobits - 5400 * 448) / 5400)


def test_the_maxrate_comes_only_from_the_encoded_titles() -> None:
    encoded = TitleLoad(600.0, (192,), 0)
    copied = TitleLoad(600.0, (448,) * 8, 0, video_bytes=10**8)

    assert estimate_disc(DVD9, [encoded, copied], 0).maxrate_kbps == maxrate_kbps(DVD9, [192], 0)


def test_a_disc_of_copies_only_is_great_when_it_fits() -> None:
    fits = estimate_disc(DVD9, [TitleLoad(7200.0, (448,), 0, video_bytes=6 * 10**9)], 1)
    too_big = estimate_disc(DVD5, [TitleLoad(7200.0, (448,), 0, video_bytes=6 * 10**9)], 1)

    assert (fits.quality, fits.video_kbps, fits.maxrate_kbps) == (Quality.GREAT, 0, 0)
    assert too_big.quality == Quality.DOES_NOT_FIT
    expected = (6 * 10**9 * 8 / 1000 + 7200 * 448) * 1000 * 1.03 / 8
    assert fits.size_bytes == int(expected) + DVD9.reserve_bytes + menu_bytes(1)
