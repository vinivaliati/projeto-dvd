"""MPEG-2 video elementary streams: soft pulldown and the checks of the automatic QA.

ffmpeg cannot write repeat_first_field flags, so film is encoded at 23.976 and patched in
place afterwards, as DGPulldown has done for years: the sequence becomes 29.97 interlaced and
each picture gets top_field_first/repeat_first_field in the 3:2 cycle, by display order. The
file size does not change.
"""

import mmap
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

PICTURE = 0x00
SEQUENCE_HEADER = 0xB3
EXTENSION = 0xB5
GOP = 0xB8
SEQUENCE_EXTENSION = 1
PICTURE_CODING_EXTENSION = 8
# Part of the encode cache key: raise it whenever the patch below changes the stream.
PULLDOWN_VERSION = 1
FILM_RATE_CODE = 1  # 23.976
NTSC_RATE_CODE = 4  # 29.97
FIELD_RATE = 60000 / 1001  # NTSC fields per second
# (top_field_first, repeat_first_field) by display position: T B T | B T | B T B | T B
FILM_CYCLE = ((True, True), (False, False), (False, True), (True, False))
CHECK_EVERY = 1000
START = b"\x00\x00\x01"
HEADER_BYTES = 9  # the farthest byte read after a start code


class PulldownError(Exception):
    """The stream cannot get soft pulldown (message in Portuguese, shown on the job page)."""


def start_codes(data: bytes | mmap.mmap, start: int = 0) -> Iterator[tuple[int, int]]:
    """(position, code) of each start code with its header bytes inside the data."""
    last = len(data) - HEADER_BYTES
    position = data.find(START, start)
    while 0 <= position <= last:
        yield position, data[position + 3]
        position = data.find(START, position + 3)


def apply_soft_pulldown(path: Path, checkpoint: Callable[[], None] = lambda: None) -> int:
    """Patch a 23.976 stream in place to 29.97 with RFF flags; returns the pictures patched."""
    if path.stat().st_nlink > 1:
        # Editing in place would change the cached copy too (it is a hard link).
        raise PulldownError("O vídeo está ligado ao cache; o ajuste de quadros foi recusado.")
    with path.open("r+b") as file, mmap.mmap(file.fileno(), 0) as data:
        return _patch(data, checkpoint)


def _patch(data: mmap.mmap, checkpoint: Callable[[], None]) -> int:
    base, last, temporal, pictures, sequences = 0, -1, 0, 0, 0
    for position, code in start_codes(data):
        if code == SEQUENCE_HEADER:
            rate = data[position + 7] & 0x0F
            if rate == NTSC_RATE_CODE and sequences == 0:
                raise PulldownError("O vídeo já tem o ajuste de quadros (pulldown).")
            if rate != FILM_RATE_CODE:
                raise PulldownError(f"Taxa de quadros {rate} no vídeo; esperado 23,976.")
            data[position + 7] = (data[position + 7] & 0xF0) | NTSC_RATE_CODE
            sequences += 1
        elif code == GOP:
            base += last + 1  # display positions continue across GOPs
            last = -1
        elif code == PICTURE:
            temporal = (data[position + 4] << 2) | (data[position + 5] >> 6)
            last = max(last, temporal)
            pictures += 1
            if pictures % CHECK_EVERY == 0:
                checkpoint()
        elif code == EXTENSION:
            kind = data[position + 4] >> 4
            if kind == SEQUENCE_EXTENSION:
                data[position + 5] &= ~0x08 & 0xFF  # progressive_sequence = 0
            elif kind == PICTURE_CODING_EXTENSION:
                tff, rff = FILM_CYCLE[(base + temporal) % 4]
                flags = data[position + 7] & ~0x82 & 0xFF
                data[position + 7] = flags | (0x80 if tff else 0) | (0x02 if rff else 0)
                data[position + 8] |= 0x80  # progressive_frame = 1
    if sequences == 0:
        raise PulldownError("O arquivo não é um vídeo MPEG-2 (sem sequence header).")
    return pictures


@dataclass
class StreamReport:
    frame_rate_codes: set[int] = field(default_factory=set)
    progressive_sequence: set[int] = field(default_factory=set)
    aspect_codes: set[int] = field(default_factory=set)
    pictures: int = 0
    repeated: int = 0
    max_gop: int = 0
    open_gops: int = 0
    parity_breaks: int = 0  # a picture starting on the same field parity the last one ended
    # Phase 4b, for copied DVD video: GOP length in displayed fields, where each GOP starts (in
    # seconds) and whether it is closed, the first GOP closed (or broken_link), and a sequence
    # header before every GOP.
    max_gop_fields: int = 0
    gops: list[tuple[float, bool]] = field(default_factory=list)
    first_gop_closed: bool = True
    headers_every_gop: bool = True


def inspect_stream(path: Path) -> StreamReport:
    with path.open("rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
        return inspect_bytes(data)


def inspect_bytes(data: bytes | mmap.mmap) -> StreamReport:
    report = StreamReport()
    gop: list[tuple[int, bool, bool]] = []  # (temporal_reference, tff, rff) in coded order
    expected: list[bool] = []  # the parity the next displayed picture must start with
    temporal = 0
    fields = [0]  # displayed fields before the current GOP
    header_seen = [False]

    def close_gop() -> None:
        report.max_gop = max(report.max_gop, len(gop))
        gop_fields = sum(3 if rff else 2 for _, _, rff in gop)
        report.max_gop_fields = max(report.max_gop_fields, gop_fields)
        fields[0] += gop_fields
        for _, tff, rff in sorted(gop):
            if expected and tff != expected[0]:
                report.parity_breaks += 1
            # 3 fields end on the parity they started; 2 fields end on the other one.
            expected[:] = [not tff if rff else tff]
        gop.clear()

    for position, code in start_codes(data):
        if code == SEQUENCE_HEADER:
            report.aspect_codes.add(data[position + 7] >> 4)
            report.frame_rate_codes.add(data[position + 7] & 0x0F)
            header_seen[0] = True
        elif code == GOP:
            close_gop()
            closed = bool(data[position + 7] & 0x40)
            if not closed:
                report.open_gops += 1
            if not report.gops:
                report.first_gop_closed = closed or bool(data[position + 7] & 0x20)
            report.gops.append((fields[0] / FIELD_RATE, closed))
            report.headers_every_gop = report.headers_every_gop and header_seen[0]
            header_seen[0] = False
        elif code == PICTURE:
            temporal = (data[position + 4] << 2) | (data[position + 5] >> 6)
            report.pictures += 1
        elif code == EXTENSION:
            kind = data[position + 4] >> 4
            if kind == SEQUENCE_EXTENSION:
                report.progressive_sequence.add((data[position + 5] >> 3) & 1)
            elif kind == PICTURE_CODING_EXTENSION:
                tff, rff = bool(data[position + 7] & 0x80), bool(data[position + 7] & 0x02)
                report.repeated += rff
                gop.append((temporal, tff, rff))
    close_gop()
    return report
