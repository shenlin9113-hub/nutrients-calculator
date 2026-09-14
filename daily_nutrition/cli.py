"""中文命令行入口：单用户每日三大产能营养素记录。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from calculator import IntakeCalculator
from food_database import FoodDatabase, per_100g_from_serving
from intake_repository import IntakeRepository
from models import (
    MEAL_TYPES,
    FoodEntry,
    FoodItem,
    Macro,
    Meal,
    MealStatus,
    validate_grams,
    validate_macro,
)

BASE_DIR = Path(__file__).resolve().parent
BUILTIN_PATH = BASE_DIR / "data" / "builtin_foods.json"
CUSTOM_PATH = BASE_DIR / "data" / "custom_foods.json"
DB_PATH = BASE_DIR / "nutrition.db"

MEAL_CN = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
}


def food_source_tag(item: FoodItem) -> str:
    """内置 / 自定义 / 临时标记。"""
    if item.id.startswith("builtin_"):
        return "[内置]"
    if item.id.startswith("temp_"):
        return "[临时]"
    return "[自定义]"


def parse_date(text: str) -> str:
    """解析 YYYY-MM-DD；空字符串表示今天。"""
    raw = text.strip()
    if not raw:
        return date.today().isoformat()
    parts = raw.split("-")
    if len(parts) != 3:
        raise ValueError("日期格式错误，请使用 YYYY-MM-DD")
    year, month, day = (int(p) for p in parts)
    return date(year, month, day).isoformat()


def prompt(msg: str) -> str:
    return input(msg).strip()


def prompt_float(msg: str) -> float:
    while True:
        raw = prompt(msg)
        try:
            return float(raw)
        except ValueError:
            print("请输入数字。")


def prompt_grams(msg: str = "克重(g): ") -> float:
    while True:
        value = prompt_float(msg)
        try:
            return validate_grams(value)
        except ValueError as exc:
            print(exc)


def prompt_macro() -> Macro:
    while True:
        protein = prompt_float("蛋白质(g): ")
        fat = prompt_float("脂肪(g): ")
        carb = prompt_float("碳水(g): ")
        macro = Macro(protein, fat, carb)
        try:
            return validate_macro(macro)
        except ValueError as exc:
            print(exc)


class App:
    """CLI 应用。"""

    def __init__(self) -> None:
        self.foods = FoodDatabase(BUILTIN_PATH, CUSTOM_PATH)
        self.repo = IntakeRepository(DB_PATH)
        self.calc = IntakeCalculator()

    def run(self) -> None:
        print("每日三大产能营养素计算工具")
        while True:
            print("\n1. 记录某天饮食")
            print("2. 查看某天明细")
            print("3. 查看历史汇总")
            print("4. 添加自定义食物")
            print("5. 管理自定义食物")
            print("6. 把某天标记为无法记录")
            print("7. 删除操作")
            print("8. 退出")
            choice = prompt("请选择: ")
            try:
                if choice == "1":
                    self.record_day()
                elif choice == "2":
                    self.view_day()
                elif choice == "3":
                    self.view_history()
                elif choice == "4":
                    self.add_custom_food_flow()
                elif choice == "5":
                    self.manage_custom_foods()
                elif choice == "6":
                    self.mark_unrecorded()
                elif choice == "7":
                    self.delete_menu()
                elif choice == "8":
                    print("再见。")
                    break
                else:
                    print("无效选项，请重新输入。")
            except (EOFError, KeyboardInterrupt):
                print("\n已中断，已录入数据已保存。")
                break
            except Exception as exc:
                print(f"操作失败: {exc}")

    def _ask_date(self, default_today: bool = True) -> str:
        while True:
            hint = "（默认今天）" if default_today else ""
            raw = prompt(f"日期 YYYY-MM-DD{hint}: ")
            try:
                if not default_today and not raw:
                    print("请输入日期。")
                    continue
                return parse_date(raw)
            except ValueError:
                print("日期格式错误，请使用 YYYY-MM-DD")

    def record_day(self) -> None:
        day_date = self._ask_date()
        existing = self.repo.get_day(day_date)
        if existing is not None:
            print(self.calc.format_day_summary(existing))
            print("1. 继续录入")
            print("2. 清空重录")
            print("3. 返回")
            choice = prompt("请选择: ")
            if choice == "2":
                self.repo.clear_day(day_date)
                print("已清空该天，开始重录。")
            elif choice != "1":
                return
        for meal_type in MEAL_TYPES:
            self._handle_meal(day_date, meal_type)
        day = self.repo.get_day(day_date)
        if day is not None:
            print(self.calc.format_day_summary(day))

    def _handle_meal(self, day_date: str, meal_type: str) -> None:
        label = MEAL_CN[meal_type]
        while True:
            print(f"\n--- {label} ---")
            print("1. 添加食物")
            print("2. 标记没吃")
            print("3. 标记未记录")
            print("4. 跳过（处理下一餐）")
            choice = prompt("请选择: ")
            if choice == "1":
                self._add_food_to_meal(day_date, meal_type)
            elif choice == "2":
                self.repo.save_meal(
                    day_date,
                    Meal(meal_type=meal_type, status=MealStatus.SKIPPED, entries=[]),
                )
                print(f"{label}已标记为没吃。")
                return
            elif choice == "3":
                self.repo.save_meal(
                    day_date,
                    Meal(meal_type=meal_type, status=MealStatus.MISSING, entries=[]),
                )
                print(f"{label}已标记为未记录。")
                return
            elif choice == "4":
                return
            else:
                print("无效选项。")

    def _add_food_to_meal(self, day_date: str, meal_type: str) -> None:
        while True:
            keyword = prompt("搜索食物（名称/别名）: ")
            results = self.foods.search(keyword)
            if not results:
                print("未找到匹配食物。是否现在添加自定义食物？")
                if prompt("y/n: ").lower() == "y":
                    item = self.add_custom_food_flow()
                    if item is None:
                        continue
                    results = [item]
                else:
                    if prompt("继续搜索？y/n: ").lower() != "y":
                        return
                    continue
            for i, item in enumerate(results, start=1):
                m = item.per_100g
                print(
                    f"{i}. {food_source_tag(item)} {item.name}  "
                    f"每100g 蛋白{m.protein_g:.1f}/脂肪{m.fat_g:.1f}/碳水{m.carb_g:.1f}"
                    + (f"  ({item.note})" if item.note else "")
                )
            raw = prompt("选择序号（空则取消）: ")
            if not raw:
                return
            try:
                idx = int(raw)
                item = results[idx - 1]
            except (ValueError, IndexError):
                print("序号无效。")
                continue
            grams = prompt_grams()
            snapshot = item.per_100g.scale(grams / 100.0)
            entry = FoodEntry(
                food_name=item.name,
                grams=grams,
                macro_snapshot=snapshot,
                food_id=item.id,
            )
            self.repo.append_entry(day_date, meal_type, entry)
            print("已保存。")
            if prompt("继续添加食物？y/n: ").lower() != "y":
                return

    def add_custom_food_flow(self) -> FoodItem | None:
        """添加自定义或临时食物，返回创建的条目。"""
        name = prompt("名称: ")
        if not name:
            print("名称不能为空。")
            return None
        alias_raw = prompt("别名（逗号分隔，可空）: ")
        aliases = [a.strip() for a in alias_raw.split(",") if a.strip()]
        category = prompt("分类: ")
        print("录入方式: 1. 每 100g  2. 每份")
        mode = prompt("请选择: ")
        if mode == "2":
            serving_grams = prompt_grams("每份克重(g): ")
            print("请输入该份的营养：")
            serving_macro = prompt_macro()
            per_100g = per_100g_from_serving(serving_macro, serving_grams)
            print(
                f"已换算为每100g: 蛋白 {per_100g.protein_g:.1f}  "
                f"脂肪 {per_100g.fat_g:.1f}  碳水 {per_100g.carb_g:.1f}"
            )
            if prompt("确认？y/n: ").lower() != "y":
                return None
        else:
            print("请输入每 100g 营养：")
            per_100g = prompt_macro()
        source = prompt("来源: ")
        note = prompt("备注: ")
        save = prompt("保存到自定义库？y 保存 / n 仅临时: ").lower()
        if save == "y":
            item = FoodItem(
                id="",
                name=name,
                per_100g=per_100g,
                aliases=aliases,
                category=category,
                source=source,
                is_custom=True,
                note=note,
            )
            saved = self.foods.add_custom_food(item)
            print(f"已保存: {saved.id}")
            return saved
        temp = self.foods.create_temp_food(
            name=name,
            per_100g=per_100g,
            aliases=aliases,
            category=category,
            source=source,
            note=note,
        )
        print(f"已创建临时食物: {temp.id}")
        return temp

    def manage_custom_foods(self) -> None:
        items = self.foods.list_custom_foods()
        if not items:
            print("暂无自定义食物。")
            return
        for item in items:
            print(f"{item.id}  {item.name}")
        food_id = prompt("输入要删除的 ID（空则返回）: ")
        if not food_id:
            return
        if prompt("确认删除？输入 yes: ") != "yes":
            print("已取消。")
            return
        if self.foods.delete_custom_food(food_id):
            print("已删除。")
        else:
            print("未找到该 ID。")

    def view_day(self) -> None:
        day_date = self._ask_date()
        day = self.repo.get_day(day_date)
        if day is None:
            print("当天没有记录。")
            return
        print(self.calc.format_day_summary(day))

    def view_history(self) -> None:
        raw = prompt("查看最近多少天（默认 10）: ")
        limit = 10
        if raw:
            try:
                limit = int(raw)
            except ValueError:
                print("无效数字，使用默认 10。")
        if limit <= 0:
            print("天数必须为正，使用默认 10。")
            limit = 10
        rows = self.repo.list_days(limit=limit, offset=0)
        print(self.calc.format_history(rows))

    def mark_unrecorded(self) -> None:
        day_date = self._ask_date()
        note = prompt("备注: ")
        self.repo.mark_day_unrecorded(day_date, note)
        print("已标记为无法记录。")

    def delete_menu(self) -> None:
        print("1. 删除单条记录")
        print("2. 清空某餐")
        print("3. 清空某天")
        choice = prompt("请选择: ")
        if choice == "1":
            day_date = self._ask_date()
            day = self.repo.get_day(day_date)
            if day is None:
                print("当天没有记录。")
                return
            print(self.calc.format_day_summary(day))
            raw = prompt("要删除的记录 id: ")
            try:
                entry_id = int(raw)
            except ValueError:
                print("无效 id。")
                return
            if prompt("确认删除？输入 yes: ") != "yes":
                print("已取消。")
                return
            if self.repo.delete_entry(entry_id):
                print("已删除。")
            else:
                print("未找到该记录。")
        elif choice == "2":
            day_date = self._ask_date()
            print("1 早餐  2 午餐  3 晚餐")
            mapping = {"1": "breakfast", "2": "lunch", "3": "dinner"}
            meal_type = mapping.get(prompt("餐次: "))
            if meal_type is None:
                print("无效餐次。")
                return
            if prompt("确认清空该餐？输入 yes: ") != "yes":
                print("已取消。")
                return
            self.repo.clear_meal(day_date, meal_type)
            print("已清空。")
        elif choice == "3":
            day_date = self._ask_date()
            if prompt("确认清空整天？输入 yes: ") != "yes":
                print("已取消。")
                return
            self.repo.clear_day(day_date)
            print("已清空。")
        else:
            print("无效选项。")


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
