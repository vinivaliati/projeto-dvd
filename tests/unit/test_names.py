from pathlib import Path

import pytest

from projeto_dvd.metadata.names import art_dir, safe_name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("O Senhor dos Anéis: A Sociedade do Anel (2001)",
         "O Senhor dos Anéis - A Sociedade do Anel (2001)"),
        ('a<b>c"d/e\\f|g?h*i', "a b c d e f g h i"),
        ("Fim com ponto.", "Fim com ponto"),
        ("  espaços  ", "espaços"),
        ("CON", "Sem nome"),
        ("nul.txt", "Sem nome"),
        ("..", "Sem nome"),
        ("", "Sem nome"),
        ("tab\tnova\nlinha", "tab nova linha"),
        ("x" * 100, "x" * 80),
        ("Amélie", "Amélie"),
    ],
)  # fmt: skip
def test_safe_name(text: str, expected: str) -> None:
    assert safe_name(text) == expected


def test_art_dir_stays_inside_covers(tmp_path: Path) -> None:
    path = art_dir(tmp_path, "Disco: 1", "Filme: Parte 2 (2001)")

    assert path == tmp_path / "covers" / "Disco - 1" / "Filme - Parte 2 (2001)"


def test_art_dir_refuses_an_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import projeto_dvd.metadata.names as names

    monkeypatch.setattr(names, "safe_name", lambda text, default="Sem nome": "../..")

    with pytest.raises(ValueError):
        art_dir(tmp_path, "a", "b")
