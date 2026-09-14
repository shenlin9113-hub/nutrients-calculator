"""摄入仓库：追加、UPSERT、级联删除、无法记录。"""

from pathlib import Path

from intake_repository import IntakeRepository
from models import DayStatus, FoodEntry, Macro, Meal, MealStatus


def _entry(name: str, p: float = 1.0) -> FoodEntry:
    return FoodEntry(name, 100, Macro(p, 0, 0), food_id="builtin_x")


def test_append_twice_keeps_two_entries(tmp_path: Path):
    repo = IntakeRepository(tmp_path / "t.db")
    repo.append_entry("2026-01-01", "breakfast", _entry("a", 1))
    day = repo.get_day("2026-01-01")
    assert day is not None
    assert len(day.meals["breakfast"].entries) == 1
    repo.append_entry("2026-01-01", "breakfast", _entry("b", 2))
    day = repo.get_day("2026-01-01")
    assert len(day.meals["breakfast"].entries) == 2
    assert day.meals["breakfast"].entries[0].food_name == "a"
    assert day.meals["breakfast"].entries[1].food_name == "b"
    repo.close()


def test_save_meal_replaces_entries(tmp_path: Path):
    repo = IntakeRepository(tmp_path / "t.db")
    repo.append_entry("2026-01-01", "lunch", _entry("a"))
    repo.append_entry("2026-01-01", "lunch", _entry("b"))
    repo.save_meal(
        "2026-01-01",
        Meal(
            meal_type="lunch",
            status=MealStatus.RECORDED,
            entries=[_entry("only")],
        ),
    )
    day = repo.get_day("2026-01-01")
    assert len(day.meals["lunch"].entries) == 1
    assert day.meals["lunch"].entries[0].food_name == "only"
    repo.close()


def test_clear_day_cascade(tmp_path: Path):
    repo = IntakeRepository(tmp_path / "t.db")
    repo.append_entry("2026-01-01", "breakfast", _entry("a"))
    repo.clear_day("2026-01-01")
    assert repo.get_day("2026-01-01") is None
    repo.close()


def test_unrecorded_list_days_none(tmp_path: Path):
    repo = IntakeRepository(tmp_path / "t.db")
    repo.mark_day_unrecorded("2026-02-02", "出差")
    rows = repo.list_days(limit=10, offset=0)
    assert len(rows) == 1
    assert rows[0]["protein_g"] is None
    assert rows[0]["fat_g"] is None
    assert rows[0]["carb_g"] is None
    assert rows[0]["energy_kcal"] is None
    assert rows[0]["status"] == DayStatus.UNRECORDED.value
    repo.append_entry("2026-02-02", "breakfast", _entry("a"))
    repo.save_meal("2026-02-02", Meal("lunch", MealStatus.SKIPPED))
    repo.save_meal("2026-02-02", Meal("dinner", MealStatus.SKIPPED))
    day = repo.get_day("2026-02-02")
    assert day.status == DayStatus.COMPLETE
    rows = repo.list_days()
    assert rows[0]["protein_g"] == 1.0
    repo.close()


def test_incomplete_when_meal_missing(tmp_path: Path):
    repo = IntakeRepository(tmp_path / "t.db")
    repo.append_entry("2026-03-03", "breakfast", _entry("a"))
    day = repo.get_day("2026-03-03")
    assert day.status == DayStatus.INCOMPLETE
    repo.close()


def test_delete_entry(tmp_path: Path):
    repo = IntakeRepository(tmp_path / "t.db")
    repo.append_entry("2026-01-01", "dinner", _entry("a"))
    day = repo.get_day("2026-01-01")
    eid = day.meals["dinner"].entries[0].entry_id
    assert repo.delete_entry(eid)
    day = repo.get_day("2026-01-01")
    assert day.meals["dinner"].entries == []
    repo.close()
