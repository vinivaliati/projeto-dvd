"""Automatic QA of a DVD ISO (items 1 to 3 of the checklist, and the bitstream).

Each title is checked on its own (`-title N`, the global number) and so is every menu page
with video (`-menu 1 -menu_vts 0 -pgc K`; the dispatchers have no cell and are skipped).

Commands are built here and run by the pipeline; the checks are pure functions over their
output. A failed check keeps the ISO out of the output folder.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from projeto_dvd.api.formatting import format_size
from projeto_dvd.encode.mpeg2 import NTSC_RATE_CODE, StreamReport
from projeto_dvd.jobs.runner import RunResult
from projeto_dvd.planner.disc_plan import DiscPlan, TitlePlan
from projeto_dvd.planner.languages import dvd_language
from projeto_dvd.planner.profiles import PROFILES

GIB = 1024**3
DISC_TREE = ("/AUDIO_TS", "/VIDEO_TS/VIDEO_TS.IFO", "/VIDEO_TS/VIDEO_TS.BUP")
ASPECT_CODES = {"16:9": 3, "4:3": 2}
MAX_GOP = 12
MAX_GOP_FIELDS = 36  # copied video: the NTSC limit in displayed fields
CHAPTER_TOLERANCE = 1.0
DURATION_TOLERANCE = 1.0
SYNC_TOLERANCE = 0.005
MAX_EDGE_DUPLICATES = 2


class Check(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    ok: bool
    detail: str = ""
    warning: bool = False


class QaReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: tuple[Check, ...]
    iso_bytes: int
    estimated_bytes: int

    @property
    def passed(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def first_failure(self) -> Check | None:
        return next((check for check in self.checks if not check.ok), None)


def size_checks(iso_bytes: int, plan: DiscPlan) -> list[Check]:
    profile = PROFILES[plan.profile]
    size = f"{format_size(iso_bytes)} de {format_size(profile.capacity_bytes)}"
    margin = int(profile.margin * profile.capacity_bytes)
    return [
        Check(name="size", label=f"Cabe num {profile.name}", ok=iso_bytes <= profile.capacity_bytes,
              detail=size),
        Check(name="margin", label="Dentro da margem de 97%", ok=True,
              warning=iso_bytes > margin,
              detail="Passou da margem de segurança, mas cabe na mídia." if iso_bytes > margin
              else ""),
    ]  # fmt: skip


def vob_check(dvd_dir: Path) -> Check:
    big = [vob.name for vob in sorted((dvd_dir / "VIDEO_TS").glob("*.VOB"))
           if vob.stat().st_size > GIB]  # fmt: skip
    return Check(name="vob", label="VOBs de até 1 GB", ok=not big, detail=", ".join(big))


def isoinfo_command(iso: Path) -> list[str]:
    return ["isoinfo", "-f", "-i", str(iso)]


def required_tree(titles: int, menus: bool) -> tuple[str, ...]:
    """One titleset per title; the VMGM menus live in VIDEO_TS.VOB."""
    sets = (
        f"/VIDEO_TS/VTS_{n:02d}_{part}" for n in range(1, titles + 1)
        for part in ("0.IFO", "0.BUP", "1.VOB")
    )  # fmt: skip
    return (*DISC_TREE, *(("/VIDEO_TS/VIDEO_TS.VOB",) if menus else ()), *sets)


def tree_check(listing: str, required: tuple[str, ...]) -> Check:
    found = {line.strip().split(";")[0].upper() for line in listing.splitlines() if line.strip()}
    missing = [path for path in required if path not in found]
    return Check(name="tree", label="Estrutura VIDEO_TS completa", ok=not missing,
                 detail="Faltando: " + ", ".join(missing) if missing else "")  # fmt: skip


def dvd_probe_command(iso: Path, title: int) -> list[str]:
    return [
        "ffprobe", "-v", "error", "-f", "dvdvideo", "-title", str(title), "-count_packets",
        "-show_streams", "-show_chapters", "-show_format", "-of", "json", str(iso),
    ]  # fmt: skip


def stream_checks(probe: dict[str, Any], plan: TitlePlan, video_seconds: float) -> list[Check]:
    streams = probe.get("streams", [])
    by_type = {
        kind: [s for s in streams if s.get("codec_type") == kind]
        for kind in ("video", "audio", "subtitle")
    }
    video = by_type["video"][0] if by_type["video"] else {}
    video_ok = (
        video.get("codec_name") == "mpeg2video"
        and (video.get("width"), video.get("height")) == (720, 480)
        and video.get("display_aspect_ratio") == plan.aspect
        and video.get("r_frame_rate") == "30000/1001"
    )
    starts = [float(c.get("start_time", 0)) for c in probe.get("chapters", [])]
    if not starts and len(plan.chapters) == 1:
        starts = [0.0]  # ffprobe lists no chapters for a title with only one
    chapters_ok = len(starts) == len(plan.chapters) and all(
        abs(a - b) <= CHAPTER_TOLERANCE for a, b in zip(starts, plan.chapters, strict=True)
    )
    duration = float(probe.get("format", {}).get("duration", 0))
    return [
        Check(name="video", label="Vídeo MPEG-2 720x480 NTSC", ok=video_ok,
              detail=_describe(video)),
        _tracks_check("audio", "Faixas de áudio", by_type["audio"], "ac3",
                      [a.language for a in plan.audio]),
        _tracks_check("subtitles", "Legendas", by_type["subtitle"], "dvd_subtitle",
                      [s.language for s in plan.subtitles]),
        Check(name="chapters", label="Capítulos", ok=chapters_ok,
              detail=f"{len(starts)} no disco, {len(plan.chapters)} planejados"),
        Check(name="duration", label="Duração", ok=abs(duration - video_seconds)
              <= DURATION_TOLERANCE, detail=f"{duration:.1f} s no disco, "
              f"{video_seconds:.1f} s codificados"),
    ]  # fmt: skip


def extract_video_command(iso: Path, output: Path, title: int) -> list[str]:
    return [
        "ffmpeg", "-y", "-nostdin", "-v", "error", "-f", "dvdvideo", "-title", str(title),
        "-i", str(iso), "-map", "0:v", "-c", "copy", "-f", "mpeg2video", str(output),
    ]  # fmt: skip


def menu_probe_command(iso: Path, pgc: int) -> list[str]:
    return [
        "ffprobe", "-v", "error", "-f", "dvdvideo", "-menu", "1", "-menu_vts", "0",
        "-pgc", str(pgc), "-count_packets", "-show_streams", "-of", "json", str(iso),
    ]  # fmt: skip


def extract_menu_command(iso: Path, output: Path, pgc: int) -> list[str]:
    return [
        "ffmpeg", "-y", "-nostdin", "-v", "error", "-f", "dvdvideo", "-menu", "1",
        "-menu_vts", "0", "-pgc", str(pgc), "-i", str(iso), "-map", "0:v", "-c", "copy",
        "-f", "mpeg2video", str(output),
    ]  # fmt: skip


def menu_checks(probe: dict[str, Any], aspect: str) -> list[Check]:
    streams = probe.get("streams", [])
    video: dict[str, Any] = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    ok = (
        video.get("codec_name") == "mpeg2video"
        and (video.get("width"), video.get("height")) == (720, 480)
        and video.get("display_aspect_ratio") == aspect
        and [s.get("codec_name") for s in audio] == ["ac3"]
    )
    return [Check(name="menu", label="Menu em MPEG-2 720x480 com áudio AC-3", ok=ok,
                  detail=_describe(video))]  # fmt: skip


def prefixed(checks: list[Check], name: str, label: str) -> list[Check]:
    """The checks of one title or menu page, told apart on the job page."""
    return [c.model_copy(update={"name": f"{name}-{c.name}", "label": f"{label}: {c.label}"})
            for c in checks]  # fmt: skip


def bitstream_checks(report: StreamReport, aspect: str) -> list[Check]:
    flags_ok = (
        report.frame_rate_codes == {NTSC_RATE_CODE}
        and report.progressive_sequence == {0}
        and report.aspect_codes == {ASPECT_CODES[aspect]}
    )
    return [
        Check(name="bitstream", label="Vídeo marcado como 29,97 entrelaçado (padrão DVD)",
              ok=flags_ok, detail=f"frame_rate_code {sorted(report.frame_rate_codes)}, "
              f"progressive_sequence {sorted(report.progressive_sequence)}"),
        Check(name="gop", label="GOPs fechados de até 12 quadros",
              ok=report.open_gops == 0 and report.max_gop <= MAX_GOP,
              detail=f"maior GOP {report.max_gop}, abertos {report.open_gops}"),
        Check(name="fields", label="Ordem dos campos contínua (sem tremida)",
              ok=report.parity_breaks == 0, detail=f"{report.parity_breaks} quebras"),
    ]  # fmt: skip


CELL_TOLERANCE = 0.05  # seconds between a chapter and the GOP it should start on


def copied_checks(
    disc: StreamReport, source: StreamReport, same: bool, chapters: Sequence[float]
) -> list[Check]:
    """A copied DVD video: identical to the rip, GOPs within the NTSC limit, cells on closed
    GOPs, and the field order of the original disc (its breaks were already there)."""
    closed = [start for start, is_closed in disc.gops if is_closed]
    cells_ok = all(
        chapter == 0 or any(abs(chapter - start) <= CELL_TOLERANCE for start in closed)
        for chapter in chapters
    )
    gop_ok = disc.max_gop_fields <= MAX_GOP_FIELDS and cells_ok
    breaks, original = disc.parity_breaks, source.parity_breaks
    return [
        Check(name="same_video", label="Vídeo idêntico ao do DVD original", ok=same),
        Check(name="gop", label="GOPs de até 36 campos e capítulos em GOP fechado", ok=gop_ok,
              detail=f"maior GOP {disc.max_gop_fields} campos"),
        Check(name="fields", label="Ordem dos campos igual à do DVD original",
              ok=breaks == original, warning=breaks > 0,
              detail=f"{breaks} quebras, já existiam no DVD original" if breaks == original
              else f"{breaks} quebras no disco, {original} no original"),
    ]  # fmt: skip


def sync_probe_command(mpg: Path) -> list[str]:
    return [
        "ffprobe", "-v", "error", "-read_intervals", "%+#2000",
        "-show_entries", "stream=index,codec_type,id:packet=stream_index,pts_time",
        "-of", "json", str(mpg),
    ]  # fmt: skip


def sync_check(probe: dict[str, Any], plan: TitlePlan) -> Check:
    """Each audio starts at the first video frame plus its own delay in the source."""
    streams = probe.get("streams", [])
    first: dict[int, float] = {}
    for packet in probe.get("packets", []):
        if packet.get("pts_time") not in (None, "N/A"):
            index = int(packet["stream_index"])
            first[index] = min(first.get(index, float("inf")), float(packet["pts_time"]))
    video = next((s["index"] for s in streams if s.get("codec_type") == "video"), None)
    audios = sorted((s for s in streams if s.get("codec_type") == "audio"),
                    key=lambda s: int(str(s.get("id", "0")), 0))  # fmt: skip
    if video not in first or len(audios) != len(plan.audio):
        return Check(name="sync", label="Áudio sincronizado", ok=False, detail="sem pacotes")
    gaps = [first.get(s["index"], float("inf")) - first[video] - max(a.offset, 0.0)
            for s, a in zip(audios, plan.audio, strict=True)]  # fmt: skip
    worst = max(abs(gap) for gap in gaps)
    return Check(name="sync", label="Áudio sincronizado", ok=worst <= SYNC_TOLERANCE,
                 detail=f"diferença máxima {worst * 1000:.1f} ms")  # fmt: skip


def encode_check(pass2: RunResult, mux: RunResult, author: RunResult) -> Check:
    frames = _count(pass2.progress.get("frame"))
    # One or two duplicates at the end are ffmpeg rounding the last frame duration; the judder
    # this guards against (a soft-telecined source read at 29.97) duplicates 1 frame in 5.
    allowed = max(MAX_EDGE_DUPLICATES, frames // 1000)
    duplicated = _count(pass2.progress.get("dup_frames")) > allowed
    dropped = _count(pass2.progress.get("drop_frames")) > allowed
    problems = [
        text
        for text, bad in (
            ("quadros duplicados", duplicated),
            ("quadros descartados", dropped),
            ("buffer underflow no mux", "buffer underflow" in mux.stderr),
            ("erro do dvdauthor", "ERR:" in author.stderr),
        )
        if bad
    ]
    return Check(name="encode", label="Codificação sem quadros duplicados", ok=not problems,
                 detail=", ".join(problems))  # fmt: skip


def decode_command(iso: Path, title: int) -> list[str]:
    return [
        "ffmpeg", "-nostdin", "-v", "error", "-f", "dvdvideo", "-title", str(title),
        "-i", str(iso),
        "-map", "0:v", "-map", "0:a", "-progress", "pipe:1", "-nostats", "-f", "null", "-",
    ]  # fmt: skip


def decode_check(stderr: str) -> Check:
    # Lines of the check's own null muxer (it rounds the 1.5-frame durations of pulldown into
    # equal timestamps) say nothing about the disc; decoder and demuxer lines do.
    errors = [
        line for line in stderr.splitlines() if line.strip() and not line.startswith("[null @")
    ]
    return Check(name="decode", label="Decodificado do começo ao fim sem erros", ok=not errors,
                 detail=errors[0][:200] if errors else "")  # fmt: skip


def _tracks_check(
    name: str, label: str, streams: list[dict[str, Any]], codec: str,
    languages: list[str | None],
) -> Check:  # fmt: skip
    ok = len(streams) == len(languages) and all(
        s.get("codec_name") == codec
        and int(s.get("nb_read_packets", 0)) > 0
        and (language is None or dvd_language(s.get("tags", {}).get("language")) == language)
        for s, language in zip(streams, languages, strict=False)
    )
    found = [
        f"{dvd_language(s.get('tags', {}).get('language')) or '?'} "
        f"({s.get('nb_read_packets', 0)} pacotes)"
        for s in streams
    ]
    return Check(name=name, label=label, ok=ok, detail=", ".join(found))


def _count(value: str | None) -> int:
    return int(value) if value and value.isdecimal() else 0


def _describe(video: dict[str, Any]) -> str:
    return (
        f"{video.get('codec_name')} {video.get('width')}x{video.get('height')} "
        f"{video.get('display_aspect_ratio')} {video.get('r_frame_rate')}"
    )
