"""A valid DvdPlan for tests, with overridable fields."""

from typing import Any

from projeto_dvd.planner.dvd_plan import AudioChoice, DvdPlan
from projeto_dvd.planner.source import VideoMode


def make_plan(**overrides: Any) -> DvdPlan:
    fields: dict[str, Any] = {
        "folder": "Filme", "path": "Filme/Filme.mkv", "video_index": 0, "size": 100,
        "mtime_ns": 200, "duration": 7200.0, "profile": "dvd9", "video_kbps": 8487,
        "maxrate_kbps": 9000, "estimated_bytes": 8_000_000_000, "mode": VideoMode.FILM,
        "top_field_first": True, "aspect": "16:9", "width": 720, "height": 356,
        "scale": True, "hd_color": True,
        "audio": (
            AudioChoice(index=2, language="pt", action="ac3", channels=6, kbps=448,
                        downmix=None, offset=0.0),
            AudioChoice(index=1, language="en", action="copy", channels=6, kbps=448,
                        downmix=None, offset=0.05),
        ),
        "subtitles": (), "subtitle_on": False, "chapters": (0.0, 300.0),
        "confirmed_low": False, "replace_existing": False, "volume": "FILME",
        "iso_name": "Filme.iso",
    }  # fmt: skip
    fields.update(overrides)
    return DvdPlan(**fields)
