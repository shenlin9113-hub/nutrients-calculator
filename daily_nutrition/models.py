"""三大产能营养素相关数据模型与校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MealStatus(str, Enum):
    """餐次记录状态。"""

    RECORDED = "recorded"
    SKIPPED = "skipped"
    MISSING = "missing"


class DayStatus(str, Enum):
    """整日记录状态。"""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNRECORDED = "unrecorded"


MEAL_TYPES: tuple[str, ...] = ("breakfast", "lunch", "dinner")


@dataclass
class Macro:
    """每份或每 100g 的三大产能营养素（克）。"""

    protein_g: float
    fat_g: float
    carb_g: float

    def energy_kcal(self) -> float:
        """按蛋白×4 + 脂肪×9 + 碳水×4 计算能量。"""
        return self.protein_g * 4.0 + self.fat_g * 9.0 + self.carb_g * 4.0

    def __add__(self, other: "Macro") -> "Macro":
        if not isinstance(other, Macro):
            return NotImplemented
        return Macro(
            protein_g=self.protein_g + other.protein_g,
            fat_g=self.fat_g + other.fat_g,
            carb_g=self.carb_g + other.carb_g,
        )

    def scale(self, factor: float) -> "Macro":
        """按系数缩放，例如克重/100 得到实际摄入。"""
        return Macro(
            protein_g=self.protein_g * factor,
            fat_g=self.fat_g * factor,
            carb_g=self.carb_g * factor,
        )


def validate_grams(g: float) -> float:
    """校验克重：必须为正数。"""
    if g <= 0:
        raise ValueError("克重必须大于 0")
    return g


def validate_macro(m: Macro) -> Macro:
    """校验营养素：不允许为负，允许为 0。"""
    if m.protein_g < 0 or m.fat_g < 0 or m.carb_g < 0:
        raise ValueError("营养素不能为负数")
    return m


@dataclass
class FoodItem:
    """食物条目，内部统一按每 100g 存储。"""

    id: str
    name: str
    per_100g: Macro
    aliases: list[str] = field(default_factory=list)
    category: str = ""
    source: str = ""
    is_custom: bool = False
    note: str = ""


@dataclass
class FoodEntry:
    """一餐中的一条摄入记录，营养为写入时的快照。"""

    food_name: str
    grams: float
    macro_snapshot: Macro
    food_id: str = ""
    entry_id: Optional[int] = None


@dataclass
class Meal:
    """一餐：早餐 / 午餐 / 晚餐。"""

    meal_type: str
    status: MealStatus = MealStatus.MISSING
    entries: list[FoodEntry] = field(default_factory=list)

    def total_macro(self) -> Optional[Macro]:
        """skipped 为 0；missing 为 None；recorded 对条目求和。"""
        if self.status == MealStatus.SKIPPED:
            return Macro(0.0, 0.0, 0.0)
        if self.status == MealStatus.MISSING:
            return None
        total = Macro(0.0, 0.0, 0.0)
        for entry in self.entries:
            total = total + entry.macro_snapshot
        return total


@dataclass
class DayRecord:
    """某一天的三餐记录。"""

    date: str
    meals: dict[str, Meal] = field(default_factory=dict)
    status: DayStatus = DayStatus.INCOMPLETE
    note: str = ""

    def __post_init__(self) -> None:
        for meal_type in MEAL_TYPES:
            if meal_type not in self.meals:
                self.meals[meal_type] = Meal(meal_type=meal_type, status=MealStatus.MISSING)

    def total_macro(self) -> Macro:
        """只对 recorded 和 skipped 求和，跳过 missing。"""
        total = Macro(0.0, 0.0, 0.0)
        for meal_type in MEAL_TYPES:
            meal = self.meals[meal_type]
            part = meal.total_macro()
            if part is not None:
                total = total + part
        return total


def derive_day_status(
    day: DayRecord, explicit_unrecorded: bool = False
) -> DayStatus:
    """根据三餐状态推导日状态。显式无法记录优先。"""
    if explicit_unrecorded:
        return DayStatus.UNRECORDED
    for meal_type in MEAL_TYPES:
        if day.meals[meal_type].status == MealStatus.MISSING:
            return DayStatus.INCOMPLETE
    return DayStatus.COMPLETE
