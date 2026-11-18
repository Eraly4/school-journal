import json
import os
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from journal.api import make_server
from journal.db import Database


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        path = os.path.join(cls.tmp, "t.db")
        db = Database(path)
        cid = db.add_class("10Б")
        sid = db.add_student("Асанов Асан", cid)
        db.add_grade(sid, db.list_subjects()[0]["id"], 5)
        db.close()
        cls.server = make_server(path, port=0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urlopen(self.base + path) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_classes(self):
        self.assertEqual(self.get("/api/classes")[0]["name"], "10Б")

    def test_report(self):
        self.assertEqual(self.get("/api/report/1")[0]["average"], 5.0)

    def test_grades(self):
        self.assertEqual(self.get("/api/students/1/grades")["average"], 5.0)

    def test_not_found(self):
        with self.assertRaises(HTTPError) as ctx:
            self.get("/api/unknown")
        self.assertEqual(ctx.exception.code, 404)
