"""Native desktop UI. Tkinter/ttk only; no web service or account required."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import platform
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .branding import (APP_NAME, APP_DESCRIPTION, APP_TEAM, APP_DEVELOPER, APP_VERSION, ASSETS_DIR)
from .collector import scan_inventory
from .export import export_csv, export_html, export_json, export_pdf
from .models import ChangeSet, Inventory, Software, compare
from .storage import latest_snapshot, save_snapshot

COLORS = {
    "background": "#f4f6f9", "surface": "#ffffff", "ink": "#192a3d",
    "muted": "#67788b", "line": "#dce3eb", "accent": "#1e5b93", "soft": "#eaf1f8",
}


def readable_date(value: str) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d.%m.%Y %H:%M") if parsed.tzinfo else parsed.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


class SoftwareAuditApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} — {APP_DESCRIPTION}")
        self.root.minsize(950, 630)
        self.root.geometry("1250x790")
        self.root.configure(background=COLORS["background"])
        self._app_icon = None
        self._header_icon = None
        try:
            self._app_icon = tk.PhotoImage(file=str(ASSETS_DIR / "app-icon.png"))
            self.root.iconphoto(True, self._app_icon)
        except (tk.TclError, OSError):
            pass
        self.current: Inventory | None = None
        self.changes: ChangeSet | None = None
        self.previous: Inventory | None = None
        self.rows: dict[str, Software] = {}
        self.visible: list[Software] = []
        self.sort_key, self.sort_desc = "name", False
        self.messages: queue.Queue = queue.Queue()
        self.scanning = False
        self.search = tk.StringVar()
        self.source = tk.StringVar(value="Все источники")
        self.include_profiler = tk.BooleanVar(value=True)
        self.include_store = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Готово к первому сканированию")
        self._styles()
        self._layout()
        self.search.trace_add("write", lambda *_: self._filter())
        self.source.trace_add("write", lambda *_: self._filter())
        self._restore()
        self.root.after(120, self._drain_messages)

    def _styles(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Audit.TFrame", background=COLORS["background"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Audit.TLabel", background=COLORS["background"],
                        foreground=COLORS["ink"], font=("Arial", 10))
        style.configure("Subtle.TLabel", background=COLORS["background"],
                        foreground=COLORS["muted"], font=("Arial", 10))
        style.configure("Accent.TButton", font=("Arial", 10, "bold"), padding=(15, 10),
                        background=COLORS["accent"], foreground="white", borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#154a7b"), ("disabled", "#a3b2c1")])
        style.configure("Audit.TButton", font=("Arial", 10), padding=(11, 9),
                        background=COLORS["surface"], foreground=COLORS["ink"])
        style.configure("Audit.Treeview", rowheight=31, font=("Arial", 10),
                        background="white", fieldbackground="white", foreground=COLORS["ink"],
                        borderwidth=0)
        style.configure("Audit.Treeview.Heading", font=("Arial", 10, "bold"),
                        padding=(10, 10), background="#edf2f7", foreground=COLORS["ink"])
        style.map("Audit.Treeview", background=[("selected", "#dceaf7")],
                  foreground=[("selected", COLORS["ink"])])
        style.configure("Audit.TNotebook", background=COLORS["background"], borderwidth=0)
        style.configure("Audit.TNotebook.Tab", padding=(15, 8), font=("Arial", 10))

    def _layout(self):
        container = ttk.Frame(self.root, style="Audit.TFrame", padding=23)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="Audit.TFrame")
        header.pack(fill="x", pady=(0, 18))
        heading = ttk.Frame(header, style="Audit.TFrame")
        heading.pack(side="left", fill="x", expand=True)
        try:
            self._header_icon = tk.PhotoImage(file=str(ASSETS_DIR / "logo-header.png"))
            tk.Label(heading, image=self._header_icon, bg=COLORS["background"], bd=0).pack(side="left", padx=(0, 12))
        except (tk.TclError, OSError):
            pass
        titles = tk.Frame(heading, bg=COLORS["background"])
        titles.pack(side="left", anchor="w")
        tk.Label(titles, text=APP_NAME, font=("Arial", 21, "bold"),
                 bg=COLORS["background"], fg=COLORS["ink"]).pack(anchor="w")
        ttk.Label(titles, text=f"{APP_DESCRIPTION} · локальный режим",
                  style="Subtle.TLabel").pack(anchor="w", pady=(5, 0))
        self.scan_button = ttk.Button(header, text="↻  Сканировать", style="Accent.TButton",
                                      command=self.start_scan)
        self.scan_button.pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Экспорт отчёта", style="Audit.TButton",
                   command=self.export).pack(side="right")
        ttk.Button(header, text="О программе", style="Audit.TButton",
                   command=self.show_about).pack(side="right", padx=(0, 8))

        stats = tk.Frame(container, bg=COLORS["background"])
        stats.pack(fill="x", pady=(0, 16))
        self.stats = {}
        stat_specs = (("total", "Найдено записей"), ("sources", "Источников"),
                      ("new", "Новые"), ("updated", "Обновлены"), ("removed", "Удалены"))
        for i, (key, title) in enumerate(stat_specs):
            frame = tk.Frame(stats, bg="white", highlightbackground=COLORS["line"],
                             highlightthickness=1, padx=16, pady=12)
            frame.grid(row=0, column=i, padx=(0, 9) if i < 4 else 0, sticky="nsew")
            stats.grid_columnconfigure(i, weight=1)
            tk.Label(frame, text=title, font=("Arial", 9), bg="white",
                     fg=COLORS["muted"]).pack(anchor="w")
            number = tk.Label(frame, text="—", font=("Arial", 23, "bold"),
                              bg="white", fg=COLORS["ink"])
            number.pack(anchor="w", pady=(3, 0))
            self.stats[key] = number

        filters = ttk.Frame(container, style="Audit.TFrame")
        filters.pack(fill="x", pady=(0, 12))
        ttk.Label(filters, text="Поиск", style="Audit.TLabel").pack(side="left", padx=(0, 8))
        self.search_field = ttk.Entry(filters, textvariable=self.search, width=42)
        self.search_field.pack(side="left", fill="x", expand=True, padx=(0, 15))
        ttk.Label(filters, text="Источник", style="Audit.TLabel").pack(side="left", padx=(0, 8))
        self.source_field = ttk.Combobox(filters, textvariable=self.source, state="readonly", width=28,
                                         values=["Все источники"])
        self.source_field.pack(side="left")

        table_area = ttk.Frame(container, style="Surface.TFrame")
        table_area.pack(fill="both", expand=True)
        cols = ("name", "version", "publisher", "source", "installed_at", "install_path")
        captions = ("ПРОГРАММА", "ВЕРСИЯ", "РАЗРАБОТЧИК", "ИСТОЧНИК", "ДАТА УСТАНОВКИ", "ПУТЬ")
        self.tree = ttk.Treeview(table_area, columns=cols, show="headings", selectmode="browse",
                                 style="Audit.Treeview")
        for col, caption, width in zip(cols, captions, (240, 130, 190, 180, 155, 280)):
            self.tree.heading(col, text=caption, command=lambda key=col: self._sort(key))
            self.tree.column(col, width=width, minwidth=80, stretch=(col in {"name", "publisher", "install_path"}))
        scroll_y = ttk.Scrollbar(table_area, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(table_area, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table_area.grid_rowconfigure(0, weight=1)
        table_area.grid_columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._select)

        notebook = ttk.Notebook(container, style="Audit.TNotebook")
        notebook.pack(fill="x", pady=(12, 0))
        details_tab = ttk.Frame(notebook, style="Surface.TFrame")
        history_tab = ttk.Frame(notebook, style="Surface.TFrame")
        options_tab = ttk.Frame(notebook, style="Surface.TFrame")
        notebook.add(details_tab, text="Сведения об установленном ПО")
        notebook.add(history_tab, text="Изменения с прошлого сканирования")
        notebook.add(options_tab, text="Настройки сканирования")
        self.details = tk.Text(details_tab, height=6, wrap="word", font=("Arial", 10),
                               bg="white", fg=COLORS["ink"], relief="flat", padx=15, pady=10)
        details_scroll = ttk.Scrollbar(details_tab, orient="vertical", command=self.details.yview)
        self.details.configure(yscrollcommand=details_scroll.set)
        self.details.pack(side="left", fill="both", expand=True)
        details_scroll.pack(side="right", fill="y")
        self.details.configure(state="disabled")
        self.history = tk.Text(history_tab, height=6, wrap="word", font=("Arial", 10),
                               bg="white", fg=COLORS["ink"], relief="flat", padx=15, pady=10)
        history_scroll = ttk.Scrollbar(history_tab, orient="vertical", command=self.history.yview)
        self.history.configure(yscrollcommand=history_scroll.set)
        self.history.pack(side="left", fill="both", expand=True)
        history_scroll.pack(side="right", fill="y")
        self.history.configure(state="disabled")
        options_inner = tk.Frame(options_tab, bg="white", padx=15, pady=10)
        options_inner.pack(fill="x")
        if platform.system() == "Darwin":
            ttk.Checkbutton(options_inner, text="Дополнительно использовать system_profiler (полнее, но медленнее)",
                            variable=self.include_profiler).pack(anchor="w")
        elif platform.system() == "Windows":
            ttk.Checkbutton(options_inner, text="Включать приложения Microsoft Store",
                            variable=self.include_store).pack(anchor="w")
        else:
            tk.Label(options_inner, text="Используются доступные локальные пакетные менеджеры.",
                     bg="white", fg=COLORS["ink"]).pack(anchor="w")
        tk.Label(options_inner, text="История хранится только на этом компьютере, в ~/.software-audit/snapshots.",
                 bg="white", fg=COLORS["muted"]).pack(anchor="w", pady=(6, 0))

        bottom = ttk.Frame(container, style="Audit.TFrame")
        bottom.pack(fill="x", pady=(12, 0))
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=110)
        self.progress.pack(side="right")
        ttk.Label(bottom, textvariable=self.status, style="Subtle.TLabel").pack(side="left")
        self._set_text(self.details, "Выберите программу в таблице, чтобы увидеть все доступные сведения.")
        self._set_text(self.history, "Сравнение появится после второго сканирования.")

    def show_about(self) -> None:
        """Display product identity and credits without affecting scanning."""
        bg, panel, line, cyan, muted = "#0b182b", "#122741", "#315878", "#57d7f7", "#bacce1"
        dialog = tk.Toplevel(self.root)
        dialog.title(f"О программе — {APP_NAME}")
        dialog.configure(bg=bg)
        dialog.geometry("850x450")
        dialog.minsize(750, 410)
        dialog.transient(self.root)
        dialog.grab_set()
        if self._app_icon is not None:
            try:
                dialog.iconphoto(True, self._app_icon)
            except tk.TclError:
                pass

        panel_frame = tk.Frame(dialog, bg=panel, highlightbackground=line, highlightthickness=1)
        panel_frame.pack(fill="both", expand=True, padx=18, pady=18)
        top = tk.Frame(panel_frame, bg=panel)
        top.pack(fill="x", padx=25, pady=(19, 14))
        tk.Label(top, text="ⓘ  О программе", bg=panel, fg="white",
                 font=("Arial", 16, "bold")).pack(side="left")
        tk.Frame(panel_frame, bg=line, height=1).pack(fill="x")

        main = tk.Frame(panel_frame, bg=panel)
        main.pack(fill="both", expand=True, padx=25, pady=23)
        image_area = tk.Frame(main, width=260, bg=panel)
        image_area.pack(side="left", fill="y", padx=(0, 25))
        image_area.pack_propagate(False)
        try:
            logo = tk.PhotoImage(file=str(ASSETS_DIR / "logo-about.png"))
            dialog._about_logo = logo  # Keep Tk image alive while the dialog is open.
            tk.Label(image_area, image=logo, bg=panel, bd=0).pack(expand=True)
        except (tk.TclError, OSError):
            tk.Label(image_area, text="АПО", font=("Arial", 34, "bold"),
                     fg=cyan, bg=panel).pack(expand=True)
        tk.Frame(main, width=1, bg=line).pack(side="left", fill="y", padx=(0, 25))
        right = tk.Frame(main, bg=panel)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text=APP_NAME, bg=panel, fg=cyan,
                 font=("Arial", 24, "bold")).pack(anchor="w", pady=(2, 4))
        tk.Label(right, text=APP_DESCRIPTION, bg=panel, fg=muted,
                 font=("Arial", 12)).pack(anchor="w")
        tk.Label(right, text=f"Версия {APP_VERSION}", bg=panel, fg="white",
                 font=("Arial", 10, "bold"), pady=6).pack(anchor="w", pady=(14, 11))
        tk.Label(right, text=f"Разработка: {APP_TEAM.lower()}", bg=panel, fg="white",
                 font=("Arial", 11), anchor="w").pack(anchor="w", pady=5)
        tk.Label(right, text=f"Разработчик: {APP_DEVELOPER}", bg=panel,
                 fg="white", font=("Arial", 11), anchor="w", wraplength=435,
                 justify="left").pack(anchor="w", pady=5)
        tk.Label(right, text="Локальный аудит установленного ПО.\n"
                            "Программа не изменяет установленные приложения.",
                 bg=panel, fg=muted, font=("Arial", 10),
                 justify="left", wraplength=425).pack(anchor="w", pady=(16, 0))
        tk.Frame(panel_frame, bg=line, height=1).pack(fill="x")
        bottom = tk.Frame(panel_frame, bg=panel)
        bottom.pack(fill="x", padx=25, pady=14)
        tk.Button(bottom, text="Закрыть", command=dialog.destroy,
                  bg="#146d9d", fg="white", activebackground="#188cbf",
                  activeforeground="white", relief="flat", bd=0,
                  font=("Arial", 11, "bold"), padx=24, pady=8).pack(side="right")
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.focus_set()

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _restore(self) -> None:
        try:
            saved = latest_snapshot()
        except (OSError, PermissionError):
            saved = None
        if saved:
            self.current = saved
            self.status.set("Загружен прежний отчёт от " + readable_date(saved.scanned_at) + ". Нажмите «Сканировать».")
            self._update_view()

    def start_scan(self) -> None:
        if self.scanning:
            return
        self.scanning = True
        self.scan_button.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Начинается локальное сканирование…")
        settings = (self.include_store.get(), self.include_profiler.get())

        def worker():
            try:
                before = latest_snapshot()
                current = scan_inventory(include_store=settings[0], include_profiler=settings[1],
                                         progress=lambda message: self.messages.put(("progress", message)))
                delta = compare(before, current) if before is not None else None
                try:
                    save_snapshot(current)
                except OSError as exc:
                    current.warnings.append(f"История не сохранена: {exc}")
                self.messages.put(("done", current, delta, before))
            except Exception as exc:
                self.messages.put(("error", f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=worker, name="software-audit-scan", daemon=True).start()

    def _drain_messages(self) -> None:
        try:
            while True:
                action, *payload = self.messages.get_nowait()
                if action == "progress":
                    self.status.set(payload[0])
                elif action == "done":
                    self.current, self.changes, self.previous = payload
                    self.scanning = False
                    self.progress.stop()
                    self.scan_button.configure(state="normal")
                    self._update_view()
                    note = f"Сканирование завершено: {len(self.current.records)} записей · "
                    note += readable_date(self.current.scanned_at)
                    if self.current.warnings:
                        note += f" · предупреждений: {len(self.current.warnings)}"
                    self.status.set(note)
                elif action == "error":
                    self.scanning = False
                    self.progress.stop()
                    self.scan_button.configure(state="normal")
                    self.status.set("Ошибка сканирования")
                    messagebox.showerror(APP_NAME, payload[0], parent=self.root)
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(120, self._drain_messages)
        except tk.TclError:
            pass

    def _update_view(self) -> None:
        if self.current is None:
            return
        count = len(self.current.records)
        categories = sorted({name.strip() for record in self.current.records
                             for name in record.source.split("; ") if name.strip()})
        self.source_field.configure(values=["Все источники", *categories])
        if self.source.get() not in ("Все источники", *categories):
            self.source.set("Все источники")
        self.stats["total"].configure(text=str(count))
        self.stats["sources"].configure(text=str(len(categories)))
        for key, number in (("new", len(self.changes.added) if self.changes else None),
                            ("updated", len(self.changes.updated) if self.changes else None),
                            ("removed", len(self.changes.removed) if self.changes else None)):
            self.stats[key].configure(text=str(number) if number is not None else "—")
        self._filter()
        self._show_changes()

    def _filter(self) -> None:
        if self.current is None:
            return
        term = self.search.get().strip().casefold()
        selected_source = self.source.get()
        self.visible = [record for record in self.current.records
                        if (not term or term in " ".join((record.name, record.version, record.publisher,
                                                           record.source, record.install_path,
                                                           record.identifier)).casefold())
                        and (selected_source == "Все источники" or
                             selected_source in record.source.split("; "))]
        self.visible.sort(key=lambda record: str(getattr(record, self.sort_key, "")).casefold(),
                          reverse=self.sort_desc)
        self.rows.clear()
        self.tree.delete(*self.tree.get_children())
        for index, record in enumerate(self.visible):
            key = str(index)
            self.rows[key] = record
            self.tree.insert("", "end", iid=key,
                             values=(record.name, record.version or "—", record.publisher or "—",
                                     record.source, record.installed_at or "—", record.install_path or "—"))

    def _sort(self, key: str) -> None:
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, False
        self._filter()

    def _select(self, _event=None):
        selected = self.tree.selection()
        if not selected or selected[0] not in self.rows:
            return
        item = self.rows[selected[0]]
        values = (("Программа", item.name), ("Версия", item.version),
                  ("Разработчик", item.publisher), ("Источник сведений", item.source),
                  ("Путь установки", item.install_path), ("Дата установки", item.installed_at),
                  ("Идентификатор", item.identifier), ("Область установки", item.scope))
        self._set_text(self.details, "\n".join(f"{title}: {value or 'нет данных'}" for title, value in values))

    def _show_changes(self) -> None:
        if self.current is None:
            return
        if self.changes is None:
            message = "Предыдущего снимка нет. После следующего сканирования здесь будут изменения."
            if self.current.warnings:
                message += "\n\nПредупреждения:\n" + "\n".join(self.current.warnings)
        else:
            changes = self.changes
            lines = [f"Добавлено: {len(changes.added)}   ·   Обновлено: {len(changes.updated)}   ·   Удалено: {len(changes.removed)}", ""]
            lines.extend("+ " + item.name + (" · " + item.version if item.version else "") for item in changes.added)
            lines.extend(f"↑ {old.name}: {old.version or 'неизвестно'} → {new.version or 'неизвестно'}"
                         for old, new in changes.updated)
            lines.extend("− " + item.name for item in changes.removed)
            if self.current.warnings:
                lines += ["", "Предупреждения:", *self.current.warnings]
            message = "\n".join(lines)
        self._set_text(self.history, message)

    def export(self) -> None:
        if self.current is None:
            messagebox.showinfo(APP_NAME, "Сначала выполните сканирование.", parent=self.root)
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="Сохранить отчёт",
                    defaultextension=".csv", initialfile="APO_TIMIMO_inventory",
                    filetypes=[("CSV (Excel)", "*.csv"), ("PDF", "*.pdf"),
                               ("HTML", "*.html"), ("JSON", "*.json")])
        if not filename:
            return
        path = Path(filename)
        formats = {".csv": export_csv, ".pdf": export_pdf,
                   ".html": export_html, ".json": export_json}
        exporter = formats.get(path.suffix.lower())
        if exporter is None:
            messagebox.showerror(APP_NAME, "Выберите CSV, PDF, HTML или JSON.", parent=self.root)
            return
        try:
            exporter(self.current, path, self.visible)
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Ошибка экспорта", str(exc), parent=self.root)
            return
        messagebox.showinfo("Отчёт сохранён", f"{path}\n\nЭкспортировано записей: {len(self.visible)}.\n"
                            "Экспортируются записи с учётом выбранных фильтров.", parent=self.root)


def main() -> None:
    root = tk.Tk()
    SoftwareAuditApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
