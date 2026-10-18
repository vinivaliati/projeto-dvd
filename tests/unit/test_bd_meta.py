from pathlib import Path

import pytest

from projeto_dvd.authoring.bluray.meta import (
    BdInputs,
    bd_meta,
    chapters_text,
    iso_639_2,
    tsmuxer_command,
    tsmuxer_problem,
    tsmuxer_progress,
)
from projeto_dvd.planner.dvd_plan import AudioChoice, SubtitleChoice
from tests.plans import make_disc_plan, make_title_plan

J = Path("/work/jobs/7")


def track(index: int, language: str, codec: str, action: str = "copy") -> AudioChoice:
    return AudioChoice(index=index, language=language, action=action, channels=6,  # type: ignore[arg-type]
                       kbps=640, downmix=None, offset=0.0, codec=codec)  # fmt: skip


def subtitle(key: str, language: str, codec: str) -> SubtitleChoice:
    return SubtitleChoice(key=key, stream_index=int(key[1:]), file=None, language=language,
                          codec=codec)  # type: ignore[arg-type]  # fmt: skip


def test_a_remux_with_lossless_audio_and_pgs() -> None:
    title = make_title_plan(width=1920, height=1080, chapters=(0.0, 300.0, 600.5),
                            audio=(track(1, "pt", "ac3"), track(2, "en", "dts")),
                            subtitles=(subtitle("s3", "pt", "pgs"),),
                            subtitle_map=(0,))  # fmt: skip
    plan = make_disc_plan(profile="bd25", volume="O Senhor dos Aneis", titles=(title,),
                          menu=None, subtitle_on=1)  # fmt: skip
    inputs = BdInputs(J / "video.h264", (J / "a1.ac3", J / "a2.dts"), (J / "s1.sup",))

    assert bd_meta(plan, inputs) == (
        'MUXOPT --blu-ray --vbr --label="O Senhor dos Aneis" '
        "--custom-chapters=00:00:00.000;00:05:00.000;00:10:00.500\n"
        'V_MPEG4/ISO/AVC, "/work/jobs/7/video.h264", fps=23.976\n'
        'A_AC3, "/work/jobs/7/a1.ac3", lang=por, default\n'
        'A_DTS, "/work/jobs/7/a2.dts", lang=eng\n'
        'S_HDMV/PGS, "/work/jobs/7/s1.sup", lang=por, default=all\n'
    )


def test_720p_with_lpcm_and_a_text_subtitle_off() -> None:
    title = make_title_plan(width=1280, height=720, chapters=(0.0,),
                            audio=(track(1, "en", "pcm_s24le"),),
                            subtitles=(subtitle("s2", "pt", "text"),),
                            subtitle_map=(0,))  # fmt: skip
    plan = make_disc_plan(profile="bd25", volume="F", titles=(title,), menu=None, subtitle_on=0)
    inputs = BdInputs(J / "video.h264", (J / "a1.mka",), (J / "s1.srt",))

    assert bd_meta(plan, inputs).splitlines()[2:] == [
        'A_LPCM, "/work/jobs/7/a1.mka", track=1, lang=eng, default',
        'S_TEXT/UTF8, "/work/jobs/7/s1.srt", font-name="DejaVu Sans", font-size=39, '
        "font-border=3, bottom-offset=72, video-width=1280, video-height=720, fps=23.976, "
        "lang=por",
    ]


def test_a_converted_track_is_ac3() -> None:
    title = make_title_plan(audio=(track(1, "en", "truehd", "ac3"),), subtitles=())
    plan = make_disc_plan(profile="bd25", titles=(title,), menu=None, subtitle_on=0)

    meta = bd_meta(plan, BdInputs(J / "v.h264", (J / "a1.ac3",), ()))

    assert 'A_AC3, "/work/jobs/7/a1.ac3", lang=eng, default' in meta


def test_chapters_and_languages() -> None:
    assert chapters_text((0.0, 3725.0417)) == "00:00:00.000;01:02:05.042"
    assert (iso_639_2("pt"), iso_639_2("en"), iso_639_2(None), iso_639_2("xx")) == (
        "por",
        "eng",
        "und",
        "und",
    )


def test_tsmuxer_command_writes_the_iso() -> None:
    assert tsmuxer_command(J / "disc.meta", J / "disc.iso") == [
        "tsMuxeR", "/work/jobs/7/disc.meta", "/work/jobs/7/disc.iso"]  # fmt: skip


@pytest.mark.parametrize(
    ("line", "fraction"), [("75.4% complete", 0.754), ("100.0% complete", 1.0), ("Muxing", None)]
)
def test_tsmuxer_progress(line: str, fraction: float | None) -> None:
    assert tsmuxer_progress(line) == fraction


@pytest.mark.parametrize(
    "output",
    [
        "Warning! MLP codec is not standard for BD disks",
        "AC3 stream (track 3): bad frame detected at position00:02:00,000. Resync stream.",
        'Invalid SRT format. "1" is invalid timing info',
        "Can't find ttf file for font: DejaVu",
    ],
)
def test_tsmuxer_problems(output: str) -> None:
    assert tsmuxer_problem(f"0.0% complete\n{output}\n100.0% complete\n") == output


def test_a_clean_tsmuxer_run() -> None:
    clean = "\n".join(
        [
            "Decoding H264 stream (track 1): Profile: High@4.1",
            "100.0% complete",
            "Mux successful complete",
        ]
    )

    assert tsmuxer_problem(clean) is None


def test_the_subtitle_turned_on_follows_the_disc_language_not_the_track_position() -> None:
    # Disc languages fr (forced only in this title), pt, es; pt turned on.
    title = make_title_plan(chapters=(0.0,), audio=(track(1, "pt", "ac3"),),
                            subtitles=(subtitle("s3", "pt", "pgs"), subtitle("s4", "es", "pgs")),
                            subtitle_map=(None, 0, 1))  # fmt: skip
    plan = make_disc_plan(profile="bd25", titles=(title,), menu=None, subtitle_on=2)

    meta = bd_meta(plan, BdInputs(J / "v.h264", (J / "a1.ac3",), (J / "s1.sup", J / "s2.sup")))

    assert 'S_HDMV/PGS, "/work/jobs/7/s1.sup", lang=por, default=all' in meta
    assert 'S_HDMV/PGS, "/work/jobs/7/s2.sup", lang=spa\n' in meta
