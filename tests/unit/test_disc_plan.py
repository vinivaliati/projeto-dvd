import pytest
from pydantic import ValidationError

from projeto_dvd.planner.disc_plan import CoverChoices, DiscPlan, Theme
from tests.plans import make_disc_plan


def test_theme_defaults_to_auto_accent_on_the_left() -> None:
    assert Theme() == Theme(backdrop=None, accent="auto", side="left")


def test_theme_rejects_a_hex_accent() -> None:
    with pytest.raises(ValidationError):
        Theme(accent="#ffffff")  # type: ignore[arg-type]


def test_disc_plan_round_trips_through_json() -> None:
    plan = make_disc_plan()

    assert DiscPlan.model_validate_json(plan.model_dump_json()) == plan


def test_cover_texts_are_limited() -> None:
    with pytest.raises(ValidationError):
        CoverChoices(front_text="x" * 81)
    assert CoverChoices(spine_text="x" * 80).spine_text == "x" * 80
