import pytest

from projeto_dvd.planner.languages import dvd_language


@pytest.mark.parametrize(
    ("tag", "code"),
    [("por", "pt"), ("pt-BR", "pt"), ("pt", "pt"), ("eng", "en"), ("fre", "fr"), ("fra", "fr"),
     ("ger", "de"), ("jpn", "ja"), ("en.forced", "en"), (None, None), ("und", None),
     ("xyz", None), ("PT-br", "pt")],
)  # fmt: skip
def test_dvd_language(tag: str | None, code: str | None) -> None:
    assert dvd_language(tag) == code
