import codecs
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from projeto_dvd.authoring.dvd.subtitles import (
    FONT,
    SubtitleError,
    count_cues,
    decode_srt,
    extract_command,
    prepare_srt,
    spumux_command,
    spumux_xml,
)

CUE = "1\n00:00:01,000 --> 00:00:02,500\nAção é coração\n"


@pytest.mark.parametrize(
    "data",
    [
        CUE.encode("utf-8"),
        codecs.BOM_UTF8 + CUE.encode("utf-8"),
        CUE.replace("\n", "\r\n").encode("utf-8"),
        CUE.encode("cp1252"),
        CUE.replace("\n", "\r\n").encode("cp1252"),
        CUE.encode("utf-16"),  # with BOM
    ],
)
def test_decode_srt(data: bytes) -> None:
    assert decode_srt(data) == CUE


def test_count_cues() -> None:
    assert count_cues(CUE + "\n2\n00:00:03.000 --> 00:00:04.000\nOi\n") == 2
    assert count_cues("nothing here") == 0


def test_prepare_srt_rejects_an_empty_subtitle() -> None:
    with pytest.raises(SubtitleError) as caught:
        prepare_srt(b"\r\n", "Filme.pt.srt")

    assert str(caught.value) == "A legenda Filme.pt.srt está vazia ou inválida."


def test_extract_command() -> None:
    assert extract_command(Path("/m/f.mkv"), 4, Path("/w/sub0.srt")) == [
        "ffmpeg", "-y", "-nostdin", "-i", "/m/f.mkv", "-map", "0:4", "-c:s", "srt",
        "/w/sub0.srt",
    ]  # fmt: skip


@pytest.mark.parametrize("aspect", ["16:9", "4:3"])
def test_spumux_xml(aspect: str) -> None:
    root = ET.fromstring(spumux_xml(Path("/w/sub0 & x.srt"), aspect))

    assert root.tag == "subpictures" and root.get("format") == "NTSC"
    textsub = root.find("stream/textsub")
    assert textsub is not None
    assert textsub.get("filename") == "/w/sub0 & x.srt"
    assert textsub.get("characterset") == "UTF-8"
    assert textsub.get("font") == str(FONT)
    assert textsub.get("fontsize") == "26.0"
    assert textsub.get("movie-fps") == textsub.get("subtitle-fps") == "29.97"
    assert textsub.get("movie-height") == "478"
    assert textsub.get("aspect") == aspect
    assert (textsub.get("left-margin"), textsub.get("bottom-margin")) == ("72", "48")


def test_spumux_command() -> None:
    assert spumux_command(Path("/w/sub1.xml"), 1) == ["spumux", "-s", "1", "/w/sub1.xml"]
