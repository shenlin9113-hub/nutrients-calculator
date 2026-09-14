"""摄入汇总计算与文本格式化。"""

from __future__ import annotations

from models import DayRecord, DayStatus, Macro, MealStatus

MEAL_LABELS = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
}

STATUS_LABELS = {
    MealStatus.RECORDED: "已记录",
    MealStatus.SKIPPED: "没吃",
    MealStatus.MISSING: "未记录",
}

DAY_STATUS_LABELS = {
    DayStatus.COMPLETE: "完整",
    DayStatus.INCOMPLETE: "不完整",
    DayStatus.UNRECORDED: "无法记录",
}


def fmt1(value: float) -> str:
    """浮点保留 1 位小数。"""
    return f"{value:.1f}"


class IntakeCalculator:
    """日合计与展示文案。"""

    def total_macro(self, day: DayRecord) -> Macro:
        """只对 recorded 和 skipped 求和。"""
        return day.total_macro()

    def format_day_summary(self, day: DayRecord) -> str:
        """单日明细文本。"""
        lines: list[str] = [f"===== {day.date} ====="]
        if day.status == DayStatus.UNRECORDED:
            lines.append(f"状态: {DAY_STATUS_LABELS[DayStatus.UNRECORDED]}")
            if day.note:
                lines.append(f"备注: {day.note}")
            return "\n".join(lines)

        has_missing = False
        for meal_type, label in MEAL_LABELS.items():
            meal = day.meals[meal_type]
            if meal.status == MealStatus.MISSING:
                has_missing = True
            lines.append(f"【{label}】{STATUS_LABELS[meal.status]}")
            if meal.status == MealStatus.RECORDED:
                for entry in meal.entries:
                    m = entry.macro_snapshot
                    extra = f"  id={entry.entry_id}" if entry.entry_id is not None else ""
                    lines.append(
                        f"  {entry.food_name}  {fmt1(entry.grams)}g  "
                        f"蛋白 {fmt1(m.protein_g)}  脂肪 {fmt1(m.fat_g)}  "
                        f"碳水 {fmt1(m.carb_g)}{extra}"
                    )
            sub = meal.total_macro()
            if sub is None:
                lines.append("  小计: —")
            else:
                lines.append(
                    f"  小计: 蛋白 {fmt1(sub.protein_g)}  脂肪 {fmt1(sub.fat_g)}  "
                    f"碳水 {fmt1(sub.carb_g)}  {fmt1(sub.energy_kcal())} kcal"
                )

        total = self.total_macro(day)
        p, f, c = total.protein_g, total.fat_g, total.carb_g
        kcal = total.energy_kcal()
        lines.append("--------------------")
        lines.append(
            f"总计: 蛋白 {fmt1(p)}  脂肪 {fmt1(f)}  碳水 {fmt1(c)}  "
            f"能量 {fmt1(kcal)} kcal"
        )
        lines.append(f"      ({fmt1(p)}×4 + {fmt1(f)}×9 + {fmt1(c)}×4)")
        if has_missing:
            lines.append("⚠ 本日有未记录餐次，以上仅为已记录部分")
        return "\n".join(lines)

    def format_history(self, rows: list[dict]) -> str:
        """历史汇总表格。空列表提示暂无记录。"""
        if not rows:
            return "暂无历史记录"
        headers = ("日期", "蛋白质", "脂肪", "碳水", "千卡", "状态")
        lines = [
            f"{headers[0]:<12} {headers[1]:>8} {headers[2]:>8} "
            f"{headers[3]:>8} {headers[4]:>8} {headers[5]:<8}"
        ]
        for row in rows:
            status = DayStatus(row["status"])
            if status == DayStatus.UNRECORDED or row["protein_g"] is None:
                p = f = c = k = "—"
            else:
                p = fmt1(row["protein_g"])
                f = fmt1(row["fat_g"])
                c = fmt1(row["carb_g"])
                k = fmt1(row["energy_kcal"])
            lines.append(
                f"{row['date']:<12} {p:>8} {f:>8} {c:>8} {k:>8} "
                f"{DAY_STATUS_LABELS.get(status, row['status']):<8}"
            )
        return "\n".join(lines)
