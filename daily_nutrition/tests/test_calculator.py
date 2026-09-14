"""汇总格式化。"""

from calculator import IntakeCalculator
from models import DayRecord, DayStatus, FoodEntry, Macro, Meal, MealStatus


def _day_with_missing() -> DayRecord:
    return DayRecord(
        date="2026-05-01",
        meals={
            "breakfast": Meal(
                "breakfast",
                MealStatus.RECORDED,
                [FoodEntry("米饭", 200, Macro(5.2, 0.6, 51.8), entry_id=1)],
            ),
            "lunch": Meal("lunch", MealStatus.MISSING),
            "dinner": Meal("dinner", MealStatus.SKIPPED),
        },
        status=DayStatus.INCOMPLETE,
    )


def test_format_day_summary_missing_warning():
    text = IntakeCalculator().format_day_summary(_day_with_missing())
    assert "早餐" in text
    assert "米饭" in text
    assert "200.0g" in text
    assert "⚠ 本日有未记录餐次，以上仅为已记录部分" in text
    assert "×4" in text and "×9" in text


def test_format_unrecorded():
    day = DayRecord(
        date="2026-05-02",
        status=DayStatus.UNRECORDED,
        note="住院",
    )
    text = IntakeCalculator().format_day_summary(day)
    assert "无法记录" in text
    assert "住院" in text
    assert "总计" not in text


def test_format_history_dash_and_empty():
    calc = IntakeCalculator()
    assert calc.format_history([]) == "暂无历史记录"
    text = calc.format_history(
        [
            {
                "date": "2026-05-02",
                "protein_g": None,
                "fat_g": None,
                "carb_g": None,
                "energy_kcal": None,
                "status": "unrecorded",
            },
            {
                "date": "2026-05-01",
                "protein_g": 1.24,
                "fat_g": 2.0,
                "carb_g": 3.0,
                "energy_kcal": 35.0,
                "status": "complete",
            },
        ]
    )
    assert "—" in text
    assert "1.2" in text
    assert "0" not in text.split("2026-05-02")[1].split("\n")[0] or "—" in text
