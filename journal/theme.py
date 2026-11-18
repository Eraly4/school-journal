"""Внешний вид приложения: цвета, шрифты и стили ttk."""
from tkinter import ttk

BG = "#f1f5f9"
CARD = "#ffffff"
PRIMARY = "#2563eb"
PRIMARY_DARK = "#1e3a8a"
PRIMARY_HOVER = "#1d4ed8"
HOVER = "#e0e7ff"
TEXT = "#1f2937"
MUTED = "#64748b"
DANGER = "#dc2626"
DANGER_HOVER = "#b91c1c"
STRIPE = "#f4f7fe"
FONT = ("Segoe UI", 10)
BOLD = ("Segoe UI", 10, "bold")


def apply_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.font", FONT)

    style.configure(".", font=FONT, background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("TLabelframe", background=BG, bordercolor="#cbd5e1")
    style.configure("TLabelframe.Label", background=BG, foreground=PRIMARY, font=BOLD)

    # верхняя панель и карточка входа
    style.configure("Top.TFrame", background=PRIMARY_DARK)
    style.configure("Top.TLabel", background=PRIMARY_DARK, foreground="white", font=("Segoe UI", 11, "bold"))
    style.configure("Card.TFrame", background=CARD, bordercolor="#cbd5e1", borderwidth=1, relief="solid")
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Title.TLabel", background=CARD, foreground=PRIMARY, font=("Segoe UI", 20, "bold"))
    style.configure("Subtitle.TLabel", background=CARD, foreground=MUTED)
    style.configure("Stat.TLabel", font=("Segoe UI", 12, "bold"), foreground=PRIMARY)
    style.configure("Hint.TLabel", foreground=MUTED)

    # кнопки
    style.configure("TButton", padding=(12, 6), background="#e2e8f0", foreground=TEXT,
                    borderwidth=0, focuscolor="none")
    style.map("TButton", background=[("active", "#cbd5e1")])
    style.configure("Accent.TButton", background=PRIMARY, foreground="white")
    style.map("Accent.TButton", background=[("active", PRIMARY_HOVER)])
    style.configure("Danger.TButton", background=DANGER, foreground="white")
    style.map("Danger.TButton", background=[("active", DANGER_HOVER)])
    style.configure("Light.TButton", background="#dbeafe", foreground=PRIMARY_DARK)
    style.map("Light.TButton", background=[("active", "#bfdbfe")])

    # вкладки
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", padding=(16, 8), background="#e2e8f0", foreground=TEXT, font=BOLD)
    style.map("TNotebook.Tab",
              background=[("selected", PRIMARY), ("active", HOVER)],
              foreground=[("selected", "white")],
              # тема clam по умолчанию уменьшает отступы у выбранной вкладки — задаём одинаковые,
              # чтобы при выборе менялся только цвет, а размер оставался прежним
              padding=[("selected", (16, 8))],
              expand=[("selected", (0, 0, 0, 0))])

    # таблицы
    style.configure("Treeview", rowheight=28, background=CARD, fieldbackground=CARD,
                    foreground=TEXT, borderwidth=0)
    style.configure("Treeview.Heading", background="#dbe4f5", foreground=PRIMARY_DARK,
                    font=BOLD, padding=(8, 6), relief="flat")
    style.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", "white")])

    # поля ввода
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, padding=5, fieldbackground="white", bordercolor="#cbd5e1")
    style.map("TEntry", fieldbackground=[("readonly", "white")])
    style.map("TCombobox", fieldbackground=[("readonly", "white")])
