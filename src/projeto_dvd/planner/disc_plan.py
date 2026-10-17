"""The disc: what the Vini chose (saved per folder) and the plan a job runs. Pure models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from projeto_dvd.planner.dvd_plan import AudioChoice, SubtitleChoice
from projeto_dvd.planner.source import VideoMode

UND = "und"  # a track without a recognized language: "Idioma não informado"
ACCENTS = ("ambar", "vermelho", "azul", "verde", "lilas", "gelo")
Accent = Literal["auto", "ambar", "vermelho", "azul", "verde", "lilas", "gelo"]
Kind = Literal["movies", "series"]
Aspect = Literal["16:9", "4:3"]


class Theme(BaseModel):
    model_config = ConfigDict(frozen=True)

    backdrop: str | None = None  # the art folder name of one title, never a path
    accent: Accent = "auto"
    side: Literal["left", "right"] = "left"


class DiscChoices(BaseModel):
    """What the Vini picked on the Montar DVD page, saved in disc_project as it changes."""

    model_config = ConfigDict(frozen=True)

    kind: Kind
    order: tuple[str, ...]  # video paths, relative to MEDIA_DIR
    profile: str
    audio: tuple[str, ...]  # DVD languages or UND, in disc order; the first plays first
    subtitles: tuple[str, ...]
    subtitle_on: str | None
    chapters: Literal["file", "every"]
    minutes: int
    theme: Theme = Theme()


class TitlePlan(BaseModel):
    """One video of the disc, ready to encode."""

    model_config = ConfigDict(frozen=True)

    path: str  # relative to the input folder
    video_index: int
    size: int
    mtime_ns: int
    duration: float
    mode: VideoMode
    top_field_first: bool
    aspect: Aspect
    width: int
    height: int
    scale: bool
    hd_color: bool
    audio: tuple[AudioChoice, ...]  # this title's tracks, in the order of the disc languages
    subtitles: tuple[SubtitleChoice, ...]
    chapters: tuple[float, ...]
    # For each disc audio language: the stream of this title that plays (its first one when
    # the title lacks the language). For each disc subtitle language: the stream, or None.
    audio_map: tuple[int, ...]
    subtitle_map: tuple[int | None, ...]
    menu_name: str


Action = Literal[
    "play", "play_all", "page", "audio", "subtitle", "audio_menu", "subtitle_menu", "back"
]


class MenuItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    action: Action
    # play: the global title number (1..N); page: the page index; audio and subtitle: the option
    target: int = 0


class MenuPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["main", "list", "audio", "subtitles"]
    heading: str
    secondary: str | None = None
    items: tuple[MenuItem, ...]
    footer: tuple[MenuItem | None, MenuItem | None, MenuItem | None] = (None, None, None)
    focus: int = 1  # the button highlighted when the page opens (1-based)
    checked: int | None = None  # the item with a check mark (audio and subtitle variants)
    large: bool = False


class MenuPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    aspect: Aspect
    backdrop: str | None  # absolute path in the container, built by the server
    accent: str  # final hex
    side: Literal["left", "right"]
    pages: tuple[MenuPage, ...]  # pages[0] is the main menu


class DiscPlan(BaseModel):
    """Everything the pipeline needs, stored whole in the job."""

    model_config = ConfigDict(frozen=True)

    folder: str
    profile: str
    video_kbps: int
    maxrate_kbps: int
    estimated_bytes: int
    confirmed_low: bool
    replace_existing: bool
    volume: str
    iso_name: str
    subtitle_on: int  # the first value of g1: 0 without subtitle, else the language position + 1
    titles: tuple[TitlePlan, ...]
    menu: MenuPlan | None  # None only in jobs converted from phase 3, which never run again
