import json
from collections.abc import Sequence
from pathlib import Path

from projeto_dvd.authoring.bluray.libs import BdInfo, BdStream
from projeto_dvd.authoring.bluray.qa import (
    REQUIRED,
    coverage_checks,
    coverage_command,
    es_check,
    es_command,
    info_checks,
    tree_checks,
)
from projeto_dvd.authoring.dvd.qa import Check
from projeto_dvd.planner.disc_plan import DiscPlan
from projeto_dvd.planner.dvd_plan import AudioChoice, SubtitleChoice
from tests.plans import make_disc_plan, make_title_plan

FRAME = 1001 / 24000


def plan(duration: float = 600.0) -> DiscPlan:
    audio = (AudioChoice(index=1, language="pt", action="copy", channels=6, kbps=640,
                         downmix=None, offset=0.0, codec="ac3"),
             AudioChoice(index=2, language="en", action="copy", channels=6, kbps=6912,
                         downmix=None, offset=0.0, codec="dts"))  # fmt: skip
    subtitles = (SubtitleChoice(key="s3", stream_index=3, file=None, language="pt", codec="pgs"),)
    title = make_title_plan(duration=duration, chapters=(0.0, 300.0), audio=audio,
                            subtitles=subtitles, width=1920, height=1080)  # fmt: skip
    return make_disc_plan(profile="bd25", titles=(title,), menu=None)


def info(**changes: object) -> BdInfo:
    fields: dict[str, object] = {
        "detected": True, "first_play": True, "duration": 600.0, "chapters": (0.0, 300.0),
        "video": (BdStream(0x1B, 6, 1, ""),),
        "audio": (BdStream(0x81, 6, 1, "por"), BdStream(0x86, 6, 1, "eng")),
        "pg": (BdStream(0x90, 0, 0, "por"),),
    }  # fmt: skip
    fields.update(changes)
    return BdInfo(**fields)  # type: ignore[arg-type]


def failed(checks: Sequence[Check]) -> list[str]:
    return [c.name for c in checks if not c.ok]


def test_a_good_tree() -> None:
    assert failed(tree_checks(REQUIRED)) == []
    missing = [path for path in REQUIRED if "CERTIFICATE" not in path]
    checks = tree_checks(missing)
    assert failed(checks) == ["tree"] and "CERTIFICATE" in checks[0].detail


def test_a_good_disc() -> None:
    assert failed(info_checks(info(), plan())) == []


def test_what_the_disc_info_catches() -> None:
    p = plan()
    assert failed(info_checks(info(detected=False), p)) == ["detected"]
    assert failed(info_checks(info(first_play=False), p)) == ["first_play"]
    assert failed(info_checks(info(duration=598.0), p)) == ["duration"]
    assert failed(info_checks(info(duration=600.0 + FRAME / 2), p)) == []
    assert failed(info_checks(info(chapters=(0.0,)), p)) == ["chapters"]
    assert failed(info_checks(info(video=(BdStream(0x02, 6, 1, ""),)), p)) == ["video"]
    short = info(audio=(BdStream(0x81, 6, 1, "por"),))
    assert failed(info_checks(short, p)) == ["audio"]
    swapped = info(audio=(BdStream(0x81, 6, 1, "eng"), BdStream(0x86, 6, 1, "por")))
    assert failed(info_checks(swapped, p)) == ["audio"]
    assert failed(info_checks(info(pg=()), p)) == ["subtitles"]


def test_lpcm_and_converted_tracks_have_their_own_types() -> None:
    title = make_title_plan(duration=600.0, chapters=(0.0,), subtitles=(),
                            audio=(AudioChoice(index=1, language="pt", action="ac3", channels=6,
                                               kbps=640, downmix=6, offset=0.0, codec="truehd"),
                                   AudioChoice(index=2, language="en", action="copy",
                                               channels=2, kbps=2304, downmix=None, offset=0.0,
                                               codec="pcm_s24le")))  # fmt: skip
    p = make_disc_plan(profile="bd25", titles=(title,), menu=None)
    disc = info(chapters=(0.0,), pg=(),
                audio=(BdStream(0x81, 6, 1, "por"), BdStream(0x80, 3, 1, "eng")))  # fmt: skip

    assert failed(info_checks(disc, p)) == []


def probe(*streams: tuple[str, float, float]) -> str:
    return json.dumps({"streams": [
        {"index": n, "codec_type": kind, "start_time": f"{start:.6f}", "duration": f"{dur:.6f}"}
        for n, (kind, start, dur) in enumerate(streams)]})  # fmt: skip


def test_every_track_covers_the_movie() -> None:
    good = probe(("video", 1.4, 600.0), ("audio", 1.4, 599.9), ("audio", 1.45, 599.8),
                 ("subtitle", 30.0, 400.0))  # fmt: skip
    assert failed(coverage_checks(good, plan())) == []

    short = probe(("video", 1.4, 600.0), ("audio", 1.4, 120.0), ("audio", 1.4, 600.0),
                  ("subtitle", 30.0, 400.0))  # fmt: skip
    checks = coverage_checks(short, plan())
    assert failed(checks) == ["coverage"] and "áudio 1" in checks[0].detail

    late = probe(("video", 1.4, 600.0), ("audio", 1.9, 599.5), ("audio", 1.4, 600.0),
                 ("subtitle", 30.0, 400.0))  # fmt: skip
    assert failed(coverage_checks(late, plan())) == ["coverage"]
    assert failed(coverage_checks("{}", plan())) == ["coverage"]


def test_the_video_on_the_disc_is_the_one_delivered() -> None:
    assert es_check("a" * 64, "a" * 64).ok
    assert not es_check("a" * 64, "b" * 64).ok


def test_qa_commands() -> None:
    m2ts = Path("/j/00000.m2ts")
    assert coverage_command(m2ts)[-1] == "/j/00000.m2ts"
    assert es_command(m2ts)[-3:] == ["-f", "h264", "-"]


def test_a_missing_audio_track_on_the_disc() -> None:
    one = probe(("video", 0.0, 600.0), ("audio", 0.0, 600.0))

    checks = coverage_checks(one, plan())

    assert failed(checks) == ["coverage"] and "1 faixas de áudio" in checks[0].detail
