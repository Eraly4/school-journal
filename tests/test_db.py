import os
import sqlite3
import tempfile
import unittest

from journal.db import Database, ValidationError


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.cid = self.db.add_class("9А")
        self.sid = self.db.add_student("Иванов Иван", self.cid)
        self.subj = self.db.list_subjects()[0]["id"]

    def test_default_admin_login(self):
        self.assertIsNotNone(self.db.authenticate("admin", "admin123"))
        self.assertIsNone(self.db.authenticate("admin", "bad"))

    def test_short_password_rejected(self):
        with self.assertRaises(ValidationError):
            self.db.add_user("teacher1", "123")

    def test_duplicate_class(self):
        with self.assertRaises(ValidationError):
            self.db.add_class("9А")

    def test_student_name_validation(self):
        with self.assertRaises(ValidationError):
            self.db.add_student("  ", self.cid)

    def test_grade_range(self):
        with self.assertRaises(ValidationError):
            self.db.add_grade(self.sid, self.subj, 11)

    def test_average(self):
        self.db.add_grade(self.sid, self.subj, 5)
        self.db.add_grade(self.sid, self.subj, 4)
        self.assertEqual(self.db.average(self.sid), 4.5)

    def test_average_without_grades(self):
        self.assertIsNone(self.db.average(self.sid))

    def test_delete_student_removes_grades(self):
        self.db.add_grade(self.sid, self.subj, 5)
        self.db.delete_student(self.sid)
        self.assertEqual(self.db.list_grades(self.sid), [])

    def test_class_report(self):
        self.db.add_grade(self.sid, self.subj, 3)
        report = self.db.class_report(self.cid)
        self.assertEqual(report[0]["average"], 3.0)

    def test_grade_ten_allowed(self):
        self.db.add_grade(self.sid, self.subj, 10)
        self.assertEqual(self.db.average(self.sid), 10.0)

    def test_grade_zero_rejected(self):
        with self.assertRaises(ValidationError):
            self.db.add_grade(self.sid, self.subj, 0)

    def test_delete_class_removes_students_and_grades(self):
        self.db.add_grade(self.sid, self.subj, 7)
        self.db.delete_class(self.cid)
        self.assertEqual(self.db.list_classes(), [])
        self.assertEqual(self.db.list_students(), [])
        self.assertEqual(self.db.list_grades(self.sid), [])

    def test_delete_grade(self):
        gid = self.db.add_grade(self.sid, self.subj, 3)
        self.db.add_grade(self.sid, self.subj, 9)
        self.db.delete_grade(gid)
        self.assertEqual([g["value"] for g in self.db.list_grades(self.sid)], [9])
        self.assertEqual(self.db.average(self.sid), 9.0)


class MigrationTests(unittest.TestCase):
    def test_old_database_with_five_point_scale_is_upgraded(self):
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE classes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
            CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
                class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE);
            CREATE TABLE subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
            CREATE TABLE grades (id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject_id INTEGER NOT NULL REFERENCES subjects(id),
                value INTEGER NOT NULL CHECK (value BETWEEN 1 AND 5), grade_date TEXT NOT NULL);
            INSERT INTO classes(name) VALUES ('9А');
            INSERT INTO students(full_name, class_id) VALUES ('Иванов Иван', 1);
            INSERT INTO subjects(name) VALUES ('Математика');
            INSERT INTO grades(student_id, subject_id, value, grade_date) VALUES (1, 1, 5, '2026-11-01');
        """)
        conn.commit()
        conn.close()
        db = Database(path)
        self.assertEqual(db.average(1), 5.0)      # старая оценка сохранилась
        db.add_grade(1, 1, 9)                      # новая шкала работает
        self.assertEqual(db.average(1), 7.0)
        db.close()
