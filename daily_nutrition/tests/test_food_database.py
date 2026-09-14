"""食物库：搜索、自定义写盘、临时食物、按份换算、内置只读与 ID 唯一。"""

import json
from pathlib import Path

import pytest

from food_database import FoodDatabase, food_item_to_dict, per_100g_from_serving
from models import FoodItem, Macro, validate_macro

ROOT = Path(__file__).resolve().parents[1]
BUILTIN = ROOT / "data" / "builtin_foods.json"


@pytest.fixture
def db(tmp_path: Path) -> FoodDatabase:
    custom = tmp_path / "custom_foods.json"
    return FoodDatabase(BUILTIN, custom)


def test_builtin_ids_unique_and_count():
    with open(BUILTIN, encoding="utf-8") as f:
        items = json.load(f)
    ids = [row["id"] for row in items]
    assert len(items) == 72
    assert len(ids) == len(set(ids))
    cooked = {row["name"]: row["note"] for row in items}
    assert cooked["米饭（蒸，熟）"] == "熟重"
    assert cooked["馒头（蒸，标准粉）"] == "熟重"
    assert cooked["面条（煮，熟）"] == "熟重"
    assert cooked["稻米（籼米）"] == ""


def test_search_merges_builtin_first(db: FoodDatabase, tmp_path: Path):
    hits = db.search("鸡蛋")
    assert hits
    assert hits[0].id.startswith("builtin_")
    db.add_custom_food(
        FoodItem(
            id="",
            name="鸡蛋冻",
            per_100g=Macro(10, 1, 1),
            aliases=["土鸡蛋"],
            is_custom=True,
        )
    )
    hits2 = db.search("鸡蛋")
    builtin_ids = [h.id for h in hits2 if h.id.startswith("builtin_")]
    custom_ids = [h.id for h in hits2 if h.id.startswith("custom_")]
    if builtin_ids and custom_ids:
        assert hits2.index(next(h for h in hits2 if h.id.startswith("builtin_"))) < hits2.index(
            next(h for h in hits2 if h.id.startswith("custom_"))
        )


def test_custom_persists_temp_does_not(db: FoodDatabase, tmp_path: Path):
    custom_path = tmp_path / "custom_foods.json"
    item = db.add_custom_food(
        FoodItem(id="", name="测试粉", per_100g=Macro(1, 2, 3), is_custom=True)
    )
    assert item.id == "custom_0001"
    with open(custom_path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved[0]["id"] == "custom_0001"
    before = custom_path.read_text(encoding="utf-8")
    temp = db.create_temp_food("临时期", Macro(1, 0, 0))
    assert temp.id == "temp_0001"
    assert custom_path.read_text(encoding="utf-8") == before
    assert db.get_by_id("temp_0001") is not None


def test_serving_conversion():
    per = per_100g_from_serving(Macro(10, 20, 30), 50)
    assert per.protein_g == pytest.approx(20)
    assert per.fat_g == pytest.approx(40)
    assert per.carb_g == pytest.approx(60)


def test_builtin_file_not_modified(db: FoodDatabase):
    original = BUILTIN.read_bytes()
    db.add_custom_food(FoodItem(id="", name="x", per_100g=Macro(0, 0, 1), is_custom=True))
    assert BUILTIN.read_bytes() == original


def test_delete_custom(db: FoodDatabase):
    item = db.add_custom_food(
        FoodItem(id="", name="删我", per_100g=Macro(1, 1, 1), is_custom=True)
    )
    assert db.delete_custom_food(item.id)
    assert db.list_custom_foods() == []
    validate_macro(Macro(0, 0, 0))


def test_food_item_roundtrip():
    item = FoodItem("custom_0002", "n", Macro(1, 2, 3), ["a"])
    again = food_item_to_dict(item)
    assert again["name"] == "n"
