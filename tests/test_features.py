import csv
import os
import tempfile
import unittest

from journal.db import Database, ValidationError, parse_date
from journal.export import export_report_csv


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.c9 = self.db.add_class("9А")
        self.c10 = self.db.add_class("10Б")
        self.s1 = self.db.add_student("Иванов Иван", self.c9)
        self.s2 = self.db.add_student("Петрова Анна", self.c9)
        self.s3 = self.db.add_student("Иванова Мария", self.c10)
        self.math, self.phys = [s["id"] for s in self.db.list_subjects()
                                if s["name"] in ("Математика", "Физика")]

    # --- пароли и роли ---
    def test_change_password(self):
        admin = self.db.authenticate("admin", "admin123")
        self.db.change_password(admin["id"], "admin123", "newpass1")
        self.assertIsNone(self.db.authenticate("admin", "admin123"))
        self.assertIsNotNone(self.db.authenticate("admin", "newpass1"))

    def test_change_password_wrong_old_or_short_new(self):
        admin = self.db.authenticate("admin", "admin123")
        with self.assertRaises(ValidationError):
            self.db.change_password(admin["id"], "wrong", "newpass1")
        with self.assertRaises(ValidationError):
            self.db.change_password(admin["id"], "admin123", "123")

    def test_teacher_sees_only_assigned_classes(self):
        tid = self.db.add_user("teacher1", "secret1", "teacher")
        teacher = self.db.authenticate("teacher1", "secret1")
        self.assertEqual(self.db.list_classes(teacher), [])
        self.db.set_user_classes(tid, [self.c9])
        self.assertEqual([c["name"] for c in self.db.list_classes(teacher)], ["9А"])
        self.assertEqual(len(self.db.list_classes()), 2)  # администратор видит все

    def test_class_created_by_teacher_is_assigned_to_him(self):
        self.db.add_user("teacher1", "secret1", "teacher")
        teacher = self.db.authenticate("teacher1", "secret1")
        self.db.add_class("5В", teacher)
        self.assertEqual([c["name"] for c in self.db.list_classes(teacher)], ["5В"])

    def test_cannot_delete_self_or_last_admin(self):
        admin = self.db.authenticate("admin", "admin123")
        with self.assertRaises(ValidationError):
            self.db.delete_user(admin["id"], admin["id"])
        with self.assertRaises(ValidationError):
            self.db.delete_user(admin["id"], None)

    def test_delete_teacher(self):
        tid = self.db.add_user("teacher1", "secret1")
        self.db.delete_user(tid)
        self.assertIsNone(self.db.authenticate("teacher1", "secret1"))

    # --- поиск и редактирование ---
    def test_search_across_classes_case_insensitive(self):
        found = self.db.search_students("иванов")
        self.assertEqual({s["full_name"] for s in found}, {"Иванов Иван", "Иванова Мария"})
        self.assertEqual({s["class_name"] for s in found}, {"9А", "10Б"})

    def test_search_respects_teacher_classes(self):
        tid = self.db.add_user("teacher1", "secret1")
        self.db.set_user_classes(tid, [self.c9])
        teacher = self.db.authenticate("teacher1", "secret1")
        self.assertEqual([s["full_name"] for s in self.db.search_students("иванов", teacher)], ["Иванов Иван"])

    def test_update_and_transfer_student(self):
        self.db.add_grade(self.s1, self.math, 8)
        self.db.update_student(self.s1, "Иванов Иван Иванович", self.c10)
        st = self.db.get_student(self.s1)
        self.assertEqual((st["full_name"], st["class_name"]), ("Иванов Иван Иванович", "10Б"))
        self.assertEqual(self.db.average(self.s1), 8.0)  # оценки сохранились

    def test_update_student_validation(self):
        with self.assertRaises(ValidationError):
            self.db.update_student(self.s1, " ", self.c9)

    def test_list_grades_for_single_day(self):
        self.db.add_grade(self.s1, self.math, 7, "2026-11-02")
        self.db.add_grade(self.s1, self.math, 9, "2026-11-03")
        self.assertEqual([g["value"] for g in self.db.list_grades(self.s1, "2026-11-02")], [7])
        self.assertEqual([g["value"] for g in self.db.list_grades(self.s1, "03.11.2026")], [9])
        self.assertEqual(self.db.list_grades(self.s1, "2026-11-04"), [])
        self.assertEqual(len(self.db.list_grades(self.s1)), 2)

    # --- предметы ---
    def test_add_and_delete_subject(self):
        sid = self.db.add_subject("Химия")
        self.db.delete_subject(sid)
        self.assertNotIn("Химия", [s["name"] for s in self.db.list_subjects()])

    def test_duplicate_or_empty_subject(self):
        with self.assertRaises(ValidationError):
            self.db.add_subject("Математика")
        with self.assertRaises(ValidationError):
            self.db.add_subject("  ")

    def test_cannot_delete_subject_with_grades(self):
        self.db.add_grade(self.s1, self.math, 7)
        with self.assertRaises(ValidationError):
            self.db.delete_subject(self.math)

    # --- посещаемость ---
    def test_attendance_and_absences(self):
        self.db.set_attendance(self.s1, "2026-11-02", False)
        self.db.set_attendance(self.s1, "03.11.2026", False)
        self.db.set_attendance(self.s2, "2026-11-02", True)
        self.assertEqual(self.db.absences(self.s1), 2)
        marks = self.db.attendance_for_date(self.c9, "2026-11-02")
        self.assertEqual(marks, {self.s1: False, self.s2: True})

    def test_attendance_can_be_corrected(self):
        self.db.set_attendance(self.s1, "2026-11-02", False)
        self.db.set_attendance(self.s1, "2026-11-02", True)
        self.assertEqual(self.db.absences(self.s1), 0)

    def test_parse_date(self):
        self.assertEqual(parse_date("06.11.2026"), "2026-11-06")
        with self.assertRaises(ValidationError):
            parse_date("вчера")

    # --- отчёты ---
    def test_subject_averages(self):
        self.db.add_grade(self.s1, self.math, 10)
        self.db.add_grade(self.s1, self.math, 8)
        self.db.add_grade(self.s1, self.phys, 6)
        avg = {r["subject"]: r["average"] for r in self.db.subject_averages(self.s1)}
        self.assertEqual(avg, {"Математика": 9.0, "Физика": 6.0})

    def test_class_report_ranking_with_ties(self):
        s3 = self.db.add_student("Сидоров Пётр", self.c9)
        self.db.add_grade(self.s1, self.math, 9)
        self.db.add_grade(self.s2, self.math, 9)
        self.db.add_grade(s3, self.math, 5)
        report = self.db.class_report(self.c9)
        self.assertEqual([r["place"] for r in report], [1, 1, 3])
        self.assertEqual(report[-1]["full_name"], "Сидоров Пётр")

    def test_class_report_students_without_grades_last(self):
        self.db.add_grade(self.s2, self.math, 4)
        report = self.db.class_report(self.c9)
        self.assertEqual(report[0]["full_name"], "Петрова Анна")
        self.assertIsNone(report[1]["place"])

    def test_class_subject_averages(self):
        self.db.add_grade(self.s1, self.math, 10)
        self.db.add_grade(self.s2, self.math, 6)
        self.assertEqual(self.db.class_subject_averages(self.c9), [{"subject": "Математика", "average": 8.0}])

    def test_export_csv(self):
        self.db.add_grade(self.s1, self.math, 9)
        self.db.set_attendance(self.s1, "2026-11-02", False)
        path = os.path.join(tempfile.mkdtemp(), "r.csv")
        export_report_csv(self.db.class_report(self.c9), path)
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0], ["Место", "ФИО", "Средний балл", "Пропусков"])
        self.assertEqual(rows[1], ["1", "Иванов Иван", "9,0", "1"])
