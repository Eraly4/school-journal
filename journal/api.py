"""HTTP API (JSON) для обмена данными с внешними сервисами.

GET /api/classes
GET /api/students?class_id=1
GET /api/students/<id>/grades
GET /api/report/<class_id>
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .db import Database


def make_server(db_path: str, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            query = parse_qs(url.query)
            db = Database(db_path)
            try:
                if parts == ["api", "classes"]:
                    self._send(200, db.list_classes())
                elif parts == ["api", "students"]:
                    class_id = int(query["class_id"][0]) if "class_id" in query else None
                    self._send(200, db.list_students(class_id))
                elif len(parts) == 4 and parts[:2] == ["api", "students"] and parts[3] == "grades":
                    sid = int(parts[2])
                    self._send(200, {"grades": db.list_grades(sid), "average": db.average(sid)})
                elif len(parts) == 3 and parts[:2] == ["api", "report"]:
                    self._send(200, db.class_report(int(parts[2])))
                else:
                    self._send(404, {"error": "Не найдено"})
            except ValueError:
                self._send(400, {"error": "Некорректный параметр"})
            finally:
                db.close()

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    # Отдельный запуск API:  python -m journal.api
    server = make_server("school.db")
    print("API запущен: http://127.0.0.1:8000/api/classes  (Ctrl+C — остановить)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
