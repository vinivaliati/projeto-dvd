from pathlib import Path

from PIL import Image

from projeto_dvd.menus.theme import (
    PALETTE,
    auto_accent,
    available_backdrops,
    backdrop_path,
    resolve_accent,
)


def test_available_backdrops_are_the_art_folders_with_a_backdrop(tmp_path: Path) -> None:
    covers = tmp_path / "covers" / "Senhor dos Aneis"
    for name in ("O Retorno do Rei (2003)", "A Sociedade do Anel (2001)", "Sem fundo"):
        (covers / name).mkdir(parents=True)
    for name in ("O Retorno do Rei (2003)", "A Sociedade do Anel (2001)"):
        (covers / name / "backdrop.jpg").write_bytes(b"x")

    assert available_backdrops(tmp_path, "Senhor dos Aneis") == (
        "A Sociedade do Anel (2001)", "O Retorno do Rei (2003)",
    )  # fmt: skip


def test_no_covers_folder_means_no_backdrops(tmp_path: Path) -> None:
    assert available_backdrops(tmp_path, "Nada") == ()


def test_backdrop_path_is_built_by_the_server(tmp_path: Path) -> None:
    path = backdrop_path(tmp_path, "Pasta", "Up (2009)")
    assert path == tmp_path / "covers" / "Pasta" / "Up (2009)" / "backdrop.jpg"


def test_backdrop_path_never_leaves_covers(tmp_path: Path) -> None:
    for name in ("..", "../../etc", "/etc/passwd"):
        path = backdrop_path(tmp_path, "Pasta", name).resolve()
        assert path.is_relative_to((tmp_path / "covers" / "Pasta").resolve())


def solid(color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (320, 180), color)


def test_auto_accent_follows_the_dominant_hue() -> None:
    assert auto_accent(solid((30, 60, 200))) == "azul"
    assert auto_accent(solid((200, 40, 30))) == "vermelho"
    assert auto_accent(solid((30, 170, 120))) == "verde"


def test_auto_accent_ignores_grey_and_dark_pictures() -> None:
    assert auto_accent(solid((128, 128, 128))) == "ambar"
    assert auto_accent(solid((20, 10, 40))) == "ambar"
    assert auto_accent(None) == "ambar"


def test_a_small_colorful_detail_loses_to_a_large_one() -> None:
    image = solid((40, 80, 200))
    image.paste((220, 40, 30), (0, 0, 20, 20))
    assert auto_accent(image) == "azul"


def test_resolve_accent() -> None:
    assert resolve_accent("verde", None) == "#3DB894"
    assert resolve_accent("auto", solid((30, 60, 200))) == PALETTE["azul"][1]


def test_palette_channels_stay_inside_the_tv_range() -> None:
    for _, color in PALETTE.values():
        channels = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
        assert all(16 <= c <= 235 for c in channels)
