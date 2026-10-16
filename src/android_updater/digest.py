"""Build and send a digest of watched apps that have updates waiting."""
import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import updater
from .repo import Release
from .state import State
from .watchlist import Config

ALL_ABIS = ["arm64-v8a", "armeabi-v7a", "x86_64", "x86"]


@dataclass
class Item:
    release: Release
    installed_code: int | None  # None: phone not seen with this app yet
    is_new: bool                # not yet reported in an earlier digest


def pending(index: dict, cfg: Config, state: State) -> list[Item]:
    """Apps with an update waiting.

    Where the phone's version is known (recorded on a previous `update`), pending means
    latest > installed. Otherwise we have nothing to compare with, so the first sighting is
    recorded as a baseline and only later releases count.
    """
    items = []
    for rel in updater.latest_releases(index, cfg, sdk=99, abis=ALL_ABIS):
        pkg, code = rel.package, rel.version_code
        installed = state.installed.get(pkg)
        if installed is None:
            state.notified.setdefault(pkg, code)  # baseline
            if code <= state.notified[pkg]:
                continue
        elif code <= installed:
            continue
        items.append(Item(rel, installed, code > state.notified.get(pkg, 0)))
    return items


def render(items: list[Item]) -> tuple[str, str]:
    n = len(items)
    title = f"{n} Android app update{'s' if n != 1 else ''} available"
    lines = []
    for i in items:
        old = f"{i.installed_code} → " if i.installed_code is not None else "→ "
        lines.append(f"{i.release.package}: {old}{i.release.version_name}" + (" (new)" if i.is_new else ""))
    return title, "\n".join(lines) + "\n\nPlug in your phone and run: android-updater update"


def mark_notified(items: list[Item], state: State) -> None:
    for i in items:
        state.notified[i.release.package] = i.release.version_code


def notify(title: str, body: str) -> bool:
    if sys.platform == "darwin":
        script = "on run argv\ndisplay notification (item 2 of argv) with title \"android-updater\" subtitle (item 1 of argv)\nend run"
        cmd = ["osascript", "-e", script, title, body] if shutil.which("osascript") else None
    elif shutil.which("notify-send"):
        cmd = ["notify-send", "-a", "android-updater", "-i", "phone", title, body]
    else:
        cmd = None
    return bool(cmd) and subprocess.run(cmd).returncode == 0
