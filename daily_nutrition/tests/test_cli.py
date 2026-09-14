"""CLI 校验与搜索无结果容错。"""

from datetime import date

import pytest

from cli import parse_date
from models import validate_grams, validate_macro, Macro


def test_parse_date_today_and_valid():
    assert parse_date("") == date.today().isoformat()
    assert parse_date("2026-09-13") == "2026-09-13"


def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date("2026/09/13")
    with pytest.raises(ValueError):
        parse_date("not-a-date")


def test_grams_and_macro_used_by_cli():
    with pytest.raises(ValueError):
        validate_grams(0)
    validate_macro(Macro(0, 100, 0))


def test_search_empty_does_not_raise(tmp_path, monkeypatch):
    from food_database import FoodDatabase
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    db = FoodDatabase(root / "data" / "builtin_foods.json", tmp_path / "c.json")
    assert db.search("不存在的食物xyz") == []
