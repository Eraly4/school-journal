"""Экспорт отчёта в CSV (открывается в Excel)."""
import csv


def export_report_csv(rows, path: str):
    """Разделитель «;» и запятая в числах — так Excel с русской локалью открывает файл корректно."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Место", "ФИО", "Средний балл", "Пропусков"])
        for r in rows:
            avg = "" if r["average"] is None else str(r["average"]).replace(".", ",")
            writer.writerow([r["place"] or "", r["full_name"], avg, r["absences"]])


def export_quarters_csv(rows, path: str):
    """Итоги класса по четвертям и за год."""
    def fmt(v):
        return "" if v is None else str(v).replace(".", ",")

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ФИО", "1 четверть", "2 четверть", "3 четверть", "4 четверть", "Год"])
        for r in rows:
            writer.writerow([r["full_name"], *(fmt(r[k]) for k in ("q1", "q2", "q3", "q4", "year"))])
