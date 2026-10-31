"""Tkinter front end: watchlist table, check, and update."""
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import adb, repo, updater, watchlist
from .cli import _plan
from .state import State

ABIS = ["arm64-v8a", "armeabi-v7a", "x86_64", "x86"]


def _source(cfg: watchlist.Config, package: str) -> str:
    if package in cfg.packages:
        return "F-Droid"
    return "direct" if any(a.package == package for a in cfg.direct) else "GitHub"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Android Updater")
        self.geometry("820x520")
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.pending: set[str] = set()  # packages the last phone check wants to install/update
        self.cands: list[updater.Candidate] = []

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        self.buttons = [ttk.Button(bar, text=t, command=c) for t, c in [
            ("Refresh", self.refresh), ("Check phone", self.check_phone),
            ("Update", self.update_phone), ("Add app…", self.add_app), ("Remove", self.remove)]]
        for b in self.buttons:
            b.pack(side="left", padx=2)

        cols = ("package", "source", "latest", "phone", "status")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended", height=12)
        for col, text, width in zip(cols, ("Package", "Source", "Latest", "On phone", "Status"), (300, 70, 120, 90, 160)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=6)

        self.log = tk.Text(self, height=9, state="disabled")
        self.log.pack(fill="x", padx=6, pady=6)
        self.after(100, self._poll)
        self.refresh()

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
            for p in cfg.all_packages():
                rel, code = found.get(p), state.installed.get(p)
                if p in self.pending:
                    status = "update available" if code else "not installed"
                elif rel and code is not None and rel.version_code > code:
                    status = "newer than last seen"
                else:
                    status = "" if rel else "not found"
                self.tree.insert("", "end", iid=p, values=(
                    p, _source(cfg, p), rel.version_name if rel else "", code if code is not None else "", status))
            self.say(f"refreshed {len(cfg.all_packages())} app(s)")
        self.say("fetching latest versions…")
        self.run(work, done)

    def check_phone(self):
        def done(res):
            _serial, self.cands, _state = res
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
