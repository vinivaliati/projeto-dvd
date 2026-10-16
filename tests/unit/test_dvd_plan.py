from typing import Any

import pytest

from projeto_dvd.library.files import ExternalSubtitle
from projeto_dvd.library.probe import Summary, summarize
from projeto_dvd.planner import dvd_plan
from projeto_dvd.planner.dvd_plan import (
    Choices,
    DvdPlan,
    audio_output,
    build_plan,
    plan_chapters,
    subtitle_options,
    suggest_choices,
    validate_choices,
    volume_name,
)
from projeto_dvd.planner.source import VideoMode

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


def test_suggests_portuguese_and_original_with_portuguese_first() -> None:
    summary = make(audio(1, "eng"), audio(2, "por"), audio(3, "eng", channels=2),
                   audio(4, "spa"))  # fmt: skip

    choices = suggest_choices(summary, subtitle_options(summary, ()), 7200.0)

    assert choices.audio == (1, 2)
    assert choices.first_audio == 2


def test_without_portuguese_suggests_only_the_original() -> None:
    summary = make(audio(1, "eng"), audio(2, "spa"))

    choices = suggest_choices(summary, subtitle_options(summary, ()), 7200.0)

    assert (choices.audio, choices.first_audio) == ((1,), 1)


def test_original_language_from_tmdb_when_the_track_exists() -> None:
    summary = make(audio(1, "eng"), audio(2, "jpn", channels=2), audio(3, "por"))

    choices = suggest_choices(summary, subtitle_options(summary, ()), 7200.0, "ja")

    assert choices.audio == (2, 3)


def test_original_language_from_tmdb_without_that_track_is_ignored() -> None:
    summary = make(audio(1, "eng"), audio(2, "jpn", channels=2))

    assert suggest_choices(summary, subtitle_options(summary, ()), 7200.0, "cn").audio == (1,)


def test_unknown_language_suggests_the_first_track() -> None:
    summary = make(audio(1, None), audio(2, None))

    assert suggest_choices(summary, subtitle_options(summary, ()), 7200.0).audio == (1,)


def test_subtitle_on_when_audio_is_not_portuguese() -> None:
    summary = make(audio(1, "eng"), subtitle(2, "por", forced=1), subtitle(3, "por"),
                   subtitle(4, "eng"))  # fmt: skip

    choices = suggest_choices(summary, subtitle_options(summary, ()), 7200.0)

    assert choices.subtitles == ("s2", "s3")
    assert choices.subtitle_on == "s3"  # the forced one never turns on by default


def test_subtitle_off_when_audio_is_portuguese() -> None:
    summary = make(audio(1, "por"), subtitle(2, "por"))

    assert suggest_choices(summary, subtitle_options(summary, ()), 7200.0).subtitle_on is None


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


# Validation


def choices(**fields: Any) -> Choices:
    base: dict[str, Any] = {"profile": "dvd9", "audio": (1,), "first_audio": 1,
                            "subtitles": (), "subtitle_on": None, "chapters": "every",
                            "minutes": 5}  # fmt: skip
    base.update(fields)
    return Choices(**base)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"audio": ()}, "Escolha ao menos uma faixa de áudio."),
        ({"audio": tuple(range(1, 10)), "first_audio": 1}, "O DVD aceita até 8 faixas de áudio."),
        ({"first_audio": 2}, "A faixa que toca ao colocar o disco precisa estar marcada."),
        ({"subtitle_on": "s9"}, "A legenda ligada ao iniciar precisa estar marcada."),
        ({"minutes": 0}, "O intervalo dos capítulos precisa ser de 1 minuto ou mais."),
        ({"profile": "bd25"}, "Escolha um perfil de disco."),
        ({"audio": (7,), "first_audio": 7}, "Faixa de áudio inválida."),
        ({"subtitles": ("s8",)}, "Legenda inválida."),
    ],
)
def test_validation_messages(fields: dict[str, Any], message: str) -> None:
    summary = make(*(audio(i, "por") for i in range(1, 10)), subtitle(10, "por"))
    if fields.get("audio") == (7,):
        summary = make(audio(1, "por"))

    errors = validate_choices(choices(**fields), summary, subtitle_options(summary, ()))

    assert message in errors


def test_too_many_subtitles() -> None:
    summary = make(audio(1, "por"), *(subtitle(i, "por") for i in range(2, 36)))
    keys = tuple(f"s{i}" for i in range(2, 36))

    errors = validate_choices(choices(subtitles=keys), summary, subtitle_options(summary, ()))

    assert "O DVD aceita até 32 legendas." in errors


def test_low_quality_needs_confirmation() -> None:
    long = summarize({"streams": [VIDEO, audio(1, "por")], "format": {"duration": "36000"}})

    errors = validate_choices(choices(profile="dvd9"), long, subtitle_options(long, ()))
    confirmed = validate_choices(
        choices(profile="dvd9", confirm_low=True), long, subtitle_options(long, ())
    )

    assert "Confirme que quer gerar com qualidade baixa." in errors
    assert confirmed == []


def test_profile_that_does_not_fit_is_refused() -> None:
    huge = summarize({"streams": [VIDEO, audio(1, "por")], "format": {"duration": "200000"}})

    errors = validate_choices(choices(profile="dvd5", confirm_low=True), huge,
                              subtitle_options(huge, ()))  # fmt: skip

    assert "O filme não cabe no DVD-5." in errors


# Volume name


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


def test_build_plan_orders_tracks_and_round_trips() -> None:
    summary = make(audio(1, "eng", "ac3", 6, bit_rate="448000", start_time="0.050"),
                   audio(2, "por"), subtitle(3, "por"), chapters=(0.0, 600.0))  # fmt: skip
    external = (ExternalSubtitle(name="F.en.srt", language="en", image=False),)
    options = subtitle_options(summary, external)
    picked = choices(audio=(1, 2), first_audio=2, subtitles=("s3", "f:F.en.srt"),
                     subtitle_on="f:F.en.srt", chapters="file")  # fmt: skip

    plan = build_plan(folder="Filme", path="Filme/F.mkv", size=10, mtime_ns=20, summary=summary,
                      options=options, choices=picked, mode=VideoMode.FILM,
                      top_field_first=True)  # fmt: skip

    assert [track.index for track in plan.audio] == [2, 1]
    assert plan.audio[1].action == "copy" and plan.audio[1].offset == pytest.approx(0.05)
    assert [sub.key for sub in plan.subtitles] == ["f:F.en.srt", "s3"]
    assert plan.subtitle_on
    assert plan.subtitles[0].file == "Filme/F.en.srt"
    assert plan.chapters == (0.0, 600.0)
    assert (plan.aspect, plan.width, plan.height, plan.hd_color) == ("16:9", 720, 356, True)
    assert plan.volume == "FILME" and plan.iso_name == "Filme.iso"
    assert DvdPlan.model_validate_json(plan.model_dump_json()) == plan


def test_plan_is_frozen() -> None:
    summary = make(audio(1, "por"))
    plan = build_plan(folder="F", path="F/f.mkv", size=1, mtime_ns=1, summary=summary,
                      options=[], choices=choices(), mode=VideoMode.FILM,
                      top_field_first=True)  # fmt: skip

    with pytest.raises(ValueError):
        plan.folder = "G"


def test_plan_needs_video_and_duration() -> None:
    summary = summarize({"streams": [audio(1, "por")], "format": {}})

    with pytest.raises(ValueError, match="without video"):
        build_plan(folder="F", path="F/f.mkv", size=1, mtime_ns=1, summary=summary,
                   options=[], choices=choices(), mode=VideoMode.FILM,
                   top_field_first=True)  # fmt: skip


def test_unknown_subtitle_codec_has_a_generic_reason() -> None:
    summary = make(audio(1, "por"), subtitle(2, "por", "eia_608"))

    option = subtitle_options(summary, ())[0]

    assert (option.supported, option.reason) == (False, dvd_plan.OTHER_SUBTITLE)
