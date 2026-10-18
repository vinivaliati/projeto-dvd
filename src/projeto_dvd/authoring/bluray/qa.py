"""Checks of a Blu-ray ISO against its plan, from what libs.py and ffprobe read. Pure."""

import json
from collections.abc import Sequence
from pathlib import Path

from projeto_dvd.authoring.bluray.libs import BdInfo
from projeto_dvd.authoring.bluray.meta import iso_639_2
from projeto_dvd.authoring.dvd.qa import Check
from projeto_dvd.planner.disc_plan import DiscPlan
from projeto_dvd.planner.dvd_plan import BD_PCM_BITS, AudioChoice

FRAME = 1001 / 24000
# tsMuxeR writes CERTIFICATE empty: id.bdmv only exists on discs with AACS or BD-J.
REQUIRED = (
    "/BDMV/index.bdmv", "/BDMV/MovieObject.bdmv", "/BDMV/PLAYLIST/00000.mpls",
    "/BDMV/CLIPINF/00000.clpi", "/BDMV/STREAM/00000.m2ts", "/BDMV/BACKUP/index.bdmv",
    "/BDMV/BACKUP/MovieObject.bdmv", "/CERTIFICATE/",
)  # fmt: skip
H264, AC3, LPCM, PG = 0x1B, 0x81, 0x80, 0x90
DTS_TYPES = frozenset({0x82, 0x85, 0x86})  # core, HRA, MA: the plan does not tell them apart
START_SLACK = 0.1  # seconds an audio track may start after the video
END_SLACK = 0.5  # and end before it


def tree_checks(paths: Sequence[str]) -> list[Check]:
    found = {path.upper() for path in paths}
    missing = [path for path in REQUIRED if path.upper() not in found]
    return [Check(name="tree", label="Estrutura BDMV e CERTIFICATE completa", ok=not missing,
                  detail="Faltando: " + ", ".join(missing) if missing else "")]  # fmt: skip


def info_checks(info: BdInfo, plan: DiscPlan) -> list[Check]:
    title = plan.titles[0]
    chapters_ok = len(info.chapters) == len(title.chapters) and all(
        abs(a - b) <= FRAME for a, b in zip(info.chapters, title.chapters, strict=True)
    )
    audio = [(stream.coding_type, stream.language) for stream in info.audio]
    wanted = [(_audio_types(track), iso_639_2(track.language)) for track in title.audio]
    audio_ok = len(audio) == len(wanted) and all(
        kind in types and language == lang
        for (kind, language), (types, lang) in zip(audio, wanted, strict=True)
    )
    pg = [stream.language for stream in info.pg]
    pg_wanted = [iso_639_2(choice.language) for choice in title.subtitles]
    return [
        Check(name="detected", label="Reconhecido como Blu-ray", ok=info.detected),
        Check(name="first_play", label="Começa sozinho (First Playback)", ok=info.first_play),
        Check(name="duration", label="Duração da playlist igual à do filme",
              ok=abs(info.duration - title.duration) <= FRAME,
              detail=f"{info.duration:.3f} s de {title.duration:.3f} s"),
        Check(name="chapters", label="Capítulos", ok=chapters_ok,
              detail=f"{len(info.chapters)} de {len(title.chapters)}"),
        Check(name="video", label="Vídeo H.264",
              ok=[s.coding_type for s in info.video] == [H264]),
        Check(name="audio", label="Faixas de áudio e idiomas", ok=audio_ok,
              detail=", ".join(f"{hex(kind)} {lang}" for kind, lang in audio)),
        Check(name="subtitles", label="Legendas e idiomas", ok=pg == pg_wanted,
              detail=", ".join(pg)),
    ]  # fmt: skip


def coverage_checks(probe_json: str, plan: DiscPlan) -> list[Check]:
    """Each audio track starts with the video and lasts to its end (tsMuxeR ignores the
    delay of the source and never complains about a short track)."""
    streams = json.loads(probe_json).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    problems: list[str] = []
    if video is None:
        problems.append("sem vídeo")
    else:
        start = float(video["start_time"])
        end = start + float(video["duration"])
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        if len(audio) != len(plan.titles[0].audio):
            problems.append(f"{len(audio)} faixas de áudio")
        for n, track in enumerate(audio, 1):
            first = float(track["start_time"])
            last = first + float(track["duration"])
            if first - start > START_SLACK or end - last > END_SLACK:
                problems.append(f"áudio {n} de {first - start:.2f} s a {last - start:.2f} s")
    return [Check(name="coverage", label="Áudio do começo ao fim do filme", ok=not problems,
                  detail="; ".join(problems))]  # fmt: skip


def coverage_command(m2ts: Path) -> list[str]:
    return ["ffprobe", "-v", "error", "-show_entries",
            "stream=index,codec_type,start_time,duration", "-of", "json", str(m2ts)]  # fmt: skip


def es_command(m2ts: Path) -> list[str]:
    """The H.264 on the disc, as tsMuxeR received it (Annex B, untouched)."""
    return ["ffmpeg", "-v", "error", "-nostdin", "-i", str(m2ts), "-map", "0:v:0", "-c", "copy",
            "-f", "h264", "-"]  # fmt: skip


def es_check(disc_sha256: str, delivered_sha256: str) -> Check:
    return Check(name="es", label="Vídeo do disco idêntico ao entregue ao tsMuxeR",
                 ok=disc_sha256 == delivered_sha256, detail=disc_sha256[:12])  # fmt: skip


def _audio_types(track: AudioChoice) -> frozenset[int]:
    if track.action == "ac3" or track.codec == "ac3":
        return frozenset({AC3})
    if track.codec in BD_PCM_BITS:
        return frozenset({LPCM})
    return DTS_TYPES
