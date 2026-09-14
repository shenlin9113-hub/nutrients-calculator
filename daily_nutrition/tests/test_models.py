"""models 核心逻辑与边界。"""

import pytest

from models import (
    DayRecord,
    DayStatus,
    FoodEntry,
    Macro,
    Meal,
    MealStatus,
    derive_day_status,
    validate_grams,
    validate_macro,
)


def test_energy_kcal():
    m = Macro(protein_g=10, fat_g=10, carb_g=10)
    assert m.energy_kcal() == 10 * 4 + 10 * 9 + 10 * 4


def test_add_and_scale():
    a = Macro(1, 2, 3)
    b = Macro(4, 5, 6)
    s = a + b
    assert s.protein_g == 5 and s.fat_g == 7 and s.carb_g == 9
    scaled = a.scale(2)
    assert scaled.protein_g == 2 and scaled.fat_g == 4 and scaled.carb_g == 6


def test_meal_skipped_zero_missing_none():
    skipped = Meal(meal_type="breakfast", status=MealStatus.SKIPPED)
    assert skipped.total_macro() == Macro(0.0, 0.0, 0.0)
    missing = Meal(meal_type="lunch", status=MealStatus.MISSING)
    assert missing.total_macro() is None
    recorded = Meal(
        meal_type="dinner",
        status=MealStatus.RECORDED,
        entries=[
            FoodEntry("a", 100, Macro(1, 2, 3)),
            FoodEntry("b", 50, Macro(4, 5, 6)),
        ],
    )
    total = recorded.total_macro()
    assert total is not None
    assert total.protein_g == 5


def test_day_total_skips_missing():
    day = DayRecord(
        date="2026-01-01",
        meals={
            "breakfast": Meal(
                "breakfast",
                MealStatus.RECORDED,
                [FoodEntry("a", 100, Macro(1, 0, 0))],
            ),
            "lunch": Meal("lunch", MealStatus.MISSING),
            "dinner": Meal("dinner", MealStatus.SKIPPED),
        },
    )
    total = day.total_macro()
    assert total.protein_g == 1
    assert total.fat_g == 0


def test_derive_day_status():
    incomplete = DayRecord(date="2026-01-01")
    assert derive_day_status(incomplete) == DayStatus.INCOMPLETE
    complete = DayRecord(
        date="2026-01-01",
        meals={
            "breakfast": Meal("breakfast", MealStatus.RECORDED),
            "lunch": Meal("lunch", MealStatus.SKIPPED),
            "dinner": Meal("dinner", MealStatus.RECORDED),
        },
    )
    assert derive_day_status(complete) == DayStatus.COMPLETE
    assert derive_day_status(complete, explicit_unrecorded=True) == DayStatus.UNRECORDED


def test_validate_grams_and_macro():
    assert validate_grams(1) == 1
    with pytest.raises(ValueError):
        validate_grams(0)
    with pytest.raises(ValueError):
        validate_grams(-1)
    assert validate_macro(Macro(0, 0, 0)).protein_g == 0
    with pytest.raises(ValueError):
        validate_macro(Macro(-0.1, 0, 0))
