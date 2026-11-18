"""Графический интерфейс (Tkinter)."""
import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, simpledialog, ttk

from .api import make_server
from .db import Database, ValidationError, parse_date
from .export import export_quarters_csv, export_report_csv
from .quarters import SCHOOL_YEAR, quarter_for, schedule_text
from .security import verify_password
from .theme import apply_theme
from .widgets import DatePicker, StripedTree

ROLE_NAMES = {"admin": "Администратор", "teacher": "Учитель"}


def make_tree(parent, columns, headings, widths, height=12, selectmode="browse"):
    tv = StripedTree(parent, columns=columns, show="headings", height=height, selectmode=selectmode)
    for col, title, width in zip(columns, headings, widths):
        tv.heading(col, text=title)
        tv.column(col, width=width)
    return tv


class App(tk.Tk):
    def __init__(self, db_path: str = "school.db"):
        super().__init__()
        apply_theme(self)
        self.title("Электронный журнал школы")
        self.geometry("1000x720")
        self.minsize(900, 580)
        self.db_path = db_path
        self.db = Database(db_path)
        self.user = None
        self.api_server = None
        self.class_map: dict[str, int] = {}
        self.student_map: dict[str, int] = {}
        self.subject_map: dict[str, int] = {}
        self.show_login()

    @property
    def is_admin(self) -> bool:
        return bool(self.user and self.user["role"] == "admin")

    def clear(self):
        for w in self.winfo_children():
            w.destroy()

    # ================= вход =================
    def show_login(self):
        self.clear()
        self.user = None
        frame = ttk.Frame(self, style="Card.TFrame", padding=(40, 30))
        frame.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(frame, text="Электронный журнал", style="Title.TLabel").grid(columnspan=2)
        ttk.Label(frame, text="Войдите, чтобы продолжить", style="Subtitle.TLabel").grid(
            columnspan=2, pady=(2, 18))
        ttk.Label(frame, text="Логин", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 2))
        self.e_login = ttk.Entry(frame, width=30)
        self.e_login.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(frame, text="Пароль", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 2))
        self.e_pass = ttk.Entry(frame, width=30, show="*")
        self.e_pass.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        ttk.Button(frame, text="Войти", style="Accent.TButton", command=self.login).grid(
            row=6, columnspan=2, sticky="ew")
        self.bind("<Return>", lambda e: self.login())
        self.e_login.focus()

    def login(self):
        user = self.db.authenticate(self.e_login.get(), self.e_pass.get())
        if not user:
            messagebox.showerror("Ошибка", "Неверный логин или пароль")
            return
        self.user = user
        self.unbind("<Return>")
        self.show_main()
        if self.is_admin and verify_password("admin123", user["password_hash"]):
            messagebox.showwarning(
                "Безопасность", "Используется стандартный пароль. Смените его кнопкой «Сменить пароль»."
            )

    def change_password(self):
        old = simpledialog.askstring("Смена пароля", "Текущий пароль:", show="*", parent=self)
        if old is None:
            return
        new = simpledialog.askstring("Смена пароля", "Новый пароль (минимум 6 символов):", show="*", parent=self)
        if new is None:
            return
        again = simpledialog.askstring("Смена пароля", "Повторите новый пароль:", show="*", parent=self)
        if new != again:
            messagebox.showerror("Ошибка", "Пароли не совпадают")
            return
        try:
            self.db.change_password(self.user["id"], old, new)
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        messagebox.showinfo("Готово", "Пароль изменён")

    # ================= главное окно =================
    def show_main(self):
        self.clear()
        top = ttk.Frame(self, style="Top.TFrame", padding=(14, 10))
        top.pack(fill="x")
        ttk.Label(top, text="Электронный журнал", style="Top.TLabel").pack(side="left")
        ttk.Label(top, text=f"   {self.user['username']} · {ROLE_NAMES[self.user['role']]}",
                  style="Top.TLabel").pack(side="left")
        ttk.Button(top, text="Выйти", style="Light.TButton", command=self.show_login).pack(side="right")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=10)
        self._tab_students()
        self.tab_grades = self._tab_grades()
        self._tab_results()
        self._tab_attendance()
        self._tab_report()
        self._tab_search()
        self._tab_subjects()
        if self.is_admin:
            self._tab_users()
        else:
            self._tab_profile()
        self.refresh_subjects()
        self.refresh_classes()

    def start_api(self):
        if self.api_server:
            messagebox.showinfo("API", "API уже запущен: http://127.0.0.1:8000/api/classes")
            return
        try:
            self.api_server = make_server(self.db_path)
        except OSError:
            messagebox.showinfo("API", "Порт 8000 занят")
            return
        threading.Thread(target=self.api_server.serve_forever, daemon=True).start()
        messagebox.showinfo("API", "API запущен: http://127.0.0.1:8000/api/classes")

    def _new_tab(self, title):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text=title)
        return tab

    def _class_row(self, tab, callback):
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="Класс:").pack(side="left")
        cb = ttk.Combobox(row, state="readonly", width=12)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: callback())
        return row, cb

    def _class_id(self, cb):
        return self.class_map.get(cb.get())

    def refresh_classes(self):
        self.class_map = {c["name"]: c["id"] for c in self.db.list_classes(self.user)}
        names = list(self.class_map)
        for cb in (self.cb_class_st, self.cb_class_gr, self.cb_class_rs, self.cb_class_at, self.cb_class_rp):
            cb["values"] = names
            if cb.get() not in names:
                cb.set(names[0] if names else "")
        self.load_students()
        self.load_grade_students()
        self.load_attendance()
        self.load_report()
        self.load_results()
        self.do_search()
        if self.is_admin:
            self.load_users()

    # ================= вкладка «Ученики» =================
    def _tab_students(self):
        tab = self._new_tab("Ученики")
        row, self.cb_class_st = self._class_row(tab, self.load_students)
        ttk.Button(row, text="Добавить класс", style="Accent.TButton", command=self.add_class).pack(side="left")
        ttk.Button(row, text="Удалить класс", style="Danger.TButton", command=self.delete_class).pack(side="left", padx=6)
        self.tv_students = make_tree(tab, ("id", "name"), ("№", "ФИО"), (60, 600), height=14)
        self.tv_students.pack(fill="both", expand=True, pady=6)
        row2 = ttk.Frame(tab)
        row2.pack(fill="x")
        self.e_student = ttk.Entry(row2, width=36)
        self.e_student.pack(side="left")
        ttk.Button(row2, text="Добавить ученика", style="Accent.TButton", command=self.add_student).pack(side="left", padx=6)
        ttk.Button(row2, text="Изменить / перевести", style="Accent.TButton", command=self.edit_student).pack(side="left")
        ttk.Button(row2, text="Удалить", style="Danger.TButton", command=self.delete_student).pack(side="left", padx=6)

    def add_class(self):
        name = simpledialog.askstring("Новый класс", "Название класса (например, 9А):", parent=self)
        if name is None:
            return
        try:
            self.db.add_class(name, self.user)
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        self.cb_class_st.set(name.strip())
        self.refresh_classes()

    def delete_class(self):
        cid = self._class_id(self.cb_class_st)
        if not cid:
            messagebox.showwarning("Внимание", "Нет выбранного класса")
            return
        count = len(self.db.list_students(cid))
        name = self.cb_class_st.get()
        if messagebox.askyesno(
            "Удаление класса",
            f"Удалить класс {name}? Будут также удалены ученики ({count}) и все их оценки.",
        ):
            self.db.delete_class(cid)
            self.refresh_classes()

    def load_students(self):
        self.tv_students.delete(*self.tv_students.get_children())
        cid = self._class_id(self.cb_class_st)
        if cid:
            for s in self.db.list_students(cid):
                self.tv_students.insert("", "end", values=(s["id"], s["full_name"]))

    def add_student(self):
        cid = self._class_id(self.cb_class_st)
        if not cid:
            messagebox.showwarning("Внимание", "Сначала добавьте класс")
            return
        try:
            self.db.add_student(self.e_student.get(), cid)
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        self.e_student.delete(0, "end")
        self.refresh_classes()

    def _selected_student_id(self):
        sel = self.tv_students.selection()
        return int(self.tv_students.item(sel[0])["values"][0]) if sel else None

    def delete_student(self):
        sid = self._selected_student_id()
        if sid and messagebox.askyesno("Удаление", "Удалить ученика вместе с оценками?"):
            self.db.delete_student(sid)
            self.refresh_classes()

    def edit_student(self):
        sid = self._selected_student_id()
        if not sid:
            messagebox.showwarning("Внимание", "Выберите ученика в списке")
            return
        st = self.db.get_student(sid)
        win = tk.Toplevel(self)
        win.title("Изменение ученика")
        win.grab_set()
        frame = ttk.Frame(win, padding=14)
        frame.pack()
        ttk.Label(frame, text="ФИО:").grid(row=0, column=0, sticky="e", pady=4)
        e = ttk.Entry(frame, width=36)
        e.insert(0, st["full_name"])
        e.grid(row=0, column=1, padx=6)
        ttk.Label(frame, text="Класс:").grid(row=1, column=0, sticky="e", pady=4)
        cb = ttk.Combobox(frame, state="readonly", values=list(self.class_map), width=12)
        cb.set(st["class_name"])
        cb.grid(row=1, column=1, sticky="w", padx=6)

        def save():
            try:
                self.db.update_student(sid, e.get(), self.class_map[cb.get()])
            except (ValidationError, KeyError) as err:
                messagebox.showerror("Ошибка", str(err), parent=win)
                return
            win.destroy()
            self.refresh_classes()

        ttk.Button(frame, text="Сохранить", style="Accent.TButton", command=save).grid(columnspan=2, pady=8)

    # ================= вкладка «Оценки» (карточка ученика) =================
    def _tab_grades(self):
        tab = self._new_tab("Оценки")
        row, self.cb_class_gr = self._class_row(tab, self.load_grade_students)
        ttk.Label(row, text="Ученик:").pack(side="left")
        self.cb_student_gr = ttk.Combobox(row, state="readonly", width=30)
        self.cb_student_gr.pack(side="left", padx=4)
        self.cb_student_gr.bind("<<ComboboxSelected>>", lambda e: self.load_grades())
        row2 = ttk.Frame(tab)
        row2.pack(fill="x", pady=6)
        ttk.Label(row2, text="Предмет:").pack(side="left")
        self.cb_subject = ttk.Combobox(row2, state="readonly", width=18)
        self.cb_subject.pack(side="left", padx=4)
        ttk.Label(row2, text="Оценка (1–10):").pack(side="left")
        self.sp_grade = ttk.Spinbox(row2, from_=1, to=10, width=4)
        self.sp_grade.set(10)
        self.sp_grade.pack(side="left", padx=4)
        row3 = ttk.Frame(tab)
        row3.pack(fill="x", pady=(0, 6))
        ttk.Label(row3, text="Дата:").pack(side="left")
        self.gr_date = DatePicker(row3, command=self.load_grades)
        self.gr_date.pack(side="left", padx=6)
        ttk.Button(row3, text="Поставить оценку", style="Accent.TButton", command=self.add_grade).pack(
            side="left", padx=12)
        self.var_all_dates = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Показать оценки за все дни", variable=self.var_all_dates,
                        command=self.load_grades).pack(side="left")
        self.lbl_avg = ttk.Label(tab, text="Средний балл: —", style="Stat.TLabel")
        self.lbl_avg.pack(anchor="w")
        self.lbl_subj = ttk.Label(tab, text="По предметам: —", wraplength=860, justify="left")
        self.lbl_subj.pack(anchor="w")
        self.lbl_day = ttk.Label(tab, text="", style="Hint.TLabel")
        self.lbl_day.pack(anchor="w", pady=(6, 0))
        self.tv_grades = make_tree(
            tab, ("subject", "value", "date", "quarter"), ("Предмет", "Оценка", "Дата", "Четверть"),
            (300, 90, 130, 130), height=10,
        )
        self.tv_grades.pack(fill="both", expand=True, pady=6)
        ttk.Button(tab, text="Удалить выбранную оценку", style="Danger.TButton", command=self.delete_grade).pack(anchor="w")
        return tab

    def load_grade_students(self):
        cid = self._class_id(self.cb_class_gr)
        students = self.db.list_students(cid) if cid else []
        names = [s["full_name"] for s in students]
        self.student_map = {}
        for s in students:  # одинаковые ФИО различаем по номеру
            label = s["full_name"] if names.count(s["full_name"]) == 1 else f"{s['full_name']} (№{s['id']})"
            self.student_map[label] = s["id"]
        self.cb_student_gr["values"] = list(self.student_map)
        self.cb_student_gr.set(next(iter(self.student_map), ""))
        self.load_grades()

    def load_grades(self):
        self.tv_grades.delete(*self.tv_grades.get_children())
        sid = self.student_map.get(self.cb_student_gr.get())
        if not sid:
            self.lbl_avg.config(text="Средний балл: —")
            self.lbl_subj.config(text="По предметам: —")
            self.lbl_day.config(text="")
            return
        try:
            day = None if self.var_all_dates.get() else parse_date(self.gr_date.get())
        except ValidationError:
            day = None
        self.lbl_day.config(text="Оценки за все дни" if day is None else f"Оценки за {self.gr_date.get()}")
        for g in self.db.list_grades(sid, day):
            d = date.fromisoformat(g["grade_date"])
            q = quarter_for(d)
            self.tv_grades.insert(
                "", "end", iid=str(g["id"]),
                values=(g["subject"], g["value"], d.strftime("%d.%m.%Y"), f"{q} четверть" if q else "—"),
            )
        avg = self.db.average(sid)
        self.lbl_avg.config(text=f"Средний балл: {avg if avg is not None else '—'}")
        parts = [f"{r['subject']}: {r['average']}" for r in self.db.subject_averages(sid)]
        self.lbl_subj.config(text="По предметам: " + ("; ".join(parts) if parts else "—"))

    def add_grade(self):
        sid = self.student_map.get(self.cb_student_gr.get())
        if not sid:
            messagebox.showwarning("Внимание", "Выберите ученика")
            return
        subject_id = self.subject_map.get(self.cb_subject.get())
        if not subject_id:
            messagebox.showwarning("Внимание", "Выберите предмет")
            return
        try:
            grade_date = parse_date(self.gr_date.get())
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        if quarter_for(date.fromisoformat(grade_date)) is None:
            messagebox.showwarning(
                "Нет четверти",
                f"Эта дата не входит ни в одну четверть {SCHOOL_YEAR} (каникулы или вне учебного года). "
                "Выберите другую дату.",
            )
            return
        try:
            self.db.add_grade(sid, subject_id, int(self.sp_grade.get()), grade_date)
        except (ValidationError, ValueError):
            messagebox.showerror("Ошибка", "Оценка должна быть числом от 1 до 10")
            return
        self.load_grades()
        self.load_report()
        self.load_results()

    def delete_grade(self):
        sel = self.tv_grades.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите оценку в списке")
            return
        if messagebox.askyesno("Удаление", "Удалить выбранную оценку?"):
            self.db.delete_grade(int(sel[0]))
            self.load_grades()
            self.load_report()
            self.load_results()

    # ================= вкладка «Итоги» (четверти и год) =================
    def _tab_results(self):
        tab = self._new_tab("Итоги")
        row, self.cb_class_rs = self._class_row(tab, self.load_results)
        ttk.Button(row, text="Экспорт итогов (CSV)", style="Accent.TButton", command=self.export_results).pack(
            side="left")
        ttk.Label(tab, text=f"Учебный год {SCHOOL_YEAR}.  {schedule_text()}", style="Hint.TLabel",
                  wraplength=940, justify="left").pack(anchor="w", pady=(0, 6))
        cols = ("name", "q1", "q2", "q3", "q4", "year")
        widths = (330, 100, 100, 100, 100, 100)
        self.tv_results = make_tree(
            tab, cols, ("ФИО (средний балл по всем предметам)", "1 четверть", "2 четверть", "3 четверть",
                        "4 четверть", "Год"), widths, height=6,
        )
        self.tv_results.pack(fill="both", expand=True)
        self.tv_results.bind("<<TreeviewSelect>>", self.load_student_results)
        self.lbl_res_student = ttk.Label(tab, text="Выберите ученика в таблице выше, чтобы увидеть оценки по предметам",
                                         style="Stat.TLabel")
        self.lbl_res_student.pack(anchor="w", pady=(8, 4))
        self.tv_student_q = make_tree(
            tab, ("subject",) + cols[1:], ("Предмет", "1 четверть", "2 четверть", "3 четверть", "4 четверть",
                                           "Итог за год"), widths, height=6,
        )
        self.tv_student_q.pack(fill="both", expand=True)
        ttk.Label(
            tab, style="Hint.TLabel", wraplength=940, justify="left",
            text="Оценка за четверть — среднее оценок этой четверти, округлённое до целого (6,5 → 7). "
                 "Итог за год — среднее четвертных оценок; «*» — итог предварительный, пока нет оценок за все четыре четверти.",
        ).pack(anchor="w", pady=(6, 0))

    @staticmethod
    def _fmt(value):
        return "—" if value is None else value

    def load_results(self):
        self.tv_results.delete(*self.tv_results.get_children())
        self.tv_student_q.delete(*self.tv_student_q.get_children())
        self.lbl_res_student.config(text="Выберите ученика в таблице выше, чтобы увидеть оценки по предметам")
        cid = self._class_id(self.cb_class_rs)
        if not cid:
            return
        for r in self.db.class_quarter_results(cid):
            self.tv_results.insert("", "end", iid=str(r["student_id"]), values=(
                r["full_name"], *(self._fmt(r[k]) for k in ("q1", "q2", "q3", "q4", "year"))))

    def load_student_results(self, _event=None):
        sel = self.tv_results.selection()
        self.tv_student_q.delete(*self.tv_student_q.get_children())
        if not sel:
            return
        sid = int(sel[0])
        self.lbl_res_student.config(text=f"Оценки по предметам: {self.db.get_student(sid)['full_name']}")
        table = self.db.quarter_table(sid)
        for r in table:
            year = self._fmt(r["year"]) if r["complete"] or r["year"] is None else f"{r['year']} *"
            self.tv_student_q.insert("", "end", values=(
                r["subject"], *(self._fmt(r[k]) for k in ("q1", "q2", "q3", "q4")), year))
        if table:
            avg = self.db.quarter_summary(table)
            self.tv_student_q.insert("", "end", values=(
                "Средний балл", *(self._fmt(avg[k]) for k in ("q1", "q2", "q3", "q4", "year"))))

    def export_results(self):
        cid = self._class_id(self.cb_class_rs)
        if not cid:
            messagebox.showwarning("Внимание", "Нет выбранного класса")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=f"итоги_{self.cb_class_rs.get()}.csv",
            filetypes=[("CSV (открывается в Excel)", "*.csv")],
        )
        if path:
            export_quarters_csv(self.db.class_quarter_results(cid), path)
            messagebox.showinfo("Готово", f"Итоги сохранены:\n{path}")

    # ================= вкладка «Посещаемость» =================
    def _tab_attendance(self):
        tab = self._new_tab("Посещаемость")
        row, self.cb_class_at = self._class_row(tab, self.load_attendance)
        ttk.Label(row, text="Дата:").pack(side="left", padx=(12, 0))
        self.e_date = DatePicker(row, command=self.load_attendance)
        self.e_date.pack(side="left", padx=6)
        self.tv_att = make_tree(
            tab, ("name", "status", "abs"), ("ФИО", "Отметка за дату", "Всего пропусков"),
            (380, 160, 140), height=14, selectmode="extended",
        )
        self.tv_att.pack(fill="both", expand=True, pady=6)
        row2 = ttk.Frame(tab)
        row2.pack(fill="x")
        ttk.Button(row2, text="Присутствовал", style="Accent.TButton", command=lambda: self.mark(True)).pack(side="left")
        ttk.Button(row2, text="Отсутствовал", style="Danger.TButton", command=lambda: self.mark(False)).pack(side="left", padx=6)
        ttk.Button(row2, text="Весь класс присутствовал", style="Accent.TButton", command=self.mark_all).pack(side="left")
        ttk.Label(row2, text="Можно выделить несколько учеников (Ctrl/Shift)", style="Hint.TLabel").pack(side="left", padx=10)

    def load_attendance(self):
        self.tv_att.delete(*self.tv_att.get_children())
        cid = self._class_id(self.cb_class_at)
        if not cid:
            return
        try:
            marks = self.db.attendance_for_date(cid, self.e_date.get())
        except ValidationError:
            return
        names = {True: "присутствовал", False: "отсутствовал"}
        for s in self.db.list_students(cid):
            self.tv_att.insert(
                "", "end", iid=str(s["id"]),
                values=(s["full_name"], names.get(marks.get(s["id"]), "—"), self.db.absences(s["id"])),
            )

    def _valid_date(self):
        try:
            return parse_date(self.e_date.get())
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return None

    def mark(self, present: bool):
        d = self._valid_date()
        sel = self.tv_att.selection()
        if not d:
            return
        if not sel:
            messagebox.showwarning("Внимание", "Выделите учеников в списке")
            return
        for iid in sel:
            self.db.set_attendance(int(iid), d, present)
        self.load_attendance()
        self.load_report()

    def mark_all(self):
        d = self._valid_date()
        if not d:
            return
        for iid in self.tv_att.get_children():
            self.db.set_attendance(int(iid), d, True)
        self.load_attendance()

    # ================= вкладка «Отчёт» =================
    def _tab_report(self):
        tab = self._new_tab("Отчёт по классу")
        row, self.cb_class_rp = self._class_row(tab, self.load_report)
        ttk.Button(row, text="Экспорт в Excel (CSV)", style="Accent.TButton", command=self.export_report).pack(side="left")
        self.tv_report = make_tree(
            tab, ("place", "name", "avg", "abs"), ("Место", "ФИО", "Средний балл", "Пропусков"),
            (70, 400, 120, 110), height=7,
        )
        self.tv_report.pack(fill="both", expand=True, pady=6)
        ttk.Label(tab, text="Средний балл класса по предметам:").pack(anchor="w")
        self.tv_subj_avg = make_tree(tab, ("subject", "avg"), ("Предмет", "Средний балл"), (300, 120), height=6)
        self.tv_subj_avg.pack(fill="x", pady=4)

    def load_report(self):
        self.tv_report.delete(*self.tv_report.get_children())
        self.tv_subj_avg.delete(*self.tv_subj_avg.get_children())
        cid = self._class_id(self.cb_class_rp)
        if not cid:
            return
        for r in self.db.class_report(cid):
            self.tv_report.insert("", "end", values=(
                r["place"] or "—", r["full_name"], r["average"] if r["average"] is not None else "—", r["absences"]))
        for r in self.db.class_subject_averages(cid):
            self.tv_subj_avg.insert("", "end", values=(r["subject"], r["average"]))

    def export_report(self):
        cid = self._class_id(self.cb_class_rp)
        if not cid:
            messagebox.showwarning("Внимание", "Нет выбранного класса")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=f"отчёт_{self.cb_class_rp.get()}.csv",
            filetypes=[("CSV (открывается в Excel)", "*.csv")],
        )
        if path:
            export_report_csv(self.db.class_report(cid), path)
            messagebox.showinfo("Готово", f"Отчёт сохранён:\n{path}")

    # ================= вкладка «Поиск» =================
    def _tab_search(self):
        tab = self._new_tab("Поиск ученика")
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="ФИО (или часть):").pack(side="left")
        self.e_search = ttk.Entry(row, width=36)
        self.e_search.pack(side="left", padx=6)
        self.e_search.bind("<KeyRelease>", lambda e: self.do_search())
        ttk.Label(row, text="Поиск по всем классам. Нажмите на ученика — откроется его карточка.", style="Hint.TLabel").pack(side="left")
        self.tv_search = make_tree(tab, ("name", "class"), ("ФИО", "Класс"), (500, 120), height=16)
        self.tv_search.pack(fill="both", expand=True)
        self.tv_search.bind("<<TreeviewSelect>>", self.open_found_student)

    def do_search(self):
        self.tv_search.delete(*self.tv_search.get_children())
        for s in self.db.search_students(self.e_search.get(), self.user):
            self.tv_search.insert("", "end", iid=str(s["id"]), values=(s["full_name"], s["class_name"]))

    def open_found_student(self, _event=None):
        sel = self.tv_search.selection()
        if not sel:
            return
        st = self.db.get_student(int(sel[0]))
        if not st:
            return
        self.cb_class_gr.set(st["class_name"])
        self.load_grade_students()
        for label, sid in self.student_map.items():
            if sid == st["id"]:
                self.cb_student_gr.set(label)
        self.load_grades()
        self.nb.select(self.tab_grades)

    # ================= вкладка «Предметы» =================
    def _tab_subjects(self):
        tab = self._new_tab("Предметы")
        self.tv_subjects = make_tree(tab, ("name",), ("Предмет",), (400,), height=14)
        self.tv_subjects.pack(fill="both", expand=True, pady=6)
        row = ttk.Frame(tab)
        row.pack(fill="x")
        self.e_subject = ttk.Entry(row, width=30)
        self.e_subject.pack(side="left")
        ttk.Button(row, text="Добавить предмет", style="Accent.TButton", command=self.add_subject).pack(side="left", padx=6)
        ttk.Button(row, text="Удалить выбранный", style="Danger.TButton", command=self.delete_subject).pack(side="left")

    def refresh_subjects(self):
        subjects = self.db.list_subjects()
        self.subject_map = {s["name"]: s["id"] for s in subjects}
        self.cb_subject["values"] = list(self.subject_map)
        if self.cb_subject.get() not in self.subject_map:
            self.cb_subject.set(next(iter(self.subject_map), ""))
        self.tv_subjects.delete(*self.tv_subjects.get_children())
        for s in subjects:
            self.tv_subjects.insert("", "end", iid=str(s["id"]), values=(s["name"],))

    def add_subject(self):
        try:
            self.db.add_subject(self.e_subject.get())
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        self.e_subject.delete(0, "end")
        self.refresh_subjects()

    def delete_subject(self):
        sel = self.tv_subjects.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите предмет в списке")
            return
        try:
            self.db.delete_subject(int(sel[0]))
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        self.refresh_subjects()

    # ================= вкладка «Профиль» (для учителей) =================
    def _tab_profile(self):
        tab = self._new_tab("Профиль")
        ttk.Label(tab, text=self.user["username"], style="Stat.TLabel").pack(anchor="w")
        ttk.Label(tab, text=ROLE_NAMES[self.user["role"]], style="Hint.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Button(tab, text="Сменить пароль", style="Accent.TButton", command=self.change_password).pack(anchor="w")

    # ================= вкладка «Пользователи» (только администратор) =================
    def _tab_users(self):
        tab = self._new_tab("Пользователи")
        self.tv_users = make_tree(
            tab, ("login", "role", "classes"), ("Логин", "Роль", "Классы"), (200, 140, 400), height=10
        )
        self.tv_users.pack(fill="both", expand=True, pady=6)
        form = ttk.LabelFrame(tab, text="Новый пользователь", padding=8)
        form.pack(fill="x", pady=4)
        ttk.Label(form, text="Логин:").grid(row=0, column=0)
        self.e_new_login = ttk.Entry(form, width=18)
        self.e_new_login.grid(row=0, column=1, padx=4)
        ttk.Label(form, text="Пароль:").grid(row=0, column=2)
        self.e_new_pass = ttk.Entry(form, width=18, show="*")
        self.e_new_pass.grid(row=0, column=3, padx=4)
        ttk.Label(form, text="Роль:").grid(row=0, column=4)
        self.cb_new_role = ttk.Combobox(form, state="readonly", width=14, values=list(ROLE_NAMES.values()))
        self.cb_new_role.set(ROLE_NAMES["teacher"])
        self.cb_new_role.grid(row=0, column=5, padx=4)
        ttk.Button(form, text="Создать", style="Accent.TButton", command=self.create_user).grid(row=0, column=6, padx=6)
        row = ttk.Frame(tab)
        row.pack(fill="x")
        ttk.Button(row, text="Назначить классы учителю", style="Accent.TButton", command=self.assign_classes).pack(side="left")
        ttk.Button(row, text="Удалить пользователя", style="Danger.TButton", command=self.delete_user).pack(side="left", padx=6)
        ttk.Button(row, text="Сменить мой пароль", command=self.change_password).pack(side="right")
        ttk.Button(row, text="Запустить API", command=self.start_api).pack(side="right", padx=6)

    def load_users(self):
        self.tv_users.delete(*self.tv_users.get_children())
        for u in self.db.list_users():
            classes = "все классы" if u["role"] == "admin" else ", ".join(u["classes"]) or "—"
            self.tv_users.insert("", "end", iid=str(u["id"]), values=(u["username"], ROLE_NAMES[u["role"]], classes))

    def create_user(self):
        role = next(k for k, v in ROLE_NAMES.items() if v == self.cb_new_role.get())
        try:
            self.db.add_user(self.e_new_login.get(), self.e_new_pass.get(), role)
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        self.e_new_login.delete(0, "end")
        self.e_new_pass.delete(0, "end")
        self.load_users()

    def delete_user(self):
        sel = self.tv_users.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите пользователя")
            return
        if not messagebox.askyesno("Удаление", "Удалить выбранного пользователя?"):
            return
        try:
            self.db.delete_user(int(sel[0]), self.user["id"])
        except ValidationError as e:
            messagebox.showerror("Ошибка", str(e))
            return
        self.load_users()

    def assign_classes(self):
        sel = self.tv_users.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите учителя в списке")
            return
        uid = int(sel[0])
        classes = self.db.list_classes()
        win = tk.Toplevel(self)
        win.title("Классы учителя")
        win.grab_set()
        ttk.Label(win, text="Выберите классы (можно несколько):").pack(padx=12, pady=(12, 4))
        lb = tk.Listbox(win, selectmode="multiple", exportselection=False, height=10)
        lb.pack(padx=12, fill="both", expand=True)
        current = set(self.db.user_class_ids(uid))
        for i, c in enumerate(classes):
            lb.insert("end", c["name"])
            if c["id"] in current:
                lb.selection_set(i)

        def save():
            self.db.set_user_classes(uid, [classes[i]["id"] for i in lb.curselection()])
            win.destroy()
            self.load_users()

        ttk.Button(win, text="Сохранить", style="Accent.TButton", command=save).pack(pady=10)


def run():
    App().mainloop()
