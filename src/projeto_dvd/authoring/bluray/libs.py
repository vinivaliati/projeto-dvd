"""Reading a Blu-ray ISO without mounting it: libbluray (the library VLC plays discs with) for
the playlist, and libudfread for the UDF 2.50 file system. Both come with the image's ffmpeg.

ctypes needs argtypes and restype on every function: without them it crashed (segfault) in
the tests of the design review. Only the image has these libraries, so this module is tested
by the slow tests and left out of the unit coverage.
"""

import ctypes as C
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

TICKS = 90_000  # libbluray times are in 90 kHz ticks
CHUNK = 1 << 20
UDF_DIR = 1
SHA_CHUNK = 1 << 22


@dataclass(frozen=True)
class BdStream:
    coding_type: int  # 0x1b H.264, 0x81 AC-3, 0x82 DTS, 0x86 DTS-HD MA, 0x80 LPCM, 0x90 PG
    format: int
    rate: int
    language: str


@dataclass(frozen=True)
class BdInfo:
    detected: bool
    first_play: bool
    duration: float  # of playlist 0, seconds
    chapters: tuple[float, ...]
    video: tuple[BdStream, ...]
    audio: tuple[BdStream, ...]
    pg: tuple[BdStream, ...]


class _Stream(C.Structure):
    _fields_ = [("coding_type", C.c_uint8), ("format", C.c_uint8), ("rate", C.c_uint8),
                ("char_code", C.c_uint8), ("lang", C.c_char * 4), ("pid", C.c_uint16),
                ("aspect", C.c_uint8), ("subpath_id", C.c_uint8)]  # fmt: skip


class _Clip(C.Structure):
    _fields_ = [("pkt_count", C.c_uint32), ("still_mode", C.c_uint8), ("still_time", C.c_uint16),
                ("video_count", C.c_uint8), ("audio_count", C.c_uint8), ("pg_count", C.c_uint8),
                ("ig_count", C.c_uint8), ("sec_audio_count", C.c_uint8),
                ("sec_video_count", C.c_uint8), ("video", C.POINTER(_Stream)),
                ("audio", C.POINTER(_Stream)), ("pg", C.POINTER(_Stream)),
                ("ig", C.POINTER(_Stream)), ("sec_audio", C.POINTER(_Stream)),
                ("sec_video", C.POINTER(_Stream)), ("start_time", C.c_uint64),
                ("in_time", C.c_uint64), ("out_time", C.c_uint64),
                ("clip_id", C.c_char * 6)]  # fmt: skip


class _Chapter(C.Structure):
    _fields_ = [("idx", C.c_uint32), ("start", C.c_uint64), ("duration", C.c_uint64),
                ("offset", C.c_uint64), ("clip_ref", C.c_uint)]  # fmt: skip


class _Title(C.Structure):
    _fields_ = [("idx", C.c_uint32), ("playlist", C.c_uint32), ("duration", C.c_uint64),
                ("clip_count", C.c_uint32), ("angle_count", C.c_uint8),
                ("chapter_count", C.c_uint32), ("mark_count", C.c_uint32),
                ("clips", C.POINTER(_Clip)), ("chapters", C.POINTER(_Chapter)),
                ("marks", C.c_void_p)]  # fmt: skip


class _Disc(C.Structure):
    _fields_ = [("bluray_detected", C.c_uint8), ("disc_name", C.c_char_p),
                ("udf_volume_id", C.c_char_p), ("disc_id", C.c_uint8 * 20),
                ("no_menu_support", C.c_uint8), ("first_play_supported", C.c_uint8),
                ("top_menu_supported", C.c_uint8), ("num_titles", C.c_uint32)]  # fmt: skip


class _Dirent(C.Structure):
    _fields_ = [("d_type", C.c_uint), ("d_name", C.c_char_p)]


def _bluray() -> C.CDLL:
    lib = C.CDLL("libbluray.so.2")
    lib.bd_open.restype, lib.bd_open.argtypes = C.c_void_p, [C.c_char_p, C.c_char_p]
    lib.bd_close.restype, lib.bd_close.argtypes = None, [C.c_void_p]
    lib.bd_get_disc_info.restype = C.POINTER(_Disc)
    lib.bd_get_disc_info.argtypes = [C.c_void_p]
    lib.bd_get_titles.restype = C.c_uint32
    lib.bd_get_titles.argtypes = [C.c_void_p, C.c_uint8, C.c_uint32]
    lib.bd_get_playlist_info.restype = C.POINTER(_Title)
    lib.bd_get_playlist_info.argtypes = [C.c_void_p, C.c_uint32, C.c_uint]
    lib.bd_free_title_info.restype, lib.bd_free_title_info.argtypes = None, [C.POINTER(_Title)]
    return lib


def _udf() -> C.CDLL:
    lib = C.CDLL("libudfread.so.0")
    lib.udfread_init.restype, lib.udfread_init.argtypes = C.c_void_p, []
    lib.udfread_open.restype, lib.udfread_open.argtypes = C.c_int, [C.c_void_p, C.c_char_p]
    lib.udfread_close.restype, lib.udfread_close.argtypes = None, [C.c_void_p]
    lib.udfread_opendir.restype = C.c_void_p
    lib.udfread_opendir.argtypes = [C.c_void_p, C.c_char_p]
    lib.udfread_readdir.restype = C.POINTER(_Dirent)
    lib.udfread_readdir.argtypes = [C.c_void_p, C.POINTER(_Dirent)]
    lib.udfread_closedir.restype, lib.udfread_closedir.argtypes = None, [C.c_void_p]
    lib.udfread_file_open.restype = C.c_void_p
    lib.udfread_file_open.argtypes = [C.c_void_p, C.c_char_p]
    lib.udfread_file_close.restype, lib.udfread_file_close.argtypes = None, [C.c_void_p]
    lib.udfread_file_read.restype = C.c_ssize_t
    lib.udfread_file_read.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t]
    return lib


def _streams(pointer: "C._Pointer[_Stream]", count: int) -> tuple[BdStream, ...]:
    return tuple(
        BdStream(
            pointer[n].coding_type,
            pointer[n].format,
            pointer[n].rate,
            pointer[n].lang.decode(errors="replace"),
        )
        for n in range(count)
    )


def bd_info(iso: Path) -> BdInfo:
    """The first playlist of the disc; OSError when libbluray cannot open it."""
    lib = _bluray()
    disc = lib.bd_open(str(iso).encode(), None)
    if not disc:
        raise OSError(f"libbluray could not open {iso}")
    try:
        found = lib.bd_get_disc_info(disc).contents
        lib.bd_get_titles(disc, 0, 0)
        pointer = lib.bd_get_playlist_info(disc, 0, 0)
        if not pointer:
            return BdInfo(bool(found.bluray_detected), bool(found.first_play_supported),
                          0.0, (), (), (), ())  # fmt: skip
        title = pointer.contents
        clip = title.clips[0]
        result = BdInfo(
            detected=bool(found.bluray_detected),
            first_play=bool(found.first_play_supported),
            duration=title.duration / TICKS,
            chapters=tuple(title.chapters[n].start / TICKS for n in range(title.chapter_count)),
            video=_streams(clip.video, clip.video_count),
            audio=_streams(clip.audio, clip.audio_count),
            pg=_streams(clip.pg, clip.pg_count),
        )
        lib.bd_free_title_info(pointer)
        return result
    finally:
        lib.bd_close(disc)


def udf_tree(iso: Path) -> tuple[str, ...]:
    """Every file and folder of the ISO, with its full path ("/BDMV/index.bdmv", "/BDMV/")."""
    lib = _udf()
    udf = lib.udfread_init()
    if lib.udfread_open(udf, str(iso).encode()) != 0:
        raise OSError(f"libudfread could not open {iso}")
    found: list[str] = []

    def walk(folder: str) -> None:
        handle = lib.udfread_opendir(udf, folder.encode())
        entry = _Dirent()
        while lib.udfread_readdir(handle, C.byref(entry)):
            name = (entry.d_name or b"").decode(errors="replace")
            if name in (".", ".."):
                continue
            path = f"{folder.rstrip('/')}/{name}"
            if entry.d_type == UDF_DIR:
                found.append(f"{path}/")
                walk(path)
            else:
                found.append(path)
        lib.udfread_closedir(handle)

    try:
        walk("/")
    finally:
        lib.udfread_close(udf)
    return tuple(found)


def udf_copy(iso: Path, inner: str, target: Path) -> None:
    """One file of the ISO copied out (the m2ts the QA reads with ffprobe)."""
    lib = _udf()
    udf = lib.udfread_init()
    if lib.udfread_open(udf, str(iso).encode()) != 0:
        raise OSError(f"libudfread could not open {iso}")
    try:
        handle = lib.udfread_file_open(udf, inner.encode())
        if not handle:
            raise OSError(f"{inner} is not in {iso}")
        buffer = C.create_string_buffer(CHUNK)
        with target.open("wb") as out:
            while (read := lib.udfread_file_read(handle, buffer, CHUNK)) > 0:
                out.write(buffer.raw[:read])
        lib.udfread_file_close(handle)
        if read < 0:
            raise OSError(f"reading {inner} failed")
    finally:
        lib.udfread_close(udf)


def es_sha256(command: list[str]) -> str:
    """sha256 of what a command writes on stdout, read in chunks (the H.264 of a whole movie)."""
    digest = hashlib.sha256()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as run:
        assert run.stdout is not None
        while chunk := run.stdout.read(SHA_CHUNK):
            digest.update(chunk)
    if run.returncode:
        raise OSError(f"{command[0]} exited with {run.returncode}")
    return digest.hexdigest()
