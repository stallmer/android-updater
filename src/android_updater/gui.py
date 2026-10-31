"""Tkinter front end: watchlist table, check, and update."""
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import font as tkfont, messagebox, simpledialog, ttk

from . import adb, repo, updater, watchlist
from .cli import _plan
from .state import State

ABIS = ["arm64-v8a", "armeabi-v7a", "x86_64", "x86"]

# Adwaita-flavoured palettes
LIGHT = dict(bg="#f6f5f4", fg="#2e3436", card="#ffffff", alt="#f6f5f4", line="#d5d0cc", muted="#77767b",
             accent="#3584e4", accent_hover="#1c71d8", on_accent="#ffffff", select="#d3e3f8",
             ok="#26a269", warn="#c64600", bad="#c01c28")
DARK = dict(bg="#242424", fg="#ebebeb", card="#303030", alt="#383838", line="#4a4a4a", muted="#9a9996",
            accent="#3584e4", accent_hover="#4a95ee", on_accent="#ffffff", select="#1c4a80",
            ok="#57e389", warn="#ffa348", bad="#ff7b63")


def _prefers_dark() -> bool:
    try:
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "dark" in out


def _source(cfg: watchlist.Config, package: str) -> str:
    if package in cfg.packages:
        return "F-Droid"
    return "direct" if any(a.package == package for a in cfg.direct) else "GitHub"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Android Updater")
        self.geometry("900x560")
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.checked = False  # a phone check has run, so statuses can say "up to date"
        self.pending: set[str] = set()  # packages the last phone check wants to install/update
        self.cands: list[updater.Candidate] = []
        self.colors = DARK if _prefers_dark() else LIGHT
        self._style()

        root = ttk.Frame(self, padding=(16, 12, 16, 12))
        root.pack(fill="both", expand=True)

        bar = ttk.Frame(root)
        bar.pack(fill="x", pady=(0, 10))
        self.buttons = []
        for text, cmd, style in [("Refresh", self.refresh, "TButton"), ("Check phone", self.check_phone, "TButton"),
                                 ("Update", self.update_phone, "Accent.TButton"),
                                 ("Add app…", self.add_app, "TButton"), ("Remove", self.remove, "TButton")]:
            b = ttk.Button(bar, text=text, command=cmd, style=style)
            b.pack(side="left", padx=(0, 6))
            self.buttons.append(b)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self.progress.pack(side="right")

        table = ttk.Frame(root, style="Card.TFrame")
        table.pack(fill="both", expand=True)
        cols = ("package", "source", "latest", "phone", "status")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended")
        for col, text, width, stretch in zip(cols, ("Package", "Source", "Latest", "On phone", "Status"),
                                             (300, 80, 120, 100, 160), (True, False, False, False, False)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, anchor="w", stretch=stretch)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        c = self.colors
        self.tree.tag_configure("odd", background=c["alt"])
        self.tree.tag_configure("update", foreground=c["warn"])
        self.tree.tag_configure("ok", foreground=c["ok"])
        self.tree.tag_configure("bad", foreground=c["bad"])

        self._fit_columns()
        self.log = tk.Text(root, height=8, state="disabled", wrap="word", relief="flat", borderwidth=0,
                           padx=10, pady=8, background=c["card"], foreground=c["fg"],
                           insertbackground=c["fg"], highlightthickness=1, highlightbackground=c["line"],
                           font=tkfont.nametofont("TkFixedFont"))
        self.log.pack(fill="x", pady=(10, 0))
        self.after(100, self._poll)
        self.refresh()

    def _style(self):
        c = self.colors
        self.configure(background=c["bg"])
        style = ttk.Style(self)
        style.theme_use("clam")
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=max(base.cget("size"), 10) + 1)
        tkfont.nametofont("TkTextFont").configure(size=base.cget("size"))
        tkfont.nametofont("TkFixedFont").configure(size=base.cget("size") - 1)
        bold = self.bold = base.copy()
        bold.configure(weight="bold")
        style.configure(".", background=c["bg"], foreground=c["fg"], bordercolor=c["line"],
                        lightcolor=c["bg"], darkcolor=c["bg"], troughcolor=c["bg"], focuscolor=c["bg"])
        style.configure("TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["card"], borderwidth=1, relief="solid", bordercolor=c["line"])
        style.configure("TButton", padding=(14, 6), background=c["card"], bordercolor=c["line"], relief="flat")
        style.map("TButton", background=[("disabled", c["bg"]), ("active", c["alt"])],
                  foreground=[("disabled", c["muted"])])
        style.configure("Accent.TButton", background=c["accent"], foreground=c["on_accent"],
                        bordercolor=c["accent"], font=bold)
        style.map("Accent.TButton", background=[("disabled", c["line"]), ("active", c["accent_hover"])],
                  foreground=[("disabled", c["muted"])], bordercolor=[("disabled", c["line"])])
        style.configure("Treeview", background=c["card"], fieldbackground=c["card"], foreground=c["fg"],
                        rowheight=int(base.metrics("linespace") * 1.9), borderwidth=0)
        style.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", c["fg"])])
        style.configure("Treeview.Heading", background=c["bg"], foreground=c["muted"], font=bold,
                        padding=(8, 6), relief="flat", borderwidth=0)
        style.map("Treeview.Heading", background=[("active", c["bg"])])
        style.configure("Vertical.TScrollbar", background=c["line"], arrowcolor=c["muted"], bordercolor=c["card"])
        style.configure("Horizontal.TProgressbar", background=c["accent"], troughcolor=c["line"],
                        bordercolor=c["line"], thickness=6)

    def _fit_columns(self):
        """Size each column to its widest header/cell and grow the window so nothing is clipped."""
        body, head = tkfont.nametofont("TkDefaultFont"), self.bold
        total = 0
        for col in self.tree["columns"]:
            cells = (self.tree.set(i, col) for i in self.tree.get_children())
            width = max([head.measure(self.tree.heading(col, "text"))] + [body.measure(c) for c in cells]) + 32
            self.tree.column(col, width=width, minwidth=width)
            total += width
        total += 20 + 32 + 8  # scrollbar, window padding, borders
        total = min(total, self.winfo_screenwidth() - 80)
        self.minsize(total, 360)
        self.update_idletasks()
        if total > self.winfo_width():
            self.geometry(f"{total}x{self.winfo_height()}")

    def say(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self, work, done=None):
        """Run `work` off the UI thread; `done(result)` runs back on it."""
        if self.busy:
            return
        self.busy = True
        self.progress.start(12)
        for b in self.buttons:
            b.state(["disabled"])

        def target():
            try:
                self.events.put((done, work(), None))
            except (adb.AdbError, OSError, RuntimeError) as e:
                self.events.put((done, None, e))
        threading.Thread(target=target, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, result, err = self.events.get_nowait()
                self.busy = False
                self.progress.stop()
                for b in self.buttons:
                    b.state(["!disabled"])
                if err:
                    self.say(f"error: {err}")
                elif done:
                    done(result)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def refresh(self):
        def work():
            cfg = watchlist.load()
            found = {r.package: r for r in updater.latest_releases(repo.load_index(), cfg, 99, ABIS)}
            return cfg, found, State.load()

        def done(res):
            cfg, found, state = res
            self.tree.delete(*self.tree.get_children())
            for n, p in enumerate(cfg.all_packages()):
                rel, code = found.get(p), state.installed.get(p)
                if p in self.pending:
                    status, tag = ("update available" if code else "not installed"), "update"
                elif rel and code is not None and rel.version_code > code:
                    status, tag = "newer than last seen", "update"
                elif not rel:
                    status, tag = "not found", "bad"
                elif self.checked:
                    status, tag = "up to date", "ok"
                else:
                    status, tag = "", ""
                self.tree.insert("", "end", iid=p, tags=(tag, "odd" if n % 2 else ""), values=(
                    p, _source(cfg, p), rel.version_name if rel else "", code if code is not None else "", status))
            self._fit_columns()
            self.say(f"refreshed {len(cfg.all_packages())} app(s)")
        self.say("fetching latest versions…")
        self.run(work, done)

    def check_phone(self):
        def done(res):
            _serial, self.cands, _state = res
            self.checked = True
            self.pending = {c.release.package for c in self.cands}
            self.say(f"{len(self.cands)} install(s)/update(s) available" if self.cands else "everything is up to date")
            self.refresh()
        self.say("checking phone…")
        self.run(_plan, done)

    def update_phone(self):
        def work():
            serial, cands, state = _plan()
            results = updater.apply(serial, cands)
            for c in cands:
                if results[c.release.package] is None:
                    state.installed[c.release.package] = c.release.version_code
                    state.tags[c.release.package] = c.release.version_name
            state.save()
            return results

        def done(results):
            for pkg, err in results.items():
                self.say(f"{'ok  ' if err is None else 'FAIL'} {pkg}" + (f": {err}" if err else ""))
            if not results:
                self.say("everything is up to date")
            self.checked = True
            self.pending = {p for p, err in results.items() if err}
            self.refresh()
        self.say("downloading and installing…")
        self.run(work, done)

    def add_app(self):
        package = simpledialog.askstring("Add app", "F-Droid package ID:", parent=self)
        if not package or not package.strip():
            return
        package = package.strip()

        def work():
            cfg = watchlist.load()
            if package not in repo.load_index()["packages"]:
                return f"{package} not found in F-Droid index"
            if package not in cfg.packages:
                cfg.packages.append(package)
                watchlist.save(cfg)
            return f"added {package}"

        def done(msg):
            self.say(msg)
            self.refresh()
        self.run(work, done)

    def remove(self):
        sel = set(self.tree.selection())
        if not sel or not messagebox.askyesno("Remove", f"Remove {len(sel)} app(s) from the watchlist?", parent=self):
            return
        cfg = watchlist.load()
        cfg.packages = [p for p in cfg.packages if p not in sel]
        cfg.direct = [a for a in cfg.direct if a.package not in sel]
        cfg.github = [a for a in cfg.github if a.package not in sel]
        watchlist.save(cfg)
        self.say(f"removed {', '.join(sorted(sel))}")
        self.refresh()


def main():
    App().mainloop()
