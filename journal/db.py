"""Работа с базой данных SQLite: пользователи, классы, ученики, предметы, оценки, посещаемость."""
import sqlite3
from datetime import date, datetime

from .quarters import quarter_for, round_half_up
from .security import hash_password, verify_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'teacher'))
);
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    value INTEGER NOT NULL CHECK (value BETWEEN 1 AND 10),
    grade_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teacher_classes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, class_id)
);
CREATE TABLE IF NOT EXISTS attendance (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    att_date TEXT NOT NULL,
    present INTEGER NOT NULL CHECK (present IN (0, 1)),
    PRIMARY KEY (student_id, att_date)
);
"""

DEFAULT_SUBJECTS = ["Математика", "Қазақ тілі", "Русский язык", "Информатика", "Физика"]


class ValidationError(ValueError):
    """Некорректные данные, введённые пользователем."""


def parse_date(text: str) -> str:
    """Принимает ГГГГ-ММ-ДД или ДД.ММ.ГГГГ, возвращает ГГГГ-ММ-ДД."""
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValidationError("Дата должна быть в формате ГГГГ-ММ-ДД или ДД.ММ.ГГГГ")


class Database:
    def __init__(self, path: str = "school.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._seed()

    def close(self):
        self.conn.close()

    def _migrate(self):
        """Старые базы создавались с оценками 1–5: пересоздаём таблицу оценок под шкалу 1–10."""
        row = self.conn.execute("SELECT sql FROM sqlite_master WHERE name = 'grades'").fetchone()
        if row and "BETWEEN 1 AND 5" in row["sql"]:
            self.conn.executescript("""
                ALTER TABLE grades RENAME TO grades_old;
                CREATE TABLE grades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    subject_id INTEGER NOT NULL REFERENCES subjects(id),
                    value INTEGER NOT NULL CHECK (value BETWEEN 1 AND 10),
                    grade_date TEXT NOT NULL
                );
                INSERT INTO grades SELECT id, student_id, subject_id, value, grade_date FROM grades_old;
                DROP TABLE grades_old;
            """)

    def _seed(self):
        if not self.conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            self.add_user("admin", "admin123", "admin")
        if not self.conn.execute("SELECT 1 FROM subjects LIMIT 1").fetchone():
            for name in DEFAULT_SUBJECTS:
                self.conn.execute("INSERT INTO subjects(name) VALUES (?)", (name,))
            self.conn.commit()

    # ---------------- пользователи и роли ----------------
    def add_user(self, username: str, password: str, role: str = "teacher") -> int:
        username = username.strip()
        if not username or len(password) < 6:
            raise ValidationError("Логин не должен быть пустым, пароль — минимум 6 символов")
        if role not in ("admin", "teacher"):
            raise ValidationError("Неизвестная роль")
        try:
            cur = self.conn.execute(
                "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Такой пользователь уже существует") from exc
        self.conn.commit()
        return cur.lastrowid

    def authenticate(self, username: str, password: str):
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return dict(row)
        return None

    def change_password(self, user_id: int, old_password: str, new_password: str):
        row = self.conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not verify_password(old_password, row["password_hash"]):
            raise ValidationError("Текущий пароль указан неверно")
        if len(new_password) < 6:
            raise ValidationError("Новый пароль — минимум 6 символов")
        self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id)
        )
        self.conn.commit()

    def list_users(self):
        users = []
        for u in self.conn.execute("SELECT id, username, role FROM users ORDER BY username"):
            names = [
                r["name"]
                for r in self.conn.execute(
                    """SELECT c.name FROM classes c JOIN teacher_classes t ON t.class_id = c.id
                       WHERE t.user_id = ? ORDER BY c.name""",
                    (u["id"],),
                )
            ]
            users.append({**dict(u), "classes": names})
        return users

    def delete_user(self, user_id: int, current_user_id: int | None = None):
        if user_id == current_user_id:
            raise ValidationError("Нельзя удалить самого себя")
        row = self.conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return
        if row["role"] == "admin":
            admins = self.conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
            if admins <= 1:
                raise ValidationError("Нельзя удалить последнего администратора")
        self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.conn.commit()

    def set_user_classes(self, user_id: int, class_ids: list[int]):
        self.conn.execute("DELETE FROM teacher_classes WHERE user_id = ?", (user_id,))
        for cid in class_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO teacher_classes(user_id, class_id) VALUES (?, ?)", (user_id, cid)
            )
        self.conn.commit()

    def user_class_ids(self, user_id: int) -> list[int]:
        return [r[0] for r in self.conn.execute(
            "SELECT class_id FROM teacher_classes WHERE user_id = ?", (user_id,))]

    # ---------------- классы ----------------
    def add_class(self, name: str, user: dict | None = None) -> int:
        """Если класс создаёт учитель, он автоматически закрепляется за ним."""
        name = name.strip()
        if not name:
            raise ValidationError("Название класса не может быть пустым")
        try:
            cur = self.conn.execute("INSERT INTO classes(name) VALUES (?)", (name,))
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Такой класс уже есть") from exc
        if user and user["role"] != "admin":
            self.conn.execute(
                "INSERT INTO teacher_classes(user_id, class_id) VALUES (?, ?)", (user["id"], cur.lastrowid)
            )
        self.conn.commit()
        return cur.lastrowid

    def delete_class(self, class_id: int):
        """Удаляет класс вместе с его учениками и их оценками."""
        self.conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        self.conn.commit()

    def list_classes(self, user: dict | None = None):
        """Администратор (и вызов без пользователя) видит все классы, учитель — только свои."""
        if user and user["role"] != "admin":
            rows = self.conn.execute(
                """SELECT c.* FROM classes c JOIN teacher_classes t ON t.class_id = c.id
                   WHERE t.user_id = ? ORDER BY c.name""",
                (user["id"],),
            )
        else:
            rows = self.conn.execute("SELECT * FROM classes ORDER BY name")
        return [dict(r) for r in rows]

    # ---------------- ученики ----------------
    @staticmethod
    def _clean_name(full_name: str) -> str:
        full_name = " ".join(full_name.split())
        if len(full_name) < 3:
            raise ValidationError("Введите ФИО ученика")
        return full_name

    def add_student(self, full_name: str, class_id: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO students(full_name, class_id) VALUES (?, ?)",
            (self._clean_name(full_name), class_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_student(self, student_id: int, full_name: str, class_id: int):
        """Изменение ФИО и/или перевод в другой класс (оценки и посещаемость сохраняются)."""
        try:
            self.conn.execute(
                "UPDATE students SET full_name = ?, class_id = ? WHERE id = ?",
                (self._clean_name(full_name), class_id, student_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Выбранный класс не найден") from exc
        self.conn.commit()

    def get_student(self, student_id: int):
        row = self.conn.execute(
            """SELECT s.id, s.full_name, s.class_id, c.name AS class_name
               FROM students s JOIN classes c ON c.id = s.class_id WHERE s.id = ?""",
            (student_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_students(self, class_id: int | None = None):
        if class_id is None:
            rows = self.conn.execute("SELECT * FROM students ORDER BY full_name")
        else:
            rows = self.conn.execute(
                "SELECT * FROM students WHERE class_id = ? ORDER BY full_name", (class_id,)
            )
        return [dict(r) for r in rows]

    def search_students(self, query: str, user: dict | None = None):
        """Поиск по ФИО сразу во всех доступных классах (без учёта регистра)."""
        q = " ".join(query.split()).casefold()
        found = []
        for c in self.list_classes(user):
            for s in self.list_students(c["id"]):
                if q in s["full_name"].casefold():
                    found.append({**s, "class_name": c["name"]})
        return found

    def delete_student(self, student_id: int):
        self.conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        self.conn.commit()

    # ---------------- предметы ----------------
    def list_subjects(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM subjects ORDER BY name")]

    def add_subject(self, name: str) -> int:
        name = " ".join(name.split())
        if not name:
            raise ValidationError("Название предмета не может быть пустым")
        try:
            cur = self.conn.execute("INSERT INTO subjects(name) VALUES (?)", (name,))
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Такой предмет уже есть") from exc
        self.conn.commit()
        return cur.lastrowid

    def delete_subject(self, subject_id: int):
        used = self.conn.execute(
            "SELECT COUNT(*) FROM grades WHERE subject_id = ?", (subject_id,)
        ).fetchone()[0]
        if used:
            raise ValidationError(f"По этому предмету уже есть оценки ({used}) — удалить нельзя")
        self.conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        self.conn.commit()

    # ---------------- оценки ----------------
    def add_grade(self, student_id: int, subject_id: int, value: int, grade_date: str | None = None) -> int:
        if not isinstance(value, int) or not 1 <= value <= 10:
            raise ValidationError("Оценка должна быть от 1 до 10")
        cur = self.conn.execute(
            "INSERT INTO grades(student_id, subject_id, value, grade_date) VALUES (?, ?, ?, ?)",
            (student_id, subject_id, value, parse_date(grade_date) if grade_date else date.today().isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_grade(self, grade_id: int):
        self.conn.execute("DELETE FROM grades WHERE id = ?", (grade_id,))
        self.conn.commit()

    def list_grades(self, student_id: int, grade_date: str | None = None):
        """Оценки ученика; если указана дата — только за этот день."""
        sql = """SELECT g.id, s.name AS subject, g.value, g.grade_date
                 FROM grades g JOIN subjects s ON s.id = g.subject_id
                 WHERE g.student_id = ?"""
        params: list = [student_id]
        if grade_date:
            sql += " AND g.grade_date = ?"
            params.append(parse_date(grade_date))
        rows = self.conn.execute(sql + " ORDER BY g.grade_date DESC, g.id DESC", params)
        return [dict(r) for r in rows]

    def average(self, student_id: int) -> float | None:
        row = self.conn.execute(
            "SELECT AVG(value) AS avg FROM grades WHERE student_id = ?", (student_id,)
        ).fetchone()
        return round(row["avg"], 2) if row["avg"] is not None else None

    def subject_averages(self, student_id: int):
        rows = self.conn.execute(
            """SELECT s.name AS subject, ROUND(AVG(g.value), 2) AS average
               FROM grades g JOIN subjects s ON s.id = g.subject_id
               WHERE g.student_id = ? GROUP BY s.id ORDER BY s.name""",
            (student_id,),
        )
        return [dict(r) for r in rows]

    # ---------------- четверти и итоги ----------------
    def quarter_table(self, student_id: int):
        """Оценки ученика по предметам: за каждую четверть и итог за год.

        Оценка за четверть — среднее оценок этой четверти, округлённое до целого (7,5 → 8).
        Итог за год — среднее четвертных оценок. complete=False, если оценки есть не за все 4 четверти.
        """
        rows = self.conn.execute(
            """SELECT sub.name AS subject, g.value, g.grade_date
               FROM grades g JOIN subjects sub ON sub.id = g.subject_id
               WHERE g.student_id = ?""",
            (student_id,),
        )
        by_subject: dict[str, dict[int, list[int]]] = {}
        for r in rows:
            q = quarter_for(date.fromisoformat(r["grade_date"]))
            if q is not None:
                by_subject.setdefault(r["subject"], {1: [], 2: [], 3: [], 4: []})[q].append(r["value"])
        table = []
        for subject in sorted(by_subject):
            row = {"subject": subject}
            for q, values in by_subject[subject].items():
                row[f"q{q}"] = round_half_up(sum(values), len(values)) if values else None
            got = [row[f"q{q}"] for q in (1, 2, 3, 4) if row[f"q{q}"] is not None]
            row["year"] = round_half_up(sum(got), len(got)) if got else None
            row["complete"] = len(got) == 4
            table.append(row)
        return table

    @staticmethod
    def _mean(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 2) if values else None

    def quarter_summary(self, table):
        """Средний балл по всем предметам за каждую четверть и за год."""
        return {k: self._mean([r[k] for r in table]) for k in ("q1", "q2", "q3", "q4", "year")}

    def class_quarter_results(self, class_id: int):
        results = []
        for s in self.list_students(class_id):
            summary = self.quarter_summary(self.quarter_table(s["id"]))
            results.append({"student_id": s["id"], "full_name": s["full_name"], **summary})
        return results

    # ---------------- посещаемость ----------------
    def set_attendance(self, student_id: int, att_date: str, present: bool):
        self.conn.execute(
            """INSERT INTO attendance(student_id, att_date, present) VALUES (?, ?, ?)
               ON CONFLICT(student_id, att_date) DO UPDATE SET present = excluded.present""",
            (student_id, parse_date(att_date), int(bool(present))),
        )
        self.conn.commit()

    def attendance_for_date(self, class_id: int, att_date: str) -> dict[int, bool]:
        rows = self.conn.execute(
            """SELECT a.student_id, a.present FROM attendance a
               JOIN students s ON s.id = a.student_id
               WHERE s.class_id = ? AND a.att_date = ?""",
            (class_id, parse_date(att_date)),
        )
        return {r["student_id"]: bool(r["present"]) for r in rows}

    def absences(self, student_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE student_id = ? AND present = 0", (student_id,)
        ).fetchone()[0]

    # ---------------- отчёты ----------------
    def class_report(self, class_id: int):
        """Рейтинг класса по среднему баллу (одинаковые баллы — одинаковое место)."""
        rows = [
            {
                "student_id": s["id"],
                "full_name": s["full_name"],
                "average": self.average(s["id"]),
                "absences": self.absences(s["id"]),
            }
            for s in self.list_students(class_id)
        ]
        rows.sort(key=lambda r: (r["average"] is None, -(r["average"] or 0), r["full_name"]))
        place, prev = 0, None
        for i, r in enumerate(rows, 1):
            if r["average"] is None:
                r["place"] = None
            else:
                if r["average"] != prev:
                    place, prev = i, r["average"]
                r["place"] = place
        return rows

    def class_subject_averages(self, class_id: int):
        rows = self.conn.execute(
            """SELECT sub.name AS subject, ROUND(AVG(g.value), 2) AS average
               FROM grades g
               JOIN students st ON st.id = g.student_id
               JOIN subjects sub ON sub.id = g.subject_id
               WHERE st.class_id = ? GROUP BY sub.id ORDER BY sub.name""",
            (class_id,),
        )
        return [dict(r) for r in rows]
