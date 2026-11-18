"""Пример клиента: получает данные с API по HTTP и разбирает JSON."""
import json
from urllib.request import urlopen


def fetch(base_url: str, path: str):
    with urlopen(f"{base_url}{path}", timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    for c in fetch("http://127.0.0.1:8000", "/api/classes"):
        print(c["id"], c["name"])
