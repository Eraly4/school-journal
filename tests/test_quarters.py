import csv
import os
import tempfile
import unittest
from datetime import date

from journal.db import Database, ValidationError
from journal.export import export_quarters_csv
from journal.quarters import quarter_for, round_half_up


class QuarterDatesTests(unittest.TestCase):
    def test_quarter_boundaries(self):
        cases = {
            date(2026, 9, 1): 1, date(2026, 10, 25): 1,
            date(2026, 10, 26): None, date(2026, 11, 1): None,      # осенние каникулы
            date(2026, 11, 2): 2, date(2026, 12, 25): 2,
            date(2026, 12, 28): None, date(2027, 1, 10): None,      # зимние каникулы
            date(2027, 1, 11): 3, date(2027, 3, 21): 3,
            date(2027, 3, 22): None, date(2027, 3, 28): None,       # весенние каникулы
            date(2027, 3, 29): 4, date(2027, 5, 25): 4,
            date(2027, 5, 26): None, date(2026, 8, 31): None,
        }
        for d, expected in cases.items():
            self.assertEqual(quarter_for(d), expected, d)

    def test_round_half_up(self):
        self.assertEqual(round_half_up(15, 2), 8)   # 7,5 → 8
        self.assertEqual(round_half_up(13, 2), 7)   # 6,5 → 7 (не «банковское» 6)
        self.assertEqual(round_half_up(22, 3), 7)   # 7,33 → 7
        self.assertEqual(round_half_up(23, 3), 8)   # 7,67 → 8


class QuarterGradesTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        cid = self.db.add_class("9А")
        self.cid = cid
        self.s1 = self.db.add_student("Иванов Иван", cid)
        self.s2 = self.db.add_student("Петрова Анна", cid)
        subs = {s["name"]: s["id"] for s in self.db.list_subjects()}
        self.math, self.phys = subs["Математика"], subs["Физика"]

    def test_quarter_grade_is_rounded_average(self):
        self.db.add_grade(self.s1, self.math, 7, "2026-11-03")
        self.db.add_grade(self.s1, self.math, 8, "2026-11-10")
        row = self.db.quarter_table(self.s1)[0]
        self.assertEqual((row["q2"], row["q1"]), (8, None))

    def test_year_grade_is_average_of_quarters(self):
        for d, v in (("2026-09-10", 10), ("2026-11-10", 8), ("2027-02-01", 8), ("2027-04-10", 10)):
            self.db.add_grade(self.s1, self.math, v, d)
        row = self.db.quarter_table(self.s1)[0]
        self.assertEqual([row["q1"], row["q2"], row["q3"], row["q4"]], [10, 8, 8, 10])
        self.assertEqual(row["year"], 9)
        self.assertTrue(row["complete"])

    def test_incomplete_year_is_marked(self):
        self.db.add_grade(self.s1, self.math, 9, "2026-09-10")
        row = self.db.quarter_table(self.s1)[0]
        self.assertEqual(row["year"], 9)
        self.assertFalse(row["complete"])

    def test_grades_on_holidays_are_ignored(self):
        self.db.add_grade(self.s1, self.math, 5, "2026-10-28")  # каникулы
        self.assertEqual(self.db.quarter_table(self.s1), [])

    def test_summary_and_class_results(self):
        self.db.add_grade(self.s1, self.math, 10, "2026-09-10")
        self.db.add_grade(self.s1, self.phys, 8, "2026-09-12")
        summary = self.db.quarter_summary(self.db.quarter_table(self.s1))
        self.assertEqual(summary["q1"], 9.0)
        results = {r["full_name"]: r for r in self.db.class_quarter_results(self.cid)}
        self.assertEqual(results["Иванов Иван"]["q1"], 9.0)
        self.assertIsNone(results["Петрова Анна"]["q1"])

    def test_add_grade_date_validation_and_formats(self):
        with self.assertRaises(ValidationError):
            self.db.add_grade(self.s1, self.math, 5, "вчера")
        self.db.add_grade(self.s1, self.math, 5, "15.10.2026")
        self.assertEqual(self.db.list_grades(self.s1)[0]["grade_date"], "2026-10-15")

    def test_export_quarters_csv(self):
        self.db.add_grade(self.s1, self.math, 9, "2026-09-10")
        path = os.path.join(tempfile.mkdtemp(), "q.csv")
        export_quarters_csv(self.db.class_quarter_results(self.cid), path)
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0][:2], ["ФИО", "1 четверть"])
        self.assertEqual(rows[1], ["Иванов Иван", "9,0", "", "", "", "9,0"])
