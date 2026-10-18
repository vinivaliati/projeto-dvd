from typing import Any

import pytest

from projeto_dvd.library.files import ExternalSubtitle
from projeto_dvd.library.probe import AudioTrack, Summary, summarize
from projeto_dvd.planner import dvd_plan
from projeto_dvd.planner.dvd_plan import (
    SubtitleChoice,
    audio_output,
    bd_audio_output,
    plan_chapters,
    subtitle_options,
    volume_name,
)

VIDEO = {
    "index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 800,
    "r_frame_rate": "24000/1001", "avg_frame_rate": "24000/1001",
    "display_aspect_ratio": "12:5", "start_time": "0.000",
}  # fmt: skip


def audio(
    index: int, lang: str | None, codec: str = "dts", channels: int = 6, **extra: Any
) -> dict[str, Any]:
    stream: dict[str, Any] = {"index": index, "codec_type": "audio", "codec_name": codec,
                              "channels": channels, "sample_rate": "48000"}  # fmt: skip
    if lang:
        stream["tags"] = {"language": lang}
    stream.update(extra)
    return stream


def subtitle(index: int, lang: str, codec: str = "subrip", forced: int = 0) -> dict[str, Any]:
    return {"index": index, "codec_type": "subtitle", "codec_name": codec,
            "tags": {"language": lang}, "disposition": {"forced": forced}}  # fmt: skip


def make(*streams: dict[str, Any], chapters: tuple[float, ...] = ()) -> Summary:
    return summarize(
        {
            "streams": [VIDEO, *streams],
            "format": {"duration": "7200.0"},
            "chapters": [{"start_time": str(start)} for start in chapters],
        }
    )


# Audio action


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"codec": "ac3", "channels": 6, "bit_rate": "448000"}, ("copy", 6, 448, None)),
        ({"codec": "ac3", "channels": 2, "bit_rate": "192000"}, ("copy", 2, 192, None)),
        ({"codec": "ac3", "channels": 6, "bit_rate": "640000"}, ("ac3", 6, 448, None)),
        ({"codec": "ac3", "channels": 6}, ("ac3", 6, 448, None)),  # bit_rate unknown
        ({"codec": "ac3", "channels": 6, "bit_rate": "448000", "sample_rate": "44100"},
         ("ac3", 6, 448, None)),
        ({"codec": "truehd", "channels": 8}, ("ac3", 6, 448, 6)),
        ({"codec": "dts", "channels": 5}, ("ac3", 5, 448, None)),
        ({"codec": "aac", "channels": 2}, ("ac3", 2, 192, 2)),
        ({"codec": "aac", "channels": 1}, ("ac3", 1, 96, 1)),
    ],
)  # fmt: skip
def test_audio_output(fields: dict[str, Any], expected: tuple[str, int, int, int | None]) -> None:
    codec = fields.pop("codec")
    channels = fields.pop("channels")
    summary = make(audio(1, "por", codec, channels, **fields))

    result = audio_output(summary.audio[0])

    assert (result.action, result.channels, result.kbps, result.downmix) == expected


def test_stereo_never_becomes_5_1() -> None:
    summary = make(audio(1, "eng", "aac", 2))

    assert audio_output(summary.audio[0]).channels == 2


# Suggestions


def test_subtitle_options_mark_unsupported_kinds() -> None:
    summary = make(audio(1, "por"), subtitle(2, "por", "hdmv_pgs_subtitle"),
                   subtitle(3, "por", "dvd_subtitle"), subtitle(4, "por", "ass"))  # fmt: skip
    external = (
        ExternalSubtitle(name="Filme.pt-BR.srt", language="pt-BR", image=False),
        ExternalSubtitle(name="Filme.en.sup", language="en", image=True),
        ExternalSubtitle(name="Filme.ssa", language=None, image=False),
    )

    options = {option.key: option for option in subtitle_options(summary, external)}

    assert not options["s2"].supported and "PGS" in str(options["s2"].reason)
    assert "VobSub" in str(options["s3"].reason)
    assert "ASS/SSA" in str(options["s4"].reason)
    assert options["f:Filme.pt-BR.srt"].supported
    assert options["f:Filme.pt-BR.srt"].language == "pt"
    assert not options["f:Filme.en.sup"].supported
    assert not options["f:Filme.ssa"].supported


# Chapters


def test_chapters_from_the_file_drop_close_and_late_ones() -> None:
    result = plan_chapters((0.0, 0.4, 300.0, 300.5, 7199.6, 7300.0), 7200.0, "file", 5)

    assert result.starts == (0.0, 300.0)
    assert result.note is None


def test_chapters_from_the_file_always_start_at_zero() -> None:
    assert plan_chapters((12.0, 600.0), 7200.0, "file", 5).starts == (0.0, 12.0, 600.0)


def test_chapters_every_n_minutes() -> None:
    assert plan_chapters((), 1000.0, "every", 5).starts == (0.0, 300.0, 600.0, 900.0)


def test_more_than_99_file_chapters_become_every_n_minutes() -> None:
    result = plan_chapters(tuple(float(i * 60) for i in range(140)), 140 * 60.0, "file", 5)

    assert result.minutes == 2
    assert len(result.starts) <= 99
    assert result.note == (
        "O arquivo tem 140 capítulos, e o DVD aceita até 99. Vão ser usados capítulos a cada "
        "2 minutos."
    )


def test_very_long_video_grows_the_interval() -> None:
    result = plan_chapters((), 9 * 3600.0, "every", 5)

    assert len(result.starts) <= 99
    assert result.minutes == 6


@pytest.mark.parametrize(
    ("folder", "volume"),
    [
        ("Senhor dos Anéis", "SENHOR_DOS_ANEIS"),
        ("O Poderoso Chefão: Parte II", "O_PODEROSO_CHEFAO_PARTE_II"),
        ("a" * 40, "A" * 32),
        ("***", "DVD"),
        ("Amélie (2001)", "AMELIE_2001"),
    ],
)
def test_volume_name(folder: str, volume: str) -> None:
    assert volume_name(folder) == volume


# Building the plan


def test_unknown_subtitle_codec_has_a_generic_reason() -> None:
    summary = make(audio(1, "por"), subtitle(2, "por", "eia_608"))

    option = subtitle_options(summary, ())[0]

    assert (option.supported, option.reason) == (False, dvd_plan.OTHER_SUBTITLE)


def bd_track(codec: str, channels: int = 6, **fields: Any) -> AudioTrack:
    stream = {"index": 1, "codec_type": "audio", "codec_name": codec, "channels": channels,
              "sample_rate": "48000", **fields}  # fmt: skip
    return make(stream).audio[0]


@pytest.mark.parametrize(
    ("track", "expected"),
    [
        (bd_track("ac3", bit_rate="640000"), ("copy", 6, 640, None)),
        (bd_track("ac3", bit_rate="448000"), ("copy", 6, 448, None)),
        (bd_track("ac3"), ("copy", 6, 640, None)),
        (bd_track("ac3", sample_rate="44100", bit_rate="448000"), ("ac3", 6, 640, None)),
        (bd_track("dts", profile="DTS", bit_rate="1509000"), ("copy", 6, 1509, None)),
        (bd_track("dts", profile="DTS"), ("copy", 6, 1536, None)),
        (bd_track("dts", 8, profile="DTS-HD MA", bits_per_raw_sample="24"),
         ("copy", 8, 9216, None)),
        (bd_track("dts", 6, profile="DTS-HD MA + DTS:X"), ("copy", 6, 6912, None)),
        (bd_track("dts", 6, profile="DTS-HD HRA", bits_per_raw_sample="16"),
         ("copy", 6, 4608, None)),
        (bd_track("dts", 2, profile="DTS Express"), ("ac3", 2, 256, 2)),
        (bd_track("pcm_s24le", 2), ("copy", 2, 2304, None)),
        (bd_track("pcm_s16le", 6), ("copy", 6, 4608, None)),
        (bd_track("truehd", 8), ("ac3", 6, 640, 6)),
        (bd_track("eac3", 6), ("ac3", 6, 640, None)),
        (bd_track("aac", 2), ("ac3", 2, 256, 2)),
        (bd_track("opus", 1), ("ac3", 1, 128, 1)),
    ],
)  # fmt: skip
def test_blu_ray_audio_output(
    track: AudioTrack, expected: tuple[str, int, int, int | None]
) -> None:
    out = bd_audio_output(track)

    assert (out.action, out.channels, out.kbps, out.downmix) == expected


def test_pgs_is_supported_only_on_blu_ray() -> None:
    options = subtitle_options(make(subtitle(3, "por", codec="hdmv_pgs_subtitle"),
                                    subtitle(4, "eng")), ())  # fmt: skip

    assert [(o.supported, o.bd_supported) for o in options] == [(False, True), (True, True)]


def test_old_subtitle_choices_are_text() -> None:
    old = SubtitleChoice.model_validate({"key": "s3", "stream_index": 3, "file": None,
                                         "language": "pt"})  # fmt: skip

    assert old.codec == "text"
