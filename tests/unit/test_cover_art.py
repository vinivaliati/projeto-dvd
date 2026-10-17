from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from projeto_dvd.covers.art import (
    ArtOption,
    art_options,
    default_front,
    front_file,
    print_dpi,
)
from projeto_dvd.metadata.curation import title_art_dir
from projeto_dvd.metadata.tmdb_models import DETAILS, Details
from projeto_dvd.planner.disc import DiscTitle
from tests.unit.test_disc import title


def image(path: str, language: str | None, width: int, height: int = 0,
          vote: float = 5.0) -> dict[str, Any]:  # fmt: skip
    return {"file_path": path, "iso_639_1": language, "width": width, "height": height,
            "vote_average": vote}  # fmt: skip


def movie(
    tmdb_id: int,
    posters: list[dict[str, Any]],
    backdrops: list[dict[str, Any]] = [],  # noqa: B006
    collection: dict[str, Any] | None = None,
) -> Details:
    return DETAILS.validate_python({"kind": "movie", "movie": {
        "id": tmdb_id, "title": f"Filme {tmdb_id}", "release_date": "2001-01-01",
        "belongs_to_collection": collection,
        "images": {"posters": posters, "backdrops": backdrops},
    }})  # fmt: skip


def episode(number: int, season: int = 1, season_poster: str | None = "/s1.jpg") -> Details:
    return DETAILS.validate_python({"kind": "episode", "season_poster_path": season_poster,
        "show": {"id": 7, "name": "Friends", "images": {
            "posters": [image("/friends.jpg", "pt", 2000, 3000)],
            "backdrops": [image("/fback.jpg", None, 3840, 2160)]}},
        "episode": {"season_number": season, "episode_number": number, "name": f"E{number}"},
    })  # fmt: skip


def titles_for(details: dict[str, Details]) -> list[DiscTitle]:
    return [title(path) for path in details]


def paths(options: list[ArtOption]) -> list[str]:
    return [o.path for o in options]


@pytest.mark.parametrize(
    ("size", "dpi"),
    [((1000, 1500), 187), ((1600, 2400), 300), ((2000, 3000), 375), ((1920, 1080), 145),
     ((3840, 2160), 290)],
)  # fmt: skip
def test_print_dpi_is_the_weaker_side_of_the_front_panel(size: tuple[int, int], dpi: int) -> None:
    assert print_dpi(*size) == dpi


def test_posters_by_language_then_backdrops_without_text_first() -> None:
    details = {
        "P/a.mkv": movie(
            1,
            [
                image("/en.jpg", "en", 2000, 3000, vote=9.0),
                image("/none.jpg", None, 2000, 3000),
                image("/ptlow.jpg", "pt", 1000, 1500, vote=9.0),
                image("/ptbig.jpg", "pt", 2000, 3000, vote=1.0),
                image("/fr.jpg", "fr", 2000, 3000),
                image("/tiny.jpg", "pt", 500, 750),
                image("/vector.svg", "pt", 2000, 3000),
            ],
            [image("/backen.jpg", "en", 3840, 2160), image("/back.png", None, 3840, 2160)],
        )
    }

    options = art_options(titles_for(details), details)

    assert paths(options) == ["/ptbig.jpg", "/ptlow.jpg", "/none.jpg", "/en.jpg",
                              "/back.png", "/backen.jpg"]  # fmt: skip
    assert options[0] == ArtOption("/ptbig.jpg", "poster", "pt", 375, "Filme 1")
    assert options[1].dpi == 187
    assert options[4].kind == "backdrop"


def test_without_a_height_the_shape_is_estimated_and_without_a_width_it_is_unknown() -> None:
    details = {"P/a.mkv": movie(1, [image("/old.jpg", "pt", 2000), image("/zero.jpg", "pt", 0)],
                                [image("/oldback.jpg", None, 1920)])}  # fmt: skip

    options = {o.path: o.dpi for o in art_options(titles_for(details), details)}

    assert options == {"/old.jpg": 375, "/zero.jpg": None}  # the old 1920 backdrop is 145


def test_the_episodes_of_a_season_share_the_art_and_the_season_poster_comes_first() -> None:
    details = {"P/1.mkv": episode(1), "P/2.mkv": episode(2)}

    options = art_options(titles_for(details), details)

    assert paths(options) == ["/s1.jpg", "/friends.jpg", "/fback.jpg"]
    assert options[0] == ArtOption("/s1.jpg", "poster", None, None, "Friends: Temporada 1")


def test_two_seasons_have_no_season_poster() -> None:
    details = {"P/1.mkv": episode(1), "P/2.mkv": episode(1, season=2, season_poster="/s2.jpg")}

    assert "/s1.jpg" not in paths(art_options(titles_for(details), details))


def test_the_collection_poster_needs_two_of_its_movies() -> None:
    ring = {"id": 9, "name": "Anéis", "poster_path": "/ring.jpg"}
    one = {"P/a.mkv": movie(1, [], collection=ring), "P/b.mkv": movie(2, [])}
    two = {"P/a.mkv": movie(1, [], collection=ring), "P/b.mkv": movie(2, [], collection=ring)}

    assert paths(art_options(titles_for(one), one)) == []
    assert art_options(titles_for(two), two) == [
        ArtOption("/ring.jpg", "poster", None, None, "Anéis")
    ]


def test_titles_without_a_match_add_nothing() -> None:
    details = {"P/a.mkv": movie(1, [image("/p.jpg", "pt", 2000, 3000)])}

    options = art_options([title("P/x.mkv"), *titles_for(details)], details)

    assert paths(options) == ["/p.jpg"]


def poster(path: Path, fmt: str = "JPEG") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 6), "red").save(path, fmt)
    return path


def test_the_default_front_is_the_downloaded_poster_of_the_first_title(tmp_path: Path) -> None:
    details = {"P/a.mkv": movie(1, []), "P/b.mkv": movie(2, [])}
    ordered = titles_for(details)
    assert default_front(tmp_path, "P", ordered, details) is None

    second = poster(title_art_dir(tmp_path, "P", details["P/b.mkv"]) / "poster.jpg")
    assert default_front(tmp_path, "P", ordered, details) == second
    first = poster(title_art_dir(tmp_path, "P", details["P/a.mkv"]) / "poster.jpg")
    assert default_front(tmp_path, "P", ordered, details) == first
    assert default_front(tmp_path, "P", [title("P/x.mkv")], details) is None


def test_front_file_is_the_chosen_art_when_it_opens(tmp_path: Path) -> None:
    folder = tmp_path / "covers" / "P"
    assert front_file(tmp_path, "P") is None

    png = poster(folder / "front.png", "PNG")
    assert front_file(tmp_path, "P") == png
    (folder / "front.png").write_bytes(b"not an image")
    assert front_file(tmp_path, "P") is None
