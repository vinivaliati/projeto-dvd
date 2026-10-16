from pathlib import Path

import pytest

from projeto_dvd.encode.mpeg2 import (
    PulldownError,
    apply_soft_pulldown,
    inspect_bytes,
    inspect_stream,
    start_codes,
)

INTRA, PREDICTED, BIDIR = 1, 2, 3


def sequence_header(rate: int = 1, aspect: int = 3) -> bytes:
    # 720x480: 0x2D0 and 0x1E0 packed in 12 bits each.
    return b"\x00\x00\x01\xb3" + bytes([0x2D, 0x01, 0xE0, (aspect << 4) | rate]) + b"\xff" * 4


def sequence_extension() -> bytes:
    # Followed by a sequence_display_extension (id 2), which both readers must skip.
    return (
        b"\x00\x00\x01\xb5" + bytes([0x14, 0x8A, 0x00, 0x01, 0x00, 0x00])
        + b"\x00\x00\x01\xb5" + bytes([0x23, 0x06, 0x06, 0x06, 0x0B, 0x42])
    )  # fmt: skip


def gop(closed: bool = True) -> bytes:
    return b"\x00\x00\x01\xb8" + bytes([0x00, 0x08, 0x00, 0x40 if closed else 0x00])


def picture(temporal: int, kind: int, tff: bool = False, rff: bool = False) -> bytes:
    header = b"\x00\x00\x01\x00" + bytes([temporal >> 2, ((temporal & 3) << 6) | (kind << 3),
                                          0xFF, 0xF8])  # fmt: skip
    flags = (0x80 if tff else 0) | (0x02 if rff else 0) | 0x01
    extension = b"\x00\x00\x01\xb5" + bytes([0x8F, 0xFF, 0xF3, flags, 0x00])
    return header + extension + b"\x00\x00\x01\x01" + b"\xaa" * 6


# Coded order of a closed GOP with two B-frames: I2 B0 B1 P5 B3 B4.
CODED = [(2, INTRA), (0, BIDIR), (1, BIDIR), (5, PREDICTED), (3, BIDIR), (4, BIDIR)]


def film_stream(gops: int = 2) -> bytes:
    data = sequence_header() + sequence_extension()
    for _ in range(gops):
        data += gop() + b"".join(picture(t, k) for t, k in CODED)
    return data


def test_start_codes_finds_every_header() -> None:
    codes = [code for _, code in start_codes(film_stream(1))]

    assert codes[:5] == [0xB3, 0xB5, 0xB5, 0xB8, 0x00]
    assert codes.count(0x00) == 6


def test_pulldown_sets_ntsc_rate_and_interlaced_sequence(tmp_path: Path) -> None:
    path = tmp_path / "v.m2v"
    path.write_bytes(film_stream())

    patched = apply_soft_pulldown(path)
    report = inspect_stream(path)

    assert patched == 12
    assert report.frame_rate_codes == {4}
    assert report.progressive_sequence == {0}
    assert report.pictures == 12
    assert report.repeated == 6
    assert report.parity_breaks == 0
    assert len(path.read_bytes()) == len(film_stream())


def test_pulldown_follows_display_order(tmp_path: Path) -> None:
    path = tmp_path / "v.m2v"
    path.write_bytes(film_stream(1))

    apply_soft_pulldown(path)

    data = path.read_bytes()
    flags = [data[pos + 7] for pos, code in start_codes(data)
             if code == 0xB5 and data[pos + 4] >> 4 == 8]  # fmt: skip
    pairs = [(bool(f & 0x80), bool(f & 0x02)) for f in flags]
    cycle = [(True, True), (False, False), (False, True), (True, False)]
    assert pairs == [cycle[t % 4] for t, _ in CODED]


def test_pulldown_refuses_a_second_run(tmp_path: Path) -> None:
    path = tmp_path / "v.m2v"
    path.write_bytes(film_stream())
    apply_soft_pulldown(path)

    with pytest.raises(PulldownError, match="já tem"):
        apply_soft_pulldown(path)


def test_pulldown_refuses_a_non_film_rate(tmp_path: Path) -> None:
    path = tmp_path / "v.m2v"
    path.write_bytes(sequence_header(rate=3) + gop() + picture(0, INTRA))

    with pytest.raises(PulldownError, match="23,976"):
        apply_soft_pulldown(path)


def test_pulldown_refuses_a_file_without_sequence_header(tmp_path: Path) -> None:
    path = tmp_path / "v.m2v"
    path.write_bytes(b"not an mpeg-2 stream" * 10)

    with pytest.raises(PulldownError, match="MPEG-2"):
        apply_soft_pulldown(path)


def test_checkpoint_can_stop_the_patch(tmp_path: Path) -> None:
    path = tmp_path / "v.m2v"
    path.write_bytes(film_stream(gops=200))

    def stop() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        apply_soft_pulldown(path, checkpoint=stop)


def test_inspection_counts_gops_and_parity_breaks() -> None:
    data = sequence_header(rate=4) + sequence_extension() + gop(closed=False)
    data += (
        picture(0, INTRA, tff=True)
        + picture(1, PREDICTED, tff=True, rff=True)
        + picture(2, PREDICTED, tff=True)
    )

    report = inspect_bytes(data)

    assert report.open_gops == 1
    assert report.max_gop == 3
    assert report.aspect_codes == {3}
    assert report.parity_breaks == 1  # after T+RFF the next picture must start on the bottom
