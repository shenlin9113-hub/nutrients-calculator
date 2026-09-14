"""内置与自定义食物库管理。内置文件只读。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from models import FoodItem, Macro, validate_grams, validate_macro

BUILTIN_SOURCE = "《中国食物成分表》标准版第6版及国家食物与营养咨询委员会"


def _macro_from_dict(data: dict) -> Macro:
    return Macro(
        protein_g=float(data["protein_g"]),
        fat_g=float(data["fat_g"]),
        carb_g=float(data["carb_g"]),
    )


def food_item_from_dict(data: dict) -> FoodItem:
    """从 JSON 字典构造 FoodItem。"""
    return FoodItem(
        id=data["id"],
        name=data["name"],
        per_100g=_macro_from_dict(data["per_100g"]),
        aliases=list(data.get("aliases") or []),
        category=data.get("category", ""),
        source=data.get("source", ""),
        is_custom=bool(data.get("is_custom", False)),
        note=data.get("note", "") or "",
    )


def food_item_to_dict(item: FoodItem) -> dict:
    """将 FoodItem 转为可写入 JSON 的字典。"""
    return {
        "id": item.id,
        "name": item.name,
        "per_100g": {
            "protein_g": item.per_100g.protein_g,
            "fat_g": item.per_100g.fat_g,
            "carb_g": item.per_100g.carb_g,
        },
        "aliases": item.aliases,
        "category": item.category,
        "source": item.source,
        "is_custom": item.is_custom,
        "note": item.note,
    }


def per_100g_from_serving(serving_macro: Macro, serving_grams: float) -> Macro:
    """按份营养换算为每 100g：该份值 / 该份克重 × 100。"""
    validate_grams(serving_grams)
    validate_macro(serving_macro)
    return serving_macro.scale(100.0 / serving_grams)


class FoodDatabase:
    """合并内置库与自定义库；临时食物仅存在于内存。"""

    def __init__(self, builtin_path: str | Path, custom_path: str | Path) -> None:
        self.builtin_path = Path(builtin_path)
        self.custom_path = Path(custom_path)
        self._temp_foods: list[FoodItem] = []
        self._temp_seq = 0
        self._builtin = self._load_json(self.builtin_path, create_if_missing=False)
        self._custom = self._load_json(self.custom_path, create_if_missing=True)

    def _load_json(self, path: Path, create_if_missing: bool) -> list[FoodItem]:
        if not path.exists():
            if create_if_missing:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("[]", encoding="utf-8")
                return []
            return []
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise ValueError(f"食物库格式错误: {path}")
        return [food_item_from_dict(item) for item in raw]

    def _save_custom(self) -> None:
        payload = [food_item_to_dict(item) for item in self._custom]
        with open(self.custom_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _all_persistent(self) -> list[FoodItem]:
        return list(self._builtin) + list(self._custom)

    def _all(self) -> list[FoodItem]:
        return self._all_persistent() + list(self._temp_foods)

    def _next_custom_id(self) -> str:
        max_n = 0
        for item in self._custom:
            if item.id.startswith("custom_"):
                suffix = item.id[len("custom_") :]
                if suffix.isdigit():
                    max_n = max(max_n, int(suffix))
        return f"custom_{max_n + 1:04d}"

    def search(self, keyword: str) -> list[FoodItem]:
        """按名称或别名模糊匹配；内置优先，再自定义，再临时。"""
        keyword = keyword.strip().lower()
        if not keyword:
            return []
        seen: set[str] = set()
        results: list[FoodItem] = []
        for item in self._all():
            hay = [item.name, *item.aliases]
            if not any(keyword in text.lower() for text in hay):
                continue
            if item.id in seen:
                continue
            seen.add(item.id)
            results.append(item)
        return results

    def get_by_id(self, food_id: str) -> Optional[FoodItem]:
        """按 ID 查找，内置优先于同 ID 的自定义项。"""
        for item in self._builtin:
            if item.id == food_id:
                return item
        for item in self._custom:
            if item.id == food_id:
                return item
        for item in self._temp_foods:
            if item.id == food_id:
                return item
        return None

    def add_custom_food(self, food: FoodItem) -> FoodItem:
        """写入 custom_foods.json，必要时生成 custom_XXXX。"""
        validate_macro(food.per_100g)
        if not food.id or not food.id.startswith("custom_"):
            food.id = self._next_custom_id()
        food.is_custom = True
        self._custom.append(food)
        self._save_custom()
        return food

    def create_temp_food(
        self,
        name: str,
        per_100g: Macro,
        aliases: Optional[list[str]] = None,
        category: str = "",
        source: str = "",
        note: str = "",
    ) -> FoodItem:
        """创建临时食物，不写盘。"""
        validate_macro(per_100g)
        self._temp_seq += 1
        item = FoodItem(
            id=f"temp_{self._temp_seq:04d}",
            name=name,
            per_100g=per_100g,
            aliases=aliases or [],
            category=category,
            source=source or "临时",
            is_custom=True,
            note=note,
        )
        self._temp_foods.append(item)
        return item

    def list_custom_foods(self) -> list[FoodItem]:
        """列出已保存的自定义食物。"""
        return list(self._custom)

    def delete_custom_food(self, food_id: str) -> bool:
        """从自定义库硬删除。"""
        before = len(self._custom)
        self._custom = [item for item in self._custom if item.id != food_id]
        if len(self._custom) == before:
            return False
        self._save_custom()
        return True

    def list_builtin(self) -> list[FoodItem]:
        """列出内置食物（测试用）。"""
        return list(self._builtin)
