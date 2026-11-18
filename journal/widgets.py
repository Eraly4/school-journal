"""Собственные виджеты: таблица с чередующимися строками и выбор даты по календарю."""
import calendar
import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from .theme import BOLD, CARD, FONT, HOVER, MUTED, PRIMARY, STRIPE, TEXT

MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
          "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


class StripedTree(ttk.Treeview):
    """Таблица, в которой строки автоматически красятся «зеброй»."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.tag_configure("even", background=CARD)
        self.tag_configure("odd", background=STRIPE)

    def insert(self, parent, index, iid=None, **kw):
        kw.setdefault("tags", ("odd" if len(self.get_children(parent)) % 2 else "even",))
        return super().insert(parent, index, iid=iid, **kw)


class DatePicker(ttk.Frame):
    """Поле даты: кнопки «‹ ›» меняют день, «Календарь» открывает выбор даты мышкой."""

    def __init__(self, parent, command=None):
        super().__init__(parent)
        self.command = command
        self.value = date.today()
        self.var = tk.StringVar()
        ttk.Button(self, text="‹", width=2, command=lambda: self.shift(-1)).pack(side="left")
        self.entry = ttk.Entry(self, textvariable=self.var, width=11, justify="center", state="readonly")
        self.entry.pack(side="left", padx=3)
        self.entry.bind("<Button-1>", lambda e: self.open_calendar())
        ttk.Button(self, text="›", width=2, command=lambda: self.shift(1)).pack(side="left")
        ttk.Button(self, text="Календарь", style="Light.TButton", command=self.open_calendar).pack(
            side="left", padx=(6, 0))
        self.var.set(self.get())

    def get(self) -> str:
        return self.value.strftime("%d.%m.%Y")

    def set(self, value: date):
        self.value = value
        self.var.set(self.get())

    def _changed(self):
        self.var.set(self.get())
        if self.command:
            self.command()

    def shift(self, days: int):
        self.value += timedelta(days=days)
        self._changed()

    def pick(self, value: date):
        self.value = value
        self._changed()

    def open_calendar(self):
        CalendarPopup(self, self.value, self.pick)


class CalendarPopup(tk.Toplevel):
    def __init__(self, anchor, selected: date, on_pick):
        super().__init__(anchor)
        self.title("Выбор даты")
        self.resizable(False, False)
        self.configure(bg=CARD)
        self.transient(anchor.winfo_toplevel())
        self.selected, self.on_pick = selected, on_pick
        self.year, self.month = selected.year, selected.month
        self.geometry(f"+{anchor.winfo_rootx()}+{anchor.winfo_rooty() + anchor.winfo_height() + 4}")
        self.body = tk.Frame(self, bg=CARD, padx=10, pady=10)
        self.body.pack()
        self.render()
        self.bind("<Escape>", lambda e: self.destroy())
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass

    def move(self, months: int):
        index = self.year * 12 + self.month - 1 + months
        self.year, month0 = divmod(index, 12)
        self.month = month0 + 1
        self.render()

    def choose(self, d: date):
        self.destroy()
        self.on_pick(d)

    def render(self):
        for w in self.body.winfo_children():
            w.destroy()
        nav = tk.Frame(self.body, bg=CARD)
        nav.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 6))

        def nav_button(text, months, side):
            tk.Button(nav, text=text, command=lambda: self.move(months), relief="flat", bg=CARD, fg=PRIMARY,
                      activebackground=HOVER, font=BOLD, width=3, cursor="hand2").pack(side=side)

        nav_button("«", -12, "left")
        nav_button("‹", -1, "left")
        nav_button("»", 12, "right")
        nav_button("›", 1, "right")
        tk.Label(nav, text=f"{MONTHS[self.month - 1]} {self.year}", bg=CARD, fg=TEXT, font=BOLD).pack(
            side="left", expand=True)

        for c, name in enumerate(WEEKDAYS):
            tk.Label(self.body, text=name, bg=CARD, fg="#dc2626" if c >= 5 else MUTED, font=BOLD, width=4).grid(
                row=1, column=c)
        today = date.today()
        weeks = calendar.monthcalendar(self.year, self.month)
        for r, week in enumerate(weeks, start=2):
            for c, day in enumerate(week):
                if not day:
                    continue
                d = date(self.year, self.month, day)
                if d == self.selected:
                    bg, fg = PRIMARY, "white"
                elif d == today:
                    bg, fg = "#dbeafe", TEXT
                else:
                    bg, fg = CARD, "#dc2626" if c >= 5 else TEXT
                tk.Button(self.body, text=str(day), width=4, relief="flat", bg=bg, fg=fg, font=FONT,
                          activebackground=HOVER, cursor="hand2",
                          command=lambda d=d: self.choose(d)).grid(row=r, column=c, padx=1, pady=1)
        tk.Button(self.body, text="Сегодня", relief="flat", bg="#dbeafe", fg=PRIMARY, font=BOLD, cursor="hand2",
                  command=lambda: self.choose(date.today())).grid(
            row=len(weeks) + 2, column=0, columnspan=7, sticky="ew", pady=(8, 0))
