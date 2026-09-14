"""SQLite 摄入记录读写。每次写库后重算当日状态。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from models import (
    MEAL_TYPES,
    DayRecord,
    DayStatus,
    FoodEntry,
    Macro,
    Meal,
    MealStatus,
    derive_day_status,
)


class IntakeRepository:
    """单用户摄入记录仓库。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def close(self) -> None:
        """关闭连接。"""
        self._conn.close()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS days (
                date TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                note TEXT
            );
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                status TEXT NOT NULL,
                UNIQUE(date, meal_type),
                FOREIGN KEY(date) REFERENCES days(date) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meal_id INTEGER NOT NULL,
                food_id TEXT,
                food_name TEXT NOT NULL,
                grams REAL NOT NULL,
                protein_g REAL NOT NULL,
                fat_g REAL NOT NULL,
                carb_g REAL NOT NULL,
                FOREIGN KEY(meal_id) REFERENCES meals(id) ON DELETE CASCADE
            );
            """
        )
        self._conn.commit()

    def _ensure_day_row(self, date: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO days(date, status, note) VALUES (?, ?, ?)",
            (date, DayStatus.INCOMPLETE.value, ""),
        )

    def _refresh_day_status(self, date: str) -> None:
        day = self.get_day(date)
        if day is None:
            return
        status = derive_day_status(day, explicit_unrecorded=False)
        self._conn.execute(
            "UPDATE days SET status = ? WHERE date = ?",
            (status.value, date),
        )
        self._conn.commit()

    def save_meal(self, date: str, meal: Meal) -> None:
        """UPSERT 某天某餐：替换 status 与全部 entries。供测试与整餐状态写入。"""
        self._ensure_day_row(date)
        existing = self._conn.execute(
            "SELECT id FROM meals WHERE date = ? AND meal_type = ?",
            (date, meal.meal_type),
        ).fetchone()
        if existing:
            meal_id = int(existing["id"])
            self._conn.execute("DELETE FROM entries WHERE meal_id = ?", (meal_id,))
            self._conn.execute(
                "UPDATE meals SET status = ? WHERE id = ?",
                (meal.status.value, meal_id),
            )
        else:
            cur = self._conn.execute(
                "INSERT INTO meals(date, meal_type, status) VALUES (?, ?, ?)",
                (date, meal.meal_type, meal.status.value),
            )
            meal_id = int(cur.lastrowid)
        for entry in meal.entries:
            self._insert_entry(meal_id, entry)
        self._conn.commit()
        self._refresh_day_status(date)

    def append_entry(self, date: str, meal_type: str, entry: FoodEntry) -> None:
        """追加一条记录；餐不存在则创建为 recorded。"""
        self._ensure_day_row(date)
        row = self._conn.execute(
            "SELECT id FROM meals WHERE date = ? AND meal_type = ?",
            (date, meal_type),
        ).fetchone()
        if row is None:
            cur = self._conn.execute(
                "INSERT INTO meals(date, meal_type, status) VALUES (?, ?, ?)",
                (date, meal_type, MealStatus.RECORDED.value),
            )
            meal_id = int(cur.lastrowid)
        else:
            meal_id = int(row["id"])
            self._conn.execute(
                "UPDATE meals SET status = ? WHERE id = ?",
                (MealStatus.RECORDED.value, meal_id),
            )
        self._insert_entry(meal_id, entry)
        self._conn.commit()
        self._refresh_day_status(date)

    def _insert_entry(self, meal_id: int, entry: FoodEntry) -> None:
        self._conn.execute(
            """
            INSERT INTO entries(
                meal_id, food_id, food_name, grams, protein_g, fat_g, carb_g
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meal_id,
                entry.food_id,
                entry.food_name,
                entry.grams,
                entry.macro_snapshot.protein_g,
                entry.macro_snapshot.fat_g,
                entry.macro_snapshot.carb_g,
            ),
        )

    def get_day(self, date: str) -> Optional[DayRecord]:
        """读取某天完整记录；无 days 行则返回 None。"""
        day_row = self._conn.execute(
            "SELECT date, status, note FROM days WHERE date = ?",
            (date,),
        ).fetchone()
        if day_row is None:
            return None
        meals: dict[str, Meal] = {}
        meal_rows = self._conn.execute(
            "SELECT id, meal_type, status FROM meals WHERE date = ?",
            (date,),
        ).fetchall()
        meal_by_type = {row["meal_type"]: row for row in meal_rows}
        for meal_type in MEAL_TYPES:
            if meal_type not in meal_by_type:
                meals[meal_type] = Meal(meal_type=meal_type, status=MealStatus.MISSING)
                continue
            row = meal_by_type[meal_type]
            entries = []
            for erow in self._conn.execute(
                """
                SELECT id, food_id, food_name, grams, protein_g, fat_g, carb_g
                FROM entries WHERE meal_id = ? ORDER BY id
                """,
                (row["id"],),
            ):
                entries.append(
                    FoodEntry(
                        food_name=erow["food_name"],
                        grams=float(erow["grams"]),
                        macro_snapshot=Macro(
                            protein_g=float(erow["protein_g"]),
                            fat_g=float(erow["fat_g"]),
                            carb_g=float(erow["carb_g"]),
                        ),
                        food_id=erow["food_id"] or "",
                        entry_id=int(erow["id"]),
                    )
                )
            meals[meal_type] = Meal(
                meal_type=meal_type,
                status=MealStatus(row["status"]),
                entries=entries,
            )
        return DayRecord(
            date=day_row["date"],
            meals=meals,
            status=DayStatus(day_row["status"]),
            note=day_row["note"] or "",
        )

    def mark_day_unrecorded(self, date: str, note: str) -> None:
        """将某天标记为无法记录。"""
        self._conn.execute(
            """
            INSERT INTO days(date, status, note) VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET status = excluded.status, note = excluded.note
            """,
            (date, DayStatus.UNRECORDED.value, note),
        )
        self._conn.commit()

    def list_days(self, limit: int = 10, offset: int = 0) -> list[dict]:
        """按日期倒序列出历史；unrecorded 的四项营养为 None。"""
        day_rows = self._conn.execute(
            "SELECT date, status, note FROM days ORDER BY date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        results: list[dict] = []
        for row in day_rows:
            date = row["date"]
            status = DayStatus(row["status"])
            if status == DayStatus.UNRECORDED:
                results.append(
                    {
                        "date": date,
                        "protein_g": None,
                        "fat_g": None,
                        "carb_g": None,
                        "energy_kcal": None,
                        "status": status.value,
                        "note": row["note"] or "",
                    }
                )
                continue
            day = self.get_day(date)
            assert day is not None
            total = day.total_macro()
            results.append(
                {
                    "date": date,
                    "protein_g": total.protein_g,
                    "fat_g": total.fat_g,
                    "carb_g": total.carb_g,
                    "energy_kcal": total.energy_kcal(),
                    "status": status.value,
                    "note": row["note"] or "",
                }
            )
        return results

    def delete_entry(self, entry_id: int) -> bool:
        """硬删除单条摄入。"""
        row = self._conn.execute(
            """
            SELECT meals.date AS date FROM entries
            JOIN meals ON meals.id = entries.meal_id
            WHERE entries.id = ?
            """,
            (entry_id,),
        ).fetchone()
        if row is None:
            return False
        date = row["date"]
        self._conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self._conn.commit()
        self._refresh_day_status(date)
        return True

    def clear_meal(self, date: str, meal_type: str) -> None:
        """硬删除某餐及其条目。"""
        self._conn.execute(
            "DELETE FROM meals WHERE date = ? AND meal_type = ?",
            (date, meal_type),
        )
        self._conn.commit()
        day_row = self._conn.execute(
            "SELECT date FROM days WHERE date = ?",
            (date,),
        ).fetchone()
        if day_row is not None:
            self._refresh_day_status(date)

    def clear_day(self, date: str) -> None:
        """硬删除整天，依赖外键级联。"""
        self._conn.execute("DELETE FROM days WHERE date = ?", (date,))
        self._conn.commit()
