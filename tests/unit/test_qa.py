from pathlib import Path
from typing import Any

import pytest

from projeto_dvd.authoring.dvd import qa
from projeto_dvd.encode.mpeg2 import StreamReport
from projeto_dvd.jobs.runner import RunResult
from projeto_dvd.planner.dvd_plan import SubtitleChoice
from projeto_dvd.planner.profiles import DVD9
from tests.plans import make_movie, movie_title
from tests.tree import make_file

DISC = make_movie()
PLAN = movie_title()


def test_size_fails_above_the_media_and_warns_above_the_margin() -> None:
    fits, margin = qa.size_checks(int(DVD9.capacity_bytes * 0.5), DISC)
    assert fits.ok and margin.ok and not margin.warning

    fits, margin = qa.size_checks(int(DVD9.capacity_bytes * 0.98), DISC)
    assert fits.ok and margin.ok and margin.warning

    fits, _ = qa.size_checks(DVD9.capacity_bytes + 1, DISC)
    assert not fits.ok


def test_vob_check(tmp_path: Path) -> None:
    make_file(tmp_path / "VIDEO_TS" / "VTS_01_1.VOB", b"x")
    assert qa.vob_check(tmp_path).ok

    big = tmp_path / "VIDEO_TS" / "VTS_01_2.VOB"
    with big.open("wb") as file:
        file.truncate(1024**3 + 1)
    assert not qa.vob_check(tmp_path).ok


LISTING = "\n".join([
    "/AUDIO_TS", "/VIDEO_TS", "/VIDEO_TS/VIDEO_TS.BUP;1", "/VIDEO_TS/VIDEO_TS.IFO;1",
    "/VIDEO_TS/VTS_01_0.BUP;1", "/VIDEO_TS/VTS_01_0.IFO;1", "/VIDEO_TS/VTS_01_1.VOB;1",
])  # fmt: skip


def test_tree_check() -> None:
    one = qa.required_tree(1, menus=False)
    assert qa.tree_check(LISTING, one).ok
    broken = qa.tree_check(LISTING.replace("/VIDEO_TS/VTS_01_0.IFO;1", ""), one)
    assert not broken.ok and "VTS_01_0.IFO" in broken.detail


def test_the_tree_needs_every_titleset_and_the_menus() -> None:
    tree = qa.required_tree(2, menus=True)
    assert "/VIDEO_TS/VIDEO_TS.VOB" in tree and "/VIDEO_TS/VTS_02_1.VOB" in tree
    check = qa.tree_check(LISTING, tree)
    assert not check.ok and "VIDEO_TS.VOB" in check.detail and "VTS_02_0.IFO" in check.detail


def probe(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "streams": [
            {"codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 480,
             "display_aspect_ratio": "16:9", "r_frame_rate": "30000/1001",
             "nb_read_packets": "300"},
            {"codec_type": "audio", "codec_name": "ac3", "tags": {"language": "por"},
             "nb_read_packets": "100"},
            {"codec_type": "audio", "codec_name": "ac3", "tags": {"language": "eng"},
             "nb_read_packets": "100"},
        ],
        "chapters": [{"start_time": "0.000000"}, {"start_time": "300.300000"}],
        "format": {"duration": "7200.4"},
    }  # fmt: skip
    data.update(changes)
    return data


def failing(checks: list[qa.Check]) -> list[str]:
    return [check.name for check in checks if not check.ok]


def test_streams_match_the_plan() -> None:
    assert failing(qa.stream_checks(probe(), PLAN, 7200.0)) == []


@pytest.mark.parametrize(
    ("mutate", "name"),
    [
        (lambda d: d["streams"][0].update(width=704), "video"),
        (lambda d: d["streams"][0].update(display_aspect_ratio="4:3"), "video"),
        (lambda d: d["streams"][1]["tags"].update(language="spa"), "audio"),
        (lambda d: d["streams"][2].update(nb_read_packets="0"), "audio"),
        (lambda d: d["streams"].pop(), "audio"),
        (lambda d: d["chapters"].pop(), "chapters"),
        (lambda d: d["format"].update(duration="7100"), "duration"),
    ],
)
def test_stream_failures(mutate: Any, name: str) -> None:
    data = probe()
    mutate(data)

    assert name in failing(qa.stream_checks(data, PLAN, 7200.0))


def test_subtitles_must_have_packets() -> None:
    plan = movie_title(subtitles=(SubtitleChoice(key="s3", stream_index=3, file=None,
                                                language="pt"),))  # fmt: skip
    data = probe()
    data["streams"].append({"codec_type": "subtitle", "codec_name": "dvd_subtitle",
                            "tags": {"language": "por"}, "nb_read_packets": "0"})  # fmt: skip

    assert "subtitles" in failing(qa.stream_checks(data, plan, 7200.0))


def report(**fields: Any) -> StreamReport:
    base = StreamReport(frame_rate_codes={4}, progressive_sequence={0}, aspect_codes={3},
                        pictures=100, repeated=50, max_gop=12)  # fmt: skip
    for key, value in fields.items():
        setattr(base, key, value)
    return base


def test_bitstream_checks() -> None:
    assert failing(qa.bitstream_checks(report(), "16:9")) == []
    assert failing(qa.bitstream_checks(report(frame_rate_codes={1}), "16:9")) == ["bitstream"]
    assert failing(qa.bitstream_checks(report(progressive_sequence={1}), "16:9")) == ["bitstream"]
    assert failing(qa.bitstream_checks(report(open_gops=1), "16:9")) == ["gop"]
    assert failing(qa.bitstream_checks(report(max_gop=13), "16:9")) == ["gop"]
    assert failing(qa.bitstream_checks(report(parity_breaks=2), "16:9")) == ["fields"]
    assert failing(qa.bitstream_checks(report(aspect_codes={2}), "16:9")) == ["bitstream"]


def packets(*items: tuple[int, float]) -> dict[str, Any]:
    return {
        "streams": [{"index": 0, "codec_type": "video", "id": "0x1e0"},
                    {"index": 1, "codec_type": "audio", "id": "0x80"},
                    {"index": 2, "codec_type": "audio", "id": "0x81"}],
        "packets": [{"stream_index": i, "pts_time": f"{t:.6f}"} for i, t in items],
    }  # fmt: skip


def test_sync_check() -> None:
    good = packets((1, 0.5556), (0, 0.5556), (2, 0.6056), (0, 0.589))
    assert qa.sync_check(good, PLAN).ok  # second audio keeps its 50 ms delay

    late = packets((0, 0.5556), (1, 0.5000), (2, 0.6056))
    assert not qa.sync_check(late, PLAN).ok


def test_encode_check() -> None:
    clean = RunResult({"dup_frames": "0", "drop_frames": "0"}, "")
    assert qa.encode_check(clean, RunResult({}, ""), RunResult({}, "")).ok
    # One duplicate at the very end is ffmpeg rounding the last frame duration, not judder.
    rounding = RunResult({"frame": "289", "dup_frames": "1", "drop_frames": "0"}, "")
    assert qa.encode_check(rounding, RunResult({}, ""), RunResult({}, "")).ok
    duplicated = RunResult({"frame": "300", "dup_frames": "60", "drop_frames": "0"}, "")
    assert not qa.encode_check(duplicated, RunResult({}, ""), RunResult({}, "")).ok
    underflow = RunResult({}, "[dvd @ 0x1] buffer underflow st=0")
    assert not qa.encode_check(clean, underflow, RunResult({}, "")).ok
    author = RunResult({}, "ERR:  no video format specified")
    assert not qa.encode_check(clean, RunResult({}, ""), author).ok


def test_decode_check() -> None:
    assert qa.decode_check("").ok
    # The check's own null muxer rounding 1.5-frame pulldown durations is not a disc error.
    muxer = "[null @ 0x62e9] Application provided invalid, non monotonically increasing dts"
    assert qa.decode_check(muxer + " to muxer in stream 0: 57 >= 57\n").ok
    assert not qa.decode_check("[mpeg2video @ 0x1] ac-tex damaged at 10 20\n").ok


def test_commands() -> None:
    iso = Path("/w/disc.iso")
    assert qa.isoinfo_command(iso) == ["isoinfo", "-f", "-i", "/w/disc.iso"]
    assert qa.dvd_probe_command(iso, 2)[:9] == [
        "ffprobe", "-v", "error", "-f", "dvdvideo", "-title", "2", "-count_packets",
        "-show_streams",
    ]  # fmt: skip
    extract = qa.extract_video_command(iso, Path("/w/qa.m2v"), 3)
    assert extract[extract.index("-map") + 1] == "0:v" and extract[-1] == "/w/qa.m2v"
    assert extract[extract.index("-title") + 1] == "3"
    decode = qa.decode_command(iso, 2)
    assert decode[decode.index("-title") + 1] == "2"
    assert decode[decode.index("-v") + 1] == "error"
    assert decode.count("-map") == 2 and decode[-3:] == ["-f", "null", "-"]


def test_report_round_trip_and_first_failure() -> None:
    checks = (qa.Check(name="a", label="A", ok=True),
              qa.Check(name="b", label="B", ok=False, detail="x"))  # fmt: skip
    result = qa.QaReport(checks=checks, iso_bytes=1, estimated_bytes=2)

    assert not result.passed
    assert result.first_failure == checks[1]
    assert qa.QaReport.model_validate_json(result.model_dump_json()) == result


def test_sync_check_without_packets_fails() -> None:
    missing = packets((1, 0.5), (2, 0.55))
    missing["packets"].append({"stream_index": 0, "pts_time": "N/A"})

    result = qa.sync_check(missing, PLAN)

    assert not result.ok and result.detail == "sem pacotes"


def test_a_single_chapter_is_not_listed_by_ffprobe() -> None:
    plan = movie_title(chapters=(0.0,))

    assert failing(qa.stream_checks(probe(chapters=[]), plan, 7200.0)) == []
    assert "chapters" in failing(qa.stream_checks(probe(chapters=[]), PLAN, 7200.0))


def test_menu_commands_read_one_vmgm_pgc() -> None:
    iso = Path("/w/disc.iso")
    probe_menu = qa.menu_probe_command(iso, 4)
    assert probe_menu[probe_menu.index("-pgc") + 1] == "4"
    assert probe_menu[probe_menu.index("-menu_vts") + 1] == "0"
    extract = qa.extract_menu_command(iso, Path("/w/m.m2v"), 3)
    assert extract[extract.index("-pgc") + 1] == "3" and extract[-1] == "/w/m.m2v"


def menu_probe(**video: Any) -> dict[str, Any]:
    base = {"codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 480,
            "display_aspect_ratio": "16:9"}  # fmt: skip
    base.update(video)
    return {"streams": [base, {"codec_type": "audio", "codec_name": "ac3"}]}


def test_menu_checks() -> None:
    assert failing(qa.menu_checks(menu_probe(), "16:9")) == []
    assert failing(qa.menu_checks(menu_probe(display_aspect_ratio="4:3"), "16:9")) == ["menu"]
    assert failing(qa.menu_checks({"streams": []}, "16:9")) == ["menu"]


def test_prefixed_checks_tell_titles_apart() -> None:
    checks = qa.prefixed([qa.Check(name="video", label="Vídeo", ok=True)], "t2", "Título 2")
    assert (checks[0].name, checks[0].label) == ("t2-video", "Título 2: Vídeo")
