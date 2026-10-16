"""Valid plans for tests, with overridable fields."""

from typing import Any

from projeto_dvd.planner.disc_plan import DiscPlan, MenuItem, MenuPage, MenuPlan, TitlePlan
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


def make_title_plan(**overrides: Any) -> TitlePlan:
    fields: dict[str, Any] = {
        "path": "Série/S01E01.mkv", "video_index": 0, "size": 100, "mtime_ns": 200,
        "duration": 2700.0, "mode": VideoMode.FILM, "top_field_first": True, "aspect": "16:9",
        "width": 720, "height": 480, "scale": True, "hd_color": True,
        "audio": (
            AudioChoice(index=1, language="pt", action="ac3", channels=6, kbps=448,
                        downmix=None, offset=0.0),
            AudioChoice(index=2, language="en", action="copy", channels=2, kbps=192,
                        downmix=None, offset=0.0),
        ),
        "subtitles": (), "chapters": (0.0, 300.0), "audio_map": (0, 1), "subtitle_map": (),
        "menu_name": "1. Piloto",
    }  # fmt: skip
    fields.update(overrides)
    return TitlePlan(**fields)


def make_disc_plan(**overrides: Any) -> DiscPlan:
    main = MenuPage(
        kind="main", heading="Série", secondary="Temporada 1", large=True,
        items=(MenuItem(label="Tocar todos", action="play_all"),
               MenuItem(label="Episódios", action="page", target=1)),
    )  # fmt: skip
    episodes = MenuPage(
        kind="list", heading="Série", secondary="Episódios 1 a 2 de 2",
        items=(MenuItem(label="1. Piloto", action="play", target=1),
               MenuItem(label="2. Volta", action="play", target=2)),
        footer=(None, MenuItem(label="Voltar", action="back"), None),
    )  # fmt: skip
    fields: dict[str, Any] = {
        "folder": "Série", "profile": "dvd9", "video_kbps": 6000, "maxrate_kbps": 9000,
        "estimated_bytes": 4_000_000_000, "confirmed_low": False, "replace_existing": False,
        "volume": "SERIE", "iso_name": "Série.iso", "subtitle_on": 0,
        "titles": (make_title_plan(),
                   make_title_plan(path="Série/S01E02.mkv", menu_name="2. Volta")),
        "menu": MenuPlan(aspect="16:9", backdrop=None, accent="#E0A526", side="left",
                         pages=(main, episodes)),
    }  # fmt: skip
    fields.update(overrides)
    return DiscPlan(**fields)
